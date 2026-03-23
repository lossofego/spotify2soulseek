"""
Spotify OAuth - Direct login for users without any setup

Uses the Authorization Code Flow with PKCE, which doesn't require a client secret.
We use a well-known client ID from an open-source project (this is a common practice).
"""

import os
import json
import time
import base64
import hashlib
import secrets
import webbrowser
import urllib.parse
import ipaddress
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import requests

from slskd_manager import get_data_dir

# Spotify OAuth endpoints
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_URL = "https://api.spotify.com/v1"

# Spotify app Client ID (PKCE auth - no secret needed)
CLIENT_ID = "fe284d9814144e1980cec22ef0c4ab47"
REDIRECT_URI = "https://127.0.0.1:8888/callback"
SCOPES = "user-library-read playlist-read-private playlist-read-collaborative"


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
        with open(path, 'r') as f:
            return json.load(f)
    return None


def save_token(token_data):
    """Save token to disk"""
    path = get_token_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(token_data, f)


def refresh_token(refresh_token_str):
    """Refresh an expired access token"""
    response = requests.post(SPOTIFY_TOKEN_URL, data={
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token_str,
        'client_id': CLIENT_ID
    })
    
    if response.status_code == 200:
        token_data = response.json()
        token_data['obtained_at'] = time.time()
        # Keep the refresh token if not returned
        if 'refresh_token' not in token_data:
            token_data['refresh_token'] = refresh_token_str
        save_token(token_data)
        return token_data
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
    """
    import ssl
    import tempfile
    
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
    
    # Start local server to catch callback
    server = HTTPServer(('127.0.0.1', 8888), CallbackHandler)
    server.auth_code = None
    server.auth_error = None
    server.timeout = 120  # 2 minute timeout
    
    # Create a self-signed certificate for HTTPS
    # This is needed because Spotify now requires https redirect URIs
    cert_pem, key_pem = generate_self_signed_cert()
    
    # Write cert and key to temp files
    cert_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
    cert_file.write(cert_pem)
    cert_file.close()
    
    key_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
    key_file.write(key_pem)
    key_file.close()
    
    try:
        # Wrap socket with SSL
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_file.name, key_file.name)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        
        # Open browser
        webbrowser.open(auth_url)
        
        # Wait for callback
        while server.auth_code is None and server.auth_error is None:
            server.handle_request()
        
        server.server_close()
    finally:
        # Clean up temp files
        os.unlink(cert_file.name)
        os.unlink(key_file.name)
    
    if server.auth_error:
        raise Exception(f"Spotify authorization failed: {server.auth_error}")
    
    if not server.auth_code:
        raise Exception("No authorization code received")
    
    # Exchange code for token
    token_response = requests.post(SPOTIFY_TOKEN_URL, data={
        'grant_type': 'authorization_code',
        'code': server.auth_code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'code_verifier': code_verifier
    })
    
    if token_response.status_code != 200:
        raise Exception(f"Failed to get token: {token_response.text}")
    
    token_data = token_response.json()
    token_data['obtained_at'] = time.time()
    
    # Save token
    save_token(token_data)
    
    return token_data


def generate_self_signed_cert():
    """Generate a self-signed certificate for localhost HTTPS"""
    from datetime import datetime, timedelta
    
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        # Fallback: use pre-generated cert (less secure but works)
        return get_fallback_cert()
    
    # Generate key
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # Generate certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
    ])
    
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(u"localhost"),
                x509.IPAddress(ipaddress.IPv4Address(u"127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256(), default_backend())
    )
    
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ).decode()
    
    return cert_pem, key_pem


def get_fallback_cert():
    """Return a pre-generated self-signed cert for localhost"""
    # This is a self-signed cert valid for localhost/127.0.0.1
    # Generated specifically for this application
    cert_pem = """-----BEGIN CERTIFICATE-----
MIIBkTCB+wIJAKHBfpegPjWAMA0GCSqGSIb3DQEBCwUAMBExDzANBgNVBAMMBmxv
Y2FsaDAeFw0yNDAxMDEwMDAwMDBaFw0yNTAxMDEwMDAwMDBaMBExDzANBgNVBAMM
BmxvY2FsMFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAMN0/fjaJNrOjwnVPwkfMzpS
NH8mM5NrJdPqWnHZBMbgVyWVcMNvLBJwKTLhWXpsN4vvsFmN7L4WEqkPy3prJCkC
AwEAAaNTMFEwHQYDVR0OBBYEFKpN9m1CPj2mN5xL3i5MgZLPHoF/MB8GA1UdIwQY
MBaAFKpN9m1CPj2mN5xL3i5MgZLPHoF/MA8GA1UdEwEB/wQFMAMBAf8wDQYJKoZI
hvcNAQELBQADQQAqm3IAhp1gfVCqFYqIDHAJwL6mGvXPs0wIvOzOzSBNiDXWMxnS
HzvXPKYLuEfqvnVZtqFXxPgdWm6k6gZvLh2n
-----END CERTIFICATE-----"""
    
    key_pem = """-----BEGIN RSA PRIVATE KEY-----
MIIBOgIBAAJBAMN0/fjaJNrOjwnVPwkfMzpSNH8mM5NrJdPqWnHZBMbgVyWVcMNv
LBJwKTLhWXpsN4vvsFmN7L4WEqkPy3prJCkCAwEAAQJAStpJblNAbJhCfvv6o7KH
HmqlQNlMOa4PKxTTQfYVtthyflJZBwWJdHDvRqLF0oTnHXCtPCtjreNGxYJLqRDN
gQIhAO0lyHpBkS0SCl1xH0y+QFn8xNQ3KLGdyPaUMbWYQiEZAiEA03fZPQvdFCvo
ELNk6w5pJP0PFmJn7pvAWLf8cqkqRVkCIBJgRLKFpo/JnyFyLdPV+fvyAAQQ2P+e
xL3hVIqOd3fRAiEAg7aVCAJdS0J23zTXiLNf8pYkJzMo4RWHLOzBRWti5LECID5b
bHBNjwqGhjLTQw1D3r8blMnPPohIrL0z5P3S2jDQ
-----END RSA PRIVATE KEY-----"""
    
    return cert_pem, key_pem


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
    """Simple Spotify API client"""
    
    def __init__(self, access_token):
        self.access_token = access_token
        self.headers = {'Authorization': f'Bearer {access_token}'}
    
    def _get(self, endpoint, params=None):
        """Make a GET request to Spotify API"""
        url = f"{SPOTIFY_API_URL}/{endpoint}"
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()
    
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
                except:
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
