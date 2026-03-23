#!/usr/bin/env python3
# spotify2slsk - download spotify playlists from soulseek

import json, os, re, shutil, signal, sys
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt, Confirm
from rich import box

from slskd_manager import (
    start_slskd, stop_slskd, is_slskd_running, is_slskd_installed,
    get_data_dir, get_download_dir, get_organized_dir, get_import_dir
)
from config import load_config, save_config, is_configured, validate_soulseek_username, generate_username, generate_password
from slskd_client import SlskdClient, SoulseekLoginError
from csv_import import run_import, import_all_files
from spotify_auth import (
    spotify_login, is_logged_in, logout, get_valid_token,
    SpotifyClient, fetch_spotify_library
)
from smart_search import generate_search_queries, score_result

# tray stuff (optional, might not be installed)
try:
    from tray import TrayIcon, show_notification, check_tray_support, check_notification_support
    TRAY_AVAILABLE = check_tray_support()
    NOTIFY_AVAILABLE = check_notification_support()
except ImportError:
    TRAY_AVAILABLE = False
    NOTIFY_AVAILABLE = False
    TrayIcon = None
    show_notification = lambda *a, **k: None

console = Console()
PREFERRED_FORMATS = ['.flac', '.mp3', '.ogg', '.m4a']
tray = None


def signal_handler(sig, frame):
    global tray
    console.print("\n[yellow]Shutting down...[/yellow]")
    if tray:
        tray.stop()
    stop_slskd()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


# file paths
def get_progress_file():
    return os.path.join(get_data_dir(), "progress.json")

def get_download_map_file():
    return os.path.join(get_data_dir(), "download_map.json")

def get_liked_songs_file():
    return os.path.join(get_data_dir(), "liked_songs.json")

def get_playlists_file():
    return os.path.join(get_data_dir(), "playlists.json")


# data persistence
def load_progress():
    p = get_progress_file()
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed": [], "skipped": [], "failed": []}

def save_progress(prog):
    with open(get_progress_file(), 'w', encoding='utf-8') as f:
        json.dump(prog, f, indent=2)

def load_download_map():
    p = get_download_map_file()
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_download_map(dm):
    with open(get_download_map_file(), 'w', encoding='utf-8') as f:
        json.dump(dm, f, indent=2, ensure_ascii=False)

def add_to_download_map(playlist, track_id, filename, artist, title):
    dm = load_download_map()
    if playlist not in dm:
        dm[playlist] = []
    dm[playlist].append({'track_id': track_id, 'filename': filename, 'artist': artist, 'title': title})
    save_download_map(dm)

def load_liked_songs():
    p = get_liked_songs_file()
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_liked_songs(songs):
    with open(get_liked_songs_file(), 'w', encoding='utf-8') as f:
        json.dump(songs, f, indent=2, ensure_ascii=False)

def load_playlists():
    p = get_playlists_file()
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_playlists(playlists):
    with open(get_playlists_file(), 'w', encoding='utf-8') as f:
        json.dump(playlists, f, indent=2, ensure_ascii=False)


# ui stuff
def show_banner():
    banner = """
  ┌─┐┌─┐┌─┐┌┬┐┬┌─┐┬ ┬┌─┐┌─┐┬  ┌─┐┬┌─
  └─┐├─┘│ │ │ │├┤ └┬┘┌─┘└─┐│  └─┐├┴┐
  └─┘┴  └─┘ ┴ ┴└   ┴ └─┘└─┘┴─┘└─┘┴ ┴
    """
    console.print(Panel(banner, subtitle="liberate your library", box=box.ROUNDED))


def show_status(liked_songs, playlists, progress, spotify_user=None, slskd_connected=False):
    spotify_status = f"[green]{spotify_user}[/green]" if spotify_user else "[dim]not connected[/dim]"
    slskd_status = "[green]Connected[/green]" if slskd_connected else "[dim]connecting...[/dim]"
    
    console.print(f"  Soulseek  {slskd_status}")
    
    # Library stats
    total_tracks = len(liked_songs) + sum(len(p['tracks']) for p in playlists)
    playlist_count = len(playlists)
    
    if total_tracks > 0:
        console.print(f"  Library   [cyan]{len(liked_songs)}[/cyan] liked + [cyan]{playlist_count}[/cyan] playlists ({total_tracks} tracks)")
    
    # Progress stats
    completed = len(progress['completed'])
    failed = len(progress['failed'])
    
    if completed > 0 or failed > 0:
        progress_str = f"  Progress  [green]{completed}[/green] downloaded"
        if failed > 0:
            progress_str += f", [red]{failed}[/red] failed"
        console.print(progress_str)


