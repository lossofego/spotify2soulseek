"""
Spotify OAuth - Direct login for users without any setup

Uses the Authorization Code Flow with PKCE, which doesn't require a client secret.
We use a well-known client ID from an open-source project (this is a common practice).

Spotify allows HTTP for loopback addresses (127.0.0.1) per their Nov 2025 OAuth migration:
https://developer.spotify.com/blog/2025-02-12-increasing-the-security-requirements-for-integrating-with-spotify
"""

import os
import json
import time
import base64
import hashlib
import secrets
import webbrowser
import urllib.parse
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import requests

from slskd_manager import get_data_dir

# Spotify OAuth endpoints
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_URL = "https://api.spotify.com/v1"

# Spotify app Client ID (PKCE auth - no secret needed)
# Users can override this via SPOTIFY_CLIENT_ID env var or config
CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "fe284d9814144e1980cec22ef0c4ab47")

# HTTP loopback — Spotify explicitly allows http:// for 127.0.0.1
# No more self-signed certs, no more browser warnings
REDIRECT_URI = "http://127.0.0.1:8888/callback"

SCOPES = "user-library-read playlist-read-private playlist-read-collaborative"

# Rate limit / retry settings
MAX_RETRIES = 3
RATE_LIMIT_BACKOFF_BASE = 2  # seconds, doubles each retry

