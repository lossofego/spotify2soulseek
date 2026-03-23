"""
Import playlists from CSV (Exportify) or JSON files
"""

import os
import csv
import json
from rich.console import Console
from rich.progress import Progress

from slskd_manager import get_import_dir

console = Console()


def parse_exportify_csv(filepath):
    """Parse a CSV file exported from Exportify"""
    tracks = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # Handle various column names from Exportify
                name = (row.get('Track Name') or row.get('track_name') or 
                       row.get('name') or row.get('Name') or '')
                artist = (row.get('Artist Name(s)') or row.get('Artist Name') or 
                         row.get('artist') or row.get('Artist') or '')
                album = (row.get('Album Name') or row.get('album') or 
                        row.get('Album') or '')
                
                if not name or not artist:
                    continue
                
                # Handle multiple artists
                if ',' in artist:
                    artist = artist.split(',')[0].strip()
                
                tracks.append({
                    'name': name.strip(),
                    'artist': artist.strip(),
                    'album': album.strip(),
                    'duration_ms': 0
                })
    except Exception as e:
        console.print(f"[red]Error reading {filepath}: {e}[/red]")
        return []
    
    return tracks


def parse_json_file(filepath):
    """Parse a JSON file"""
    tracks = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get('tracks') or data.get('items') or []
            else:
                return []
            
            for item in items:
                if 'track' in item:
                    item = item['track']
                
                name = item.get('name') or item.get('trackName') or ''
                artist = item.get('artist') or item.get('artistName') or ''
                
                if isinstance(artist, dict):
                    artist = artist.get('name', '')
                elif isinstance(artist, list) and artist:
                    artist = artist[0].get('name', '') if isinstance(artist[0], dict) else str(artist[0])
                
                album = item.get('album') or item.get('albumName') or ''
                if isinstance(album, dict):
                    album = album.get('name', '')
                
                if not name or not artist:
                    continue
                
                tracks.append({
                    'name': str(name).strip(),
                    'artist': str(artist).strip(),
                    'album': str(album).strip(),
                    'duration_ms': item.get('duration_ms', 0)
                })
    except Exception as e:
        console.print(f"[red]Error reading {filepath}: {e}[/red]")
        return []
    
    return tracks


def scan_import_directory(import_dir=None):
    """Scan directory for CSV and JSON files"""
    if import_dir is None:
        import_dir = get_import_dir()
    
    files = []
    
    if not os.path.exists(import_dir):
        return files
    
    for filename in os.listdir(import_dir):
        filepath = os.path.join(import_dir, filename)
        if os.path.isfile(filepath):
            ext = os.path.splitext(filename)[1].lower()
            if ext in ['.csv', '.json']:
                files.append({
                    'filename': filename,
                    'filepath': filepath,
                    'type': ext[1:]
                })
    
    return files


def import_file(filepath):
    """Import a single file"""
    ext = os.path.splitext(filepath)[1].lower()
    
    if ext == '.csv':
        return parse_exportify_csv(filepath)
    elif ext == '.json':
        return parse_json_file(filepath)
    return []


def import_all_files(import_dir=None, data_dir=None):
    """Import all files from import directory"""
    from slskd_manager import get_data_dir
    
    if import_dir is None:
        import_dir = get_import_dir()
    if data_dir is None:
        data_dir = get_data_dir()
    
    output_liked = os.path.join(data_dir, 'liked_songs.json')
    output_playlists = os.path.join(data_dir, 'playlists.json')
    
    files = scan_import_directory(import_dir)
    
    if not files:
        console.print(f"[yellow]No CSV or JSON files found in:[/yellow]")
        console.print(f"  [cyan]{import_dir}[/cyan]")
        console.print("\n[dim]Export your playlists from https://exportify.net[/dim]")
        return False
    
    console.print(f"\n[bold]Found {len(files)} files to import[/bold]")
    
    all_tracks = []
    playlists = []
    
    with Progress() as progress:
        task = progress.add_task("Importing...", total=len(files))
        
        for f in files:
            tracks = import_file(f['filepath'])
            
            if tracks:
                playlist_name = os.path.splitext(f['filename'])[0]
                
                if 'liked' in playlist_name.lower() or 'saved' in playlist_name.lower():
                    all_tracks.extend(tracks)
                else:
                    playlists.append({
                        'name': playlist_name,
                        'id': playlist_name,
                        'total_tracks': len(tracks),
                        'tracks': tracks
                    })
                    all_tracks.extend(tracks)
            
            progress.advance(task)
    
    # Deduplicate
    seen = set()
    unique_tracks = []
    for track in all_tracks:
        key = f"{track['artist']} - {track['name']}".lower()
        if key not in seen:
            seen.add(key)
            unique_tracks.append(track)
    
    # Save
    with open(output_liked, 'w', encoding='utf-8') as f:
        json.dump(unique_tracks, f, indent=2, ensure_ascii=False)
    
    with open(output_playlists, 'w', encoding='utf-8') as f:
        json.dump(playlists, f, indent=2, ensure_ascii=False)
    
    console.print(f"\n[green]✓ Imported {len(unique_tracks)} unique tracks[/green]")
    console.print(f"[green]✓ Imported {len(playlists)} playlists[/green]")
    
    return True


def run_import():
    """Run the import process interactively"""
    from rich.prompt import Confirm
    from rich.panel import Panel
    import subprocess
    import platform
    
    import_dir = get_import_dir()
    
    console.print(Panel("[bold]Import from CSV/JSON[/bold]"))
    console.print(f"\nLooking for files in:\n  [cyan]{import_dir}[/cyan]\n")
    
    files = scan_import_directory(import_dir)
    
    if not files:
        console.print("[yellow]No files found.[/yellow]")
        console.print("\n[bold]How to get your Spotify playlists:[/bold]")
        console.print("\n  1. Go to [cyan]https://exportify.net[/cyan]")
        console.print("  2. Log in with your Spotify account")
        console.print("  3. Click 'Export' on playlists you want")
        console.print(f"  4. Move the downloaded CSVs to:\n     [green]{import_dir}[/green]")
        
        if Confirm.ask("\nOpen import folder?"):
            system = platform.system()
            if system == 'Windows':
                subprocess.run(['explorer', import_dir])
            elif system == 'Darwin':
                subprocess.run(['open', import_dir])
            else:
                subprocess.run(['xdg-open', import_dir])
        
        return False
    
    return import_all_files()