def show_playlists(playlists):
    table = Table(title="Your Playlists", box=box.ROUNDED)
    table.add_column("#", style="dim", width=4)
    table.add_column("Name", max_width=45)
    table.add_column("Tracks", justify="right")
    
    for i, p in enumerate(playlists):
        table.add_row(str(i + 1), p['name'][:45], str(len(p['tracks'])))
    
    console.print(table)


def show_menu(has_library=False, has_downloads=False, has_failed=False):
    """Show menu with context-aware options"""
    console.print("\n[bold]─── Menu ───[/bold]\n")
    
    # Import section
    if not has_library:
        console.print("  [bold cyan]1[/bold cyan]  Login with Spotify")
        console.print("  [bold cyan]2[/bold cyan]  Import from CSV files")
    else:
        console.print("  [bold cyan]1[/bold cyan]  Refresh Spotify library")
        console.print("  [bold cyan]2[/bold cyan]  Import more from CSV")
    
    # Download section
    console.print()
    if has_library:
        console.print("  [bold cyan]3[/bold cyan]  Download ALL")
        console.print("  [bold cyan]4[/bold cyan]  Download a playlist")
    else:
        console.print("  [dim]3  Download ALL (import library first)[/dim]")
        console.print("  [dim]4  Download a playlist[/dim]")
    
    if has_failed:
        console.print("  [bold cyan]5[/bold cyan]  Retry failed tracks [yellow]◀[/yellow]")
    else:
        console.print("  [dim]5  Retry failed tracks[/dim]")
    
    # Output section
    console.print()
    if has_downloads:
        console.print("  [bold cyan]6[/bold cyan]  Organize into folders")
    else:
        console.print("  [dim]6  Organize into folders[/dim]")
    console.print("  [bold cyan]7[/bold cyan]  Open folders")
    
    # Utility section
    console.print()
    console.print("  [bold cyan]s[/bold cyan]  Settings")
    console.print("  [bold cyan]q[/bold cyan]  Quit")
    console.print()


# spotify stuff
def do_spotify_login():
    console.print("\n[bold]Connecting to Spotify...[/bold]")
    console.print("[dim]A browser window will open for you to log in.[/dim]\n")
    
    try:
        token = spotify_login()
        client = SpotifyClient(token['access_token'])
        user = client.get_current_user()
        console.print(f"[green]✓ Logged in as {user['display_name']}[/green]")
        return user['display_name']
    except Exception as e:
        console.print(f"[red]Login failed: {e}[/red]")
        return None


def fetch_library_from_spotify():
    console.print("\n[bold]Fetching your Spotify library...[/bold]\n")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as prog:
        task = prog.add_task("Fetching liked songs...", total=None)
        
        token = get_valid_token()
        client = SpotifyClient(token['access_token'])
        
        def liked_cb(cur, tot):
            prog.update(task, completed=cur, total=tot, description=f"Liked songs: {cur}/{tot}")
        
        liked = client.get_liked_songs(progress_callback=liked_cb)
        save_liked_songs(liked)
        console.print(f"[green]✓ {len(liked)} liked songs[/green]")
        
        prog.update(task, description="Fetching playlists...", completed=0, total=None)
        
        def playlist_cb(cur, tot, name):
            prog.update(task, completed=cur, total=tot, description=f"Playlist {cur}/{tot}: {name[:30]}")
        
        playlists = client.get_playlists(progress_callback=playlist_cb)
        save_playlists(playlists)
        
        n_tracks = sum(len(p['tracks']) for p in playlists)
        console.print(f"[green]✓ {len(playlists)} playlists ({n_tracks} tracks)[/green]")
    
    return liked, playlists


def get_spotify_user():
    if is_logged_in():
        try:
            token = get_valid_token()
            client = SpotifyClient(token['access_token'])
            return client.get_current_user()['display_name']
        except:
            pass
    return None


# soulseek setup
def setup_soulseek_credentials(config):
    """
    Setup Soulseek credentials with auto-generation option.
    Uses the config module's setup_wizard for first-time setup.
    """
    from config import setup_wizard, is_configured
    
    if not is_configured():
        # Run the setup wizard which handles auto-generation
        config = setup_wizard()
    
    return config