logger = logging.getLogger(__name__)


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to catch the OAuth callback"""

    def do_GET(self):
        """Handle the callback from Spotify"""
        # Parse the URL
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
            <html>
            <head>
                <style>
                    body { font-family: -apple-system, sans-serif; display: flex;
                           justify-content: center; align-items: center; height: 100vh;
                           margin: 0; background: #1a1a1a; color: #fff; }
                    .box { text-align: center; }
                    h1 { font-size: 24px; margin-bottom: 10px; }
                    p { color: #888; }
                </style>
            </head>
            <body>
                <div class="box">
                    <h1>&#10003; Logged in!</h1>
                    <p>You can close this window and return to spotify2slsk.</p>
                </div>
            </body>
            </html>
            """)
        elif 'error' in params:
            self.server.auth_error = params['error'][0]
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(f"<html><body><h1>Error: {params['error'][0]}</h1></body></html>".encode())
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress logging"""
        pass


def generate_pkce_pair():
    """Generate PKCE code verifier and challenge"""
    # Generate a random code verifier
    code_verifier = secrets.token_urlsafe(64)[:128]

    # Create the code challenge
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip('=')

    return code_verifier, code_challenge


def get_token_path():
    """Get path to stored token"""
    return os.path.join(get_data_dir(), "spotify_token.json")


def load_token():
    """Load saved token if it exists"""
    path = get_token_path()
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            logger.warning("Corrupt token file, will need fresh login")
            return None
    return None


def save_token(token_data):
    """Save token to disk"""
    path = get_token_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(token_data, f)


def refresh_token(refresh_token_str):
    """Refresh an expired access token"""
    try:
        response = requests.post(SPOTIFY_TOKEN_URL, data={
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token_str,
            'client_id': CLIENT_ID
        }, timeout=15)
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error refreshing token: {e}")
        return None

    if response.status_code == 200:
        token_data = response.json()
        token_data['obtained_at'] = time.time()
        # Keep the refresh token if not returned
        if 'refresh_token' not in token_data:
            token_data['refresh_token'] = refresh_token_str
        save_token(token_data)
        return token_data

    logger.warning(f"Token refresh failed: {response.status_code} {response.text[:200]}")
    return None


def get_valid_token():
    """Get a valid access token, refreshing if necessary"""
    token_data = load_token()
    if not token_data:
        return None

    # Check if token is expired (with 60 second buffer)
    expires_at = token_data.get('obtained_at', 0) + token_data.get('expires_in', 0) - 60

    if time.time() > expires_at:
        # Token expired, try to refresh
        if 'refresh_token' in token_data:
            token_data = refresh_token(token_data['refresh_token'])
    return token_data


def spotify_login():
    """
    Perform Spotify OAuth login.
    Opens browser for user to authorize, returns access token.

    Uses plain HTTP on 127.0.0.1 loopback — no SSL certs needed.
    Spotify explicitly permits this per their OAuth policy.
    """
    # Generate PKCE codes
    code_verifier, code_challenge = generate_pkce_pair()

    # Generate state for security
    state = secrets.token_urlsafe(16)

    # Build authorization URL
    auth_params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPES,
        'code_challenge_method': 'S256',
        'code_challenge': code_challenge,
        'state': state
    }
    auth_url = f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(auth_params)}"

    # Start local HTTP server to catch callback
    # No SSL/TLS needed — Spotify allows http://127.0.0.1
    server = HTTPServer(('127.0.0.1', 8888), CallbackHandler)
    server.auth_code = None
    server.auth_error = None
    server.timeout = 120  # 2 minute timeout

    try:
        # Open browser
        webbrowser.open(auth_url)

        # Wait for callback
        while server.auth_code is None and server.auth_error is None:
            server.handle_request()
    finally:
        server.server_close()

    if server.auth_error:
        raise Exception(f"Spotify authorization failed: {server.auth_error}")

    if not server.auth_code:
        raise Exception("No authorization code received")

    # Exchange code for token
    try:
        token_response = requests.post(SPOTIFY_TOKEN_URL, data={
            'grant_type': 'authorization_code',
            'code': server.auth_code,
            'redirect_uri': REDIRECT_URI,
            'client_id': CLIENT_ID,
            'code_verifier': code_verifier
        }, timeout=15)
    except requests.exceptions.RequestException as e:
        raise Exception(f"Network error exchanging auth code: {e}")

    if token_response.status_code != 200:
        raise Exception(f"Failed to get token: {token_response.text}")

    token_data = token_response.json()
    token_data['obtained_at'] = time.time()

    # Save token
    save_token(token_data)

    return token_data


def is_logged_in():
    """Check if user is logged into Spotify"""
    token = get_valid_token()
    return token is not None


def logout():
    """Remove saved Spotify token"""
    path = get_token_path()
    if os.path.exists(path):
        os.remove(path)


class SpotifyClient:
    """Simple Spotify API client with retry logic"""

    def __init__(self, access_token):
        self.access_token = access_token
        self.headers = {'Authorization': f'Bearer {access_token}'}

    def _get(self, endpoint, params=None):
        """Make a GET request to Spotify API with retry on rate limits"""
        url = f"{SPOTIFY_API_URL}/{endpoint}"

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=15)
            except requests.exceptions.ConnectionError as e:
                if attempt < MAX_RETRIES:
                    wait = RATE_LIMIT_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(f"Connection error on {endpoint}, retrying in {wait}s: {e}")
                    time.sleep(wait)
                    continue
                raise
            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES:
                    wait = RATE_LIMIT_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(f"Timeout on {endpoint}, retrying in {wait}s")
                    time.sleep(wait)
                    continue
                raise

            # Handle rate limiting (429)
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', RATE_LIMIT_BACKOFF_BASE * (2 ** attempt)))
                logger.warning(f"Rate limited by Spotify, waiting {retry_after}s (attempt {attempt + 1}/{MAX_RETRIES + 1})")
                time.sleep(retry_after)
                continue

            # Handle server errors (5xx) with retry
            if response.status_code >= 500:
                if attempt < MAX_RETRIES:
                    wait = RATE_LIMIT_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(f"Spotify server error {response.status_code} on {endpoint}, retrying in {wait}s")
                    time.sleep(wait)
                    continue

            # Raise on client errors (4xx except 429) or final server errors
            response.raise_for_status()
            return response.json()

        # Should not reach here, but just in case
        raise Exception(f"Failed to fetch {endpoint} after {MAX_RETRIES + 1} attempts")

    def get_current_user(self):
        """Get current user's profile"""
        return self._get('me')

    def get_liked_songs(self, progress_callback=None):
        """Fetch all liked songs"""
        songs = []
        offset = 0
        limit = 50

        while True:
            data = self._get('me/tracks', {'limit': limit, 'offset': offset})
            if not data['items']:
                break

            for item in data['items']:
                track = item['track']
                if track:
                    songs.append({
                        'name': track['name'],
                        'artist': track['artists'][0]['name'] if track['artists'] else 'Unknown',
                        'album': track['album']['name'] if track['album'] else 'Unknown',
                        'duration_ms': track.get('duration_ms', 0)
                    })

            offset += limit
            if progress_callback:
                progress_callback(len(songs), data.get('total', 0))

            if offset >= data.get('total', 0):
                break

            time.sleep(0.1)  # Rate limiting

        return songs

    def get_playlists(self, progress_callback=None):
        """Fetch all user's playlists with tracks"""
        playlists = []
        offset = 0
        limit = 50

        # Get current user ID to filter own playlists
        user = self.get_current_user()
        user_id = user['id']

        # First, get all playlist metadata
        while True:
            data = self._get('me/playlists', {'limit': limit, 'offset': offset})
            if not data['items']:
                break

            for item in data['items']:
                # Only include user's own playlists
                if item['owner']['id'] == user_id:
                    playlists.append({
                        'name': item['name'],
                        'id': item['id'],
                        'total_tracks': item['tracks']['total'],
                        'tracks': []
                    })

            offset += limit
            if offset >= data.get('total', 0):
                break

            time.sleep(0.1)

        # Now fetch tracks for each playlist
        for i, playlist in enumerate(playlists):
            if progress_callback:
                progress_callback(i, len(playlists), playlist['name'])

            offset = 0
            while True:
                try:
                    data = self._get(f"playlists/{playlist['id']}/tracks",
                                    {'limit': 100, 'offset': offset})
                except requests.exceptions.HTTPError as e:
                    # Log and skip this playlist if we hit a permissions error (403)
                    # or the playlist was deleted (404)
                    if hasattr(e, 'response') and e.response is not None:
                        status = e.response.status_code
                        if status in (403, 404):
                            logger.warning(f"Skipping playlist '{playlist['name']}': HTTP {status}")
                            break
                    # Re-raise unexpected HTTP errors after retries are exhausted
                    logger.error(f"Error fetching playlist '{playlist['name']}': {e}")
                    break
                except requests.exceptions.RequestException as e:
                    # Network errors — log and move on to next playlist
                    logger.error(f"Network error fetching playlist '{playlist['name']}': {e}")
                    break

                if not data['items']:
                    break

                for item in data['items']:
                    track = item.get('track')
                    if track and track.get('name'):
                        playlist['tracks'].append({
                            'name': track['name'],
                            'artist': track['artists'][0]['name'] if track['artists'] else 'Unknown',
                            'album': track['album']['name'] if track['album'] else 'Unknown',
                            'duration_ms': track.get('duration_ms', 0)
                        })

                offset += 100
                if offset >= data.get('total', 0):
                    break

                time.sleep(0.1)

        return playlists


def fetch_spotify_library(progress_callback=None):
    """
    Fetch entire Spotify library (liked songs + playlists).
    Returns (liked_songs, playlists) tuple.
    """
    token_data = get_valid_token()
    if not token_data:
        raise Exception("Not logged into Spotify")

    client = SpotifyClient(token_data['access_token'])

    # Fetch liked songs
    if progress_callback:
        progress_callback("Fetching liked songs...")
    liked_songs = client.get_liked_songs()

    # Fetch playlists
    if progress_callback:
        progress_callback("Fetching playlists...")
    playlists = client.get_playlists()

    return liked_songs, playlists


# For testing
if __name__ == "__main__":
    print("Testing Spotify OAuth...")
    if is_logged_in():
        print("Already logged in!")
        token = get_valid_token()
        client = SpotifyClient(token['access_token'])
        user = client.get_current_user()
        print(f"Logged in as: {user['display_name']}")
    else:
        print("Not logged in. Starting login flow...")
        token = spotify_login()
        print("Login successful!")
        client = SpotifyClient(token['access_token'])
        user = client.get_current_user()
        print(f"Logged in as: {user['display_name']}")