def start_soulseek(config):
    """
    Start Soulseek and return connected client.
    
    Handles:
    - Downloading slskd if needed
    - Starting slskd process
    - Connecting to Soulseek network
    - Detecting login errors (wrong password, invalid username)
    - Auto-registration for new accounts
    
    Raises:
        SoulseekLoginError: If login fails (wrong password, invalid username, etc.)
        Exception: For other errors
    """
    from slskd_client import SoulseekLoginError
    
    console.print("\n[dim]Starting Soulseek...[/dim]")
    
    # Start slskd process
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        task = progress.add_task("Initializing...", total=None)
        
        def update(msg):
            progress.update(task, description=msg)
        
        try:
            start_slskd(config['soulseek_username'], config['soulseek_password'], progress_callback=update)
        except Exception as e:
            raise Exception(f"Failed to start Soulseek client: {e}")
    
    # Connect to slskd API
    client = SlskdClient()
    client.connect()
    
    console.print("[dim]Connecting to Soulseek network...[/dim]")
    console.print(f"[dim]Username: {config['soulseek_username']}[/dim]")
    
    # Wait for Soulseek connection with proper error handling
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        task = progress.add_task("Connecting...", total=None)
        
        def update(msg):
            progress.update(task, description=msg)
        
        try:
            connected = client.wait_for_soulseek_connection(timeout=45, progress_callback=update)
        except SoulseekLoginError as e:
            # Re-raise with more context
            raise e
    
    if connected:
        console.print("[green]✓ Connected to Soulseek![/green]")
        # Check if this was a new account (account is created on first successful login)
        state = client.get_soulseek_state()
        if state.get("username"):
            console.print(f"[dim]Logged in as: {state['username']}[/dim]")
    else:
        console.print("[yellow]Warning: Connection is taking longer than expected...[/yellow]")
        console.print("[dim]The network might be slow. Downloads may still work.[/dim]")
    
    return client


def handle_login_error(error, config):
    """
    Handle Soulseek login errors with appropriate user guidance.
    
    Returns:
        tuple: (should_retry: bool, updated_config: dict)
    """
    from config import generate_username, generate_password, validate_soulseek_username, save_config
    from slskd_client import SoulseekLoginError
    
    if not isinstance(error, SoulseekLoginError):
        console.print(f"\n[red]Error: {error}[/red]")
        return False, config
    
    console.print(f"\n[red]Login failed: {error.reason}[/red]")
    
    if error.reason == "INVALIDPASS":
        # Username exists but password is wrong
        console.print("\n[yellow]This username already exists and the password is incorrect.[/yellow]")
        console.print("\nOptions:")
        console.print("  1. Enter the correct password for this account")
        console.print("  2. Try a different username")
        console.print("  3. Generate a new random account")
        
        choice = Prompt.ask("Choice", choices=["1", "2", "3"], default="3")
        
        if choice == "1":
            config['soulseek_password'] = Prompt.ask("Password", password=True)
            save_config(config)
            return True, config
        elif choice == "2":
            while True:
                username = Prompt.ask("New username")
                valid, err = validate_soulseek_username(username)
                if valid:
                    config['soulseek_username'] = username
                    config['soulseek_password'] = Prompt.ask("Password", password=True)
                    break
                console.print(f"[red]{err}[/red]")
            save_config(config)
            return True, config
        else:
            config['soulseek_username'] = generate_username()
            config['soulseek_password'] = generate_password()
            console.print(f"\n[green]Generated new account:[/green]")
            console.print(f"  Username: [cyan]{config['soulseek_username']}[/cyan]")
            console.print(f"  Password: [cyan]{config['soulseek_password']}[/cyan]")
            save_config(config)
            return True, config
    
    elif error.reason == "INVALIDUSERNAME":
        console.print(f"\n[yellow]Invalid username format.[/yellow]")
        if error.detail:
            console.print(f"[dim]{error.detail}[/dim]")
        
        console.print("\nOptions:")
        console.print("  1. Enter a valid username")
        console.print("  2. Generate a random account")
        
        choice = Prompt.ask("Choice", choices=["1", "2"], default="2")
        
        if choice == "1":
            while True:
                username = Prompt.ask("Username")
                valid, err = validate_soulseek_username(username)
                if valid:
                    config['soulseek_username'] = username
                    break
                console.print(f"[red]{err}[/red]")
            config['soulseek_password'] = Prompt.ask("Password", password=True)
        else:
            config['soulseek_username'] = generate_username()
            config['soulseek_password'] = generate_password()
            console.print(f"\n[green]Generated new account:[/green]")
            console.print(f"  Username: [cyan]{config['soulseek_username']}[/cyan]")
            console.print(f"  Password: [cyan]{config['soulseek_password']}[/cyan]")
        
        save_config(config)
        return True, config
    
    elif error.reason == "SVRFULL":
        console.print("\n[yellow]The Soulseek server is currently full.[/yellow]")
        console.print("Please try again later.")
        return False, config
    
    elif error.reason == "SVRPRIVATE":
        console.print("\n[yellow]The server is not accepting new registrations.[/yellow]")
        console.print("You'll need to use an existing Soulseek account.")
        
        if Confirm.ask("Enter existing account credentials?"):
            config['soulseek_username'] = Prompt.ask("Username")
            config['soulseek_password'] = Prompt.ask("Password", password=True)
            save_config(config)
            return True, config
        return False, config
    
    else:
        # Unknown error
        if Confirm.ask("Try again with different credentials?"):
            config['soulseek_username'] = Prompt.ask("Username")
            config['soulseek_password'] = Prompt.ask("Password", password=True)
            save_config(config)
            return True, config
        return False, config


# search & filtering
def filter_results(responses, config):
    results = []
    min_br = config.get('min_bitrate', 192)
    prefer_lossless = config.get('format_preference', 'mp3') == 'lossless'
    
    for resp in responses:
        user = resp['username']
        speed = resp.get('uploadSpeed', 0)
        
        for f in resp.get('files', []):
            fname = f.get('filename', '')
            if '.' not in fname:
                continue
            
            ext = fname[fname.rfind('.'):].lower()
            if ext not in PREFERRED_FORMATS:
                continue
            
            br = f.get('bitRate', 0) or 0
            size = f.get('size', 0) / 1024 / 1024
            
            # skip low quality mp3s
            if ext == '.mp3' and 0 < br < min_br:
                continue
            
            results.append({
                'username': user,
                'file_obj': f,
                'filename': fname,
                'displayname': fname.split('\\')[-1],
                'bitrate': br,
                'size_mb': round(size, 1),
                'ext': ext,
                'speed': speed
            })
    
    # sort based on preference
    if prefer_lossless:
        # flac first, then high bitrate mp3, then speed
        results.sort(key=lambda x: (x['ext'] != '.flac', x['ext'] != '.wav', -(x['bitrate'] or 9999), -x['speed']))
    else:
        # high bitrate mp3 first, then flac (as backup), then speed
        # mp3 320 > mp3 256 > mp3 192 > flac > lower mp3
        def mp3_score(r):
            if r['ext'] == '.mp3':
                br = r['bitrate'] or 256  # unknown = assume decent
                if br >= 320: return 0
                if br >= 256: return 1
                if br >= 192: return 2
                return 5
            elif r['ext'] in ['.flac', '.wav']:
                return 3  # lossless as fallback
            return 4
        results.sort(key=lambda x: (mp3_score(x), -(x['bitrate'] or 9999), -x['speed']))
    
    return results[:10]


def is_good_match(c, config):
    min_sz = config.get('auto_accept_min_size_mb', 3)
    max_sz = config.get('auto_accept_max_size_mb', 200)
    prefer_lossless = config.get('format_preference', 'mp3') == 'lossless'
    
    if c['size_mb'] < min_sz or c['size_mb'] > max_sz:
        return False
    
    if prefer_lossless:
        # lossless mode: accept flac/wav, or high quality mp3
        if c['ext'] in ['.flac', '.wav']:
            return True
        if c['ext'] == '.mp3' and (c['bitrate'] >= 256 or c['bitrate'] == 0):
            return True
    else:
        # mp3 mode: prefer mp3, accept lossless as fallback
        if c['ext'] == '.mp3' and (c['bitrate'] >= 192 or c['bitrate'] == 0):
            return True
        if c['ext'] in ['.flac', '.wav']:  # accept lossless if no good mp3
            return True
    
    return False


# file organization
def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def find_file_in_downloads(dl_dir, filename):
    target = filename.split('\\')[-1]
    for root, dirs, files in os.walk(dl_dir):
        for f in files:
            if f == target:
                return os.path.join(root, f)
    return None


def get_desktop_path():
    if sys.platform == 'win32':
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
            desktop = winreg.QueryValueEx(key, "Desktop")[0]
            winreg.CloseKey(key)
            return desktop
        except:
            pass
        # Fallback
        return os.path.join(os.path.expanduser("~"), "Desktop")
    else:
        return os.path.join(os.path.expanduser("~"), "Desktop")


def organize_downloads():
    download_map = load_download_map()
    download_dir = get_download_dir()
    
    if not download_map:
        console.print("[yellow]No downloads to organize yet.[/yellow]")
        return
    
    # Ask where to save
    console.print("\n[bold]Where to save organized files?[/bold]")
    console.print(f"  [bold]1[/bold] = Desktop")
    console.print(f"  [bold]2[/bold] = Default ({get_organized_dir()})")
    
    choice = Prompt.ask("Choice", choices=["1", "2"], default="1")
    
    if choice == "1":
        desktop = get_desktop_path()
        organized_dir = os.path.join(desktop, "spotify2slsk Music")
    else:
        organized_dir = get_organized_dir()
    
    os.makedirs(organized_dir, exist_ok=True)
    console.print(f"\n[bold]Organizing into:[/bold] {organized_dir}\n")
    
    total_found = 0
    total_missing = 0
    
    with Progress() as progress:
        task = progress.add_task("[cyan]Organizing...", total=len(download_map))
        
        for playlist_name, tracks in download_map.items():
            safe_name = sanitize_filename(playlist_name)
            playlist_dir = os.path.join(organized_dir, safe_name)
            os.makedirs(playlist_dir, exist_ok=True)
            
            playlist_entries = []
            
            for track in tracks:
                source = find_file_in_downloads(download_dir, track['filename'])
                
                if source:
                    ext = os.path.splitext(source)[1]
                    nice_name = sanitize_filename(f"{track['artist']} - {track['title']}{ext}")
                    dest = os.path.join(playlist_dir, nice_name)
                    
                    if not os.path.exists(dest):
                        shutil.copy2(source, dest)
                    
                    playlist_entries.append(nice_name)
                    total_found += 1
                else:
                    total_missing += 1
            
            m3u_path = os.path.join(playlist_dir, f"{safe_name}.m3u")
            with open(m3u_path, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                for entry in playlist_entries:
                    f.write(f"{entry}\n")
            
            progress.advance(task)
    
    console.print(f"\n[green]✓ Done![/green] {total_found} files organized to:")
    console.print(f"   [bold]{organized_dir}[/bold]")


# === PROCESSING ===
def process_tracks(client, config, tracks, source_name, auto_mode=True):
    global tray
    progress_data = load_progress()
    timeout = config.get('search_timeout', 90)
    completed_set = set(progress_data['completed'])
    
    remaining = [t for t in tracks 
                 if f"{t['artist']} - {t['name']}" not in progress_data['completed']
                 and f"{t['artist']} - {t['name']}" not in progress_data['skipped']]
    
    if not remaining:
        console.print("[green]All tracks already processed![/green]")
        return
    
    total = len(remaining)
    queued = 0
    failed = 0
    
    # Update tray with initial status
    if tray:
        tray.update(status=f"Downloading: {source_name}", total=total, downloaded=0, failed=0)
    
    console.print(Panel(f"[bold]{source_name}[/bold]\n{total} tracks", box=box.ROUNDED))
    
    for i, song in enumerate(remaining):
        artist = song['artist']
        title = song['name']
        track_id = f"{artist} - {title}"
        
        if track_id in completed_set:
            continue
        
        # Update tray with current track
        if tray:
            tray.update(current=f"{artist} - {title}", downloaded=queued, failed=failed)
        
        console.print(f"\n[bold][{i+1}/{total}][/bold] {artist} - {title}")
        
        # Generate multiple search queries
        queries = generate_search_queries(artist, title)
        all_candidates = []
        
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as prog:
            task = prog.add_task("Searching...", total=None)
            
            for query_num, query in enumerate(queries):
                def update(files, users, secs, complete):
                    status = "✓" if complete else f"{secs}s"
                    q_info = f"[{query_num+1}/{len(queries)}]" if len(queries) > 1 else ""
                    prog.update(task, description=f"Searching{q_info}... {files} files ({status})")
                
                # Use shorter timeout for alternate queries
                q_timeout = timeout if query_num == 0 else min(timeout, 30)
                responses = client.search(query, timeout=q_timeout, progress_callback=update)
                candidates = filter_results(responses, config)
                
                if candidates:
                    # Score each candidate based on how well it matches
                    for c in candidates:
                        c['match_score'] = score_result(c['filename'], artist, title)
                    all_candidates.extend(candidates)
                    
                    # If we found good matches on first query, don't try more
                    if query_num == 0 and any(c['match_score'] > 50 for c in candidates):
                        break
                
                # If we have enough candidates, stop searching
                if len(all_candidates) >= 20:
                    break
        
        # Sort by match score, then by our preference (format, bitrate, etc)
        if all_candidates:
            # Deduplicate by filename
            seen_files = set()
            unique_candidates = []
            for c in all_candidates:
                if c['filename'] not in seen_files:
                    seen_files.add(c['filename'])
                    unique_candidates.append(c)
            
            # Sort: high match score first, then by quality
            unique_candidates.sort(key=lambda x: (-x.get('match_score', 0), -x.get('score', 0)))
            candidates = unique_candidates
        else:
            candidates = []
        
        if not candidates:
            console.print("  [red]No results[/red]")
            progress_data['failed'].append(track_id)
            save_progress(progress_data)
            failed += 1
            if tray:
                tray.update(failed=failed)
            continue
        
        if auto_mode:
            if is_good_match(candidates[0], config):
                c = candidates[0]
                if client.queue_download(c['username'], c['file_obj']):
                    console.print(f"  [green]✓[/green] {c['displayname'][:50]} ({c['ext'][1:].upper()}, {c['size_mb']}MB)")
                    progress_data['completed'].append(track_id)
                    completed_set.add(track_id)
                    save_progress(progress_data)
                    add_to_download_map(source_name, track_id, c['filename'], artist, title)
                    queued += 1
                    if tray:
                        tray.update(downloaded=queued)
                else:
                    console.print("  [red]Queue failed[/red]")
                    progress_data['failed'].append(track_id)
                    save_progress(progress_data)
                    failed += 1
                    if tray:
                        tray.update(failed=failed)
            else:
                console.print("  [yellow]No good match[/yellow]")
                progress_data['failed'].append(track_id)
                save_progress(progress_data)
                failed += 1
                if tray:
                    tray.update(failed=failed)
        else:
            table = Table(show_header=True, box=box.SIMPLE)
            table.add_column("#", width=2)
            table.add_column("Type", width=5)
            table.add_column("File", max_width=45)
            table.add_column("Size", width=8)
            
            for j, c in enumerate(candidates):
                table.add_row(str(j+1), c['ext'][1:].upper(), c['displayname'][:45], f"{c['size_mb']}MB")
            
            console.print(table)
            
            choice = Prompt.ask("Choice (1-10/[s]kip/[q]uit)", default="1")
            
            if choice == 'q':
                break
            elif choice == 's':
                progress_data['skipped'].append(track_id)
                save_progress(progress_data)
            elif choice.isdigit() and 0 < int(choice) <= len(candidates):
                c = candidates[int(choice) - 1]
                if client.queue_download(c['username'], c['file_obj']):
                    console.print(f"  [green]✓ Queued[/green]")
                    progress_data['completed'].append(track_id)
                    completed_set.add(track_id)
                    save_progress(progress_data)
                    add_to_download_map(source_name, track_id, c['filename'], artist, title)
                    queued += 1
    
    console.print(f"\n[bold]Summary:[/bold] Queued {queued}, Failed {failed}")
    
    # Update tray and send notification
    if tray:
        tray.update(status="Idle", current="")
        if NOTIFY_AVAILABLE:
            show_notification(
                f"Finished: {source_name}",
                f"Queued {queued} tracks, {failed} failed"
            )


def process_all(client, config, liked_songs, playlists):
    """Process entire library"""
    global tray
    console.print(Panel("[bold]Downloading entire library[/bold]", box=box.ROUNDED))
    
    total_tracks = len(liked_songs) + sum(len(p['tracks']) for p in playlists)
    console.print(f"Total: {total_tracks} tracks across {len(playlists) + 1} collections\n")
    
    if not Confirm.ask("Start downloading?"):
        return
    
    total_queued = 0
    total_failed = 0
    
    if liked_songs:
        console.print("\n[bold cyan]═══ Liked Songs ═══[/bold cyan]")
        process_tracks(client, config, liked_songs, "Liked Songs", auto_mode=True)
    
    for i, playlist in enumerate(playlists):
        console.print(f"\n[bold cyan]═══ [{i+1}/{len(playlists)}] {playlist['name']} ═══[/bold cyan]")
        if playlist['tracks']:
            process_tracks(client, config, playlist['tracks'], playlist['name'], auto_mode=True)
    
    console.print("\n[bold green]✓ All done![/bold green]")
    
    # Final notification
    if tray and NOTIFY_AVAILABLE:
        show_notification(
            "Library Download Complete",
            f"Processed {total_tracks} tracks from {len(playlists) + 1} collections"
        )


# settings
def show_settings(config):
    console.print("\n[bold]─── Settings ───[/bold]\n")
    
    console.print(f"  Soulseek user   [cyan]{config.get('soulseek_username', '[not set]')}[/cyan]")
    console.print(f"  Search timeout  [cyan]{config.get('search_timeout', 90)}s[/cyan]")
    console.print(f"  Min bitrate     [cyan]{config.get('min_bitrate', 192)}kbps[/cyan]")
    
    # format preference display
    fmt = config.get('format_preference', 'mp3')
    if fmt == 'lossless':
        fmt_display = "[cyan]Lossless (FLAC)[/cyan]"
    else:
        fmt_display = "[cyan]MP3 (320kbps)[/cyan]"
    console.print(f"  Format          {fmt_display}")
    console.print()
    
    spotify_user = get_spotify_user()
    if spotify_user:
        console.print(f"  Spotify         [green]{spotify_user}[/green]")
    else:
        console.print(f"  Spotify         [dim]Not connected[/dim]")
    
    tray_status = "[green]On[/green]" if TRAY_AVAILABLE else "[dim]Off[/dim]"
    notify_status = "[green]On[/green]" if NOTIFY_AVAILABLE else "[dim]Off[/dim]"
    console.print(f"  System tray     {tray_status}")
    console.print(f"  Notifications   {notify_status}")
    console.print()
    
    console.print(f"  [dim]Downloads: {get_download_dir()}[/dim]")
    console.print()
    
    # options
    console.print("  [bold cyan]1[/bold cyan]  Edit settings")
    console.print("  [bold cyan]2[/bold cyan]  Toggle format (MP3 ↔ Lossless)")
    if spotify_user:
        console.print("  [bold cyan]3[/bold cyan]  Log out of Spotify")
    console.print("  [bold cyan]c[/bold cyan]  Back to menu")
    
    choice = Prompt.ask("\nChoice", default="c").strip().lower()
    
    if choice == "1":
        new_user = Prompt.ask("Soulseek username", default=config.get('soulseek_username', ''))
        if new_user != config.get('soulseek_username'):
            config['soulseek_username'] = new_user
            config['soulseek_password'] = Prompt.ask("Soulseek password", password=True)
        
        timeout = Prompt.ask("Search timeout (seconds)", default=str(config.get('search_timeout', 90)))
        config['search_timeout'] = int(timeout) if timeout.isdigit() else 90
        
        bitrate = Prompt.ask("Min bitrate (kbps)", default=str(config.get('min_bitrate', 192)))
        config['min_bitrate'] = int(bitrate) if bitrate.isdigit() else 192
        
        save_config(config)
        console.print("[green]✓ Saved[/green]")
        console.print("[yellow]Restart to apply Soulseek credential changes[/yellow]")
    
    elif choice == "2":
        current = config.get('format_preference', 'mp3')
        if current == 'mp3':
            config['format_preference'] = 'lossless'
            console.print("[green]✓ Switched to Lossless (FLAC/WAV)[/green]")
            console.print("[dim]Will prefer FLAC, fall back to high-quality MP3[/dim]")
        else:
            config['format_preference'] = 'mp3'
            console.print("[green]✓ Switched to MP3 (320kbps preferred)[/green]")
            console.print("[dim]Will prefer 320kbps MP3, fall back to lossless[/dim]")
        save_config(config)
    
    elif choice == "3" and spotify_user:
        if Confirm.ask(f"Log out of Spotify ({spotify_user})?", default=False):
            logout()
            console.print("[green]✓ Logged out of Spotify[/green]")
            console.print("[dim]Use option 1 from the menu to log in with a different account[/dim]")
    
    return config


def open_folders():
    import subprocess
    import platform
    
    console.print("\n[bold]Folders:[/bold]")
    console.print(f"  1. Downloads:  {get_download_dir()}")
    console.print(f"  2. Organized:  {get_organized_dir()}")
    console.print(f"  3. CSV Import: {get_import_dir()}")
    
    choice = Prompt.ask("\nOpen", choices=["1", "2", "3", "c"], default="c")
    
    if choice == "c":
        return
    
    folders = [get_download_dir(), get_organized_dir(), get_import_dir()]
    folder = folders[int(choice) - 1]
    
    system = platform.system()
    if system == 'Windows':
        subprocess.run(['explorer', folder])
    elif system == 'Darwin':
        subprocess.run(['open', folder])
    else:
        subprocess.run(['xdg-open', folder])


# === MAIN ===
def main():
    global tray
    from slskd_client import SoulseekLoginError
    from config import validate_soulseek_username, generate_username, generate_password
    
    console.clear()
    show_banner()
    
    # Initialize system tray if available
    if TRAY_AVAILABLE:
        tray = TrayIcon(
            on_show=lambda: console.print("\n[dim]Window focused[/dim]"),
            on_quit=lambda: signal_handler(None, None)
        )
        if tray.start():
            console.print("[dim]System tray enabled[/dim]")
        else:
            tray = None
    
    # Load or create configuration
    config = load_config()
    config = setup_soulseek_credentials(config)
    
    # Connection retry loop
    max_retries = 3
    retry_count = 0
    client = None
    
    while retry_count < max_retries:
        try:
            client = start_soulseek(config)
            break  # Success!
        except SoulseekLoginError as e:
            retry_count += 1
            should_retry, config = handle_login_error(e, config)
            if not should_retry:
                if tray:
                    tray.stop()
                stop_slskd()
                return
            if retry_count >= max_retries:
                console.print(f"\n[red]Too many failed attempts. Please restart the app.[/red]")
                if tray:
                    tray.stop()
                stop_slskd()
                return
            console.print(f"\n[dim]Retrying... ({retry_count}/{max_retries})[/dim]")
            stop_slskd()  # Stop before retry
            import time
            time.sleep(2)
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            if Confirm.ask("Re-enter Soulseek credentials?"):
                config['soulseek_username'] = Prompt.ask("Soulseek username")
                config['soulseek_password'] = Prompt.ask("Soulseek password", password=True)
                save_config(config)
                console.print("[yellow]Please restart the app.[/yellow]")
            if tray:
                tray.stop()
            stop_slskd()
            return
    
    if client is None:
        console.print("[red]Failed to connect. Please restart the app.[/red]")
        stop_slskd()
        return
    
    # Load saved data
    liked_songs = load_liked_songs()
    playlists = load_playlists()
    progress_data = load_progress()
    spotify_user = get_spotify_user()
    
    # Show current status
    show_status(liked_songs, playlists, progress_data, spotify_user, client.is_connected_to_soulseek())
    
    # Main menu loop
    while True:
        has_library = len(liked_songs) > 0 or len(playlists) > 0
        has_downloads = len(progress_data['completed']) > 0
        has_failed = len(progress_data['failed']) > 0
        show_menu(has_library, has_downloads, has_failed)
        choice = Prompt.ask("Choice", default="q").strip().lower()
        
        if choice == '1':
            if is_logged_in():
                liked_songs, playlists = fetch_library_from_spotify()
            else:
                if do_spotify_login():
                    liked_songs, playlists = fetch_library_from_spotify()
            spotify_user = get_spotify_user()
            show_status(liked_songs, playlists, load_progress(), spotify_user, client.is_connected_to_soulseek())
        
        elif choice == '2':
            run_import()
            liked_songs = load_liked_songs()
            playlists = load_playlists()
            show_status(liked_songs, playlists, load_progress(), spotify_user, client.is_connected_to_soulseek())
        
        elif choice == '3':
            if not liked_songs and not playlists:
                console.print("[yellow]No library. Use option 1 or 2 first.[/yellow]")
            else:
                process_all(client, config, liked_songs, playlists)
                progress_data = load_progress()  # Refresh for menu
        
        elif choice == '4':
            if not playlists and not liked_songs:
                console.print("[yellow]No playlists. Import first.[/yellow]")
            else:
                if liked_songs:
                    console.print(f"  0. Liked Songs ({len(liked_songs)} tracks)")
                show_playlists(playlists)
                idx = Prompt.ask("Playlist number")
                if idx == '0' and liked_songs:
                    process_tracks(client, config, liked_songs, "Liked Songs", auto_mode=True)
                    progress_data = load_progress()
                elif idx.isdigit() and 0 < int(idx) <= len(playlists):
                    p = playlists[int(idx) - 1]
                    process_tracks(client, config, p['tracks'], p['name'], auto_mode=True)
                    progress_data = load_progress()
        
        elif choice == '5':
            progress_data = load_progress()
            failed = []
            for tid in progress_data['failed']:
                parts = tid.split(' - ', 1)
                if len(parts) == 2:
                    failed.append({'artist': parts[0], 'name': parts[1]})
            if failed:
                console.print(f"\n[bold]{len(failed)} failed tracks[/bold]")
                progress_data['failed'] = []
                save_progress(progress_data)
                process_tracks(client, config, failed, "Failed Tracks", auto_mode=False)
                progress_data = load_progress()
            else:
                console.print("[green]No failed tracks![/green]")
        
        elif choice == '6':
            organize_downloads()
        
        elif choice == '7':
            open_folders()
        
        elif choice == 's':
            config = show_settings(config)
        
        elif choice == 'q':
            console.print("\n[dim]Shutting down...[/dim]")
            if tray:
                tray.stop()
            stop_slskd()
            console.print("[bold]Goodbye![/bold]\n")
            break


if __name__ == "__main__":
    main()
