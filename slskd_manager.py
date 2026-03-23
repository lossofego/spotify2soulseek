"""
slskd Manager - Automatically download and manage slskd
"""

import os
import sys
import platform
import subprocess
import time
import zipfile
import tarfile
import shutil
import signal
import atexit
import requests
from pathlib import Path

# slskd release info
SLSKD_VERSION = "0.21.4"
SLSKD_RELEASES = {
    "Windows": {
        "url": f"https://github.com/slskd/slskd/releases/download/{SLSKD_VERSION}/slskd-{SLSKD_VERSION}-win-x64.zip",
        "executable": "slskd.exe",
        "archive_type": "zip"
    },
    "Darwin": {  # macOS
        "url": f"https://github.com/slskd/slskd/releases/download/{SLSKD_VERSION}/slskd-{SLSKD_VERSION}-osx-x64.tar.gz",
        "executable": "slskd",
        "archive_type": "tar.gz"
    },
    "Linux": {
        "url": f"https://github.com/slskd/slskd/releases/download/{SLSKD_VERSION}/slskd-{SLSKD_VERSION}-linux-x64.tar.gz",
        "executable": "slskd",
        "archive_type": "tar.gz"
    }
}

# Global process reference
slskd_process = None


def get_app_dir():
    """Get the application directory"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        # Use the directory where the exe is located
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))


def get_slskd_app_dir():
    """Get directory for slskd binary - always in user data, not exe dir"""
    # Store slskd in user data dir so it persists and doesn't need admin rights
    return os.path.join(get_data_dir(), "slskd_bin")


def get_slskd_dir():
    """Get the slskd installation directory"""
    return get_slskd_app_dir()


def get_data_dir():
    """Get the data directory for downloads, etc."""
    system = platform.system()
    if system == "Windows":
        base = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'spotify2slsk')
    else:
        base = os.path.join(os.path.expanduser('~'), '.spotify2slsk')
    
    os.makedirs(base, exist_ok=True)
    return base


def get_download_dir():
    """Get the downloads directory"""
    d = os.path.join(get_data_dir(), "downloads")
    os.makedirs(d, exist_ok=True)
    return d


def get_organized_dir():
    """Get the organized output directory"""
    d = os.path.join(get_data_dir(), "organized")
    os.makedirs(d, exist_ok=True)
    return d


def get_import_dir():
    """Get the import directory for CSVs"""
    d = os.path.join(get_data_dir(), "import")
    os.makedirs(d, exist_ok=True)
    return d


def get_slskd_executable():
    """Get path to slskd executable"""
    system = platform.system()
    if system not in SLSKD_RELEASES:
        raise Exception(f"Unsupported platform: {system}")
    
    info = SLSKD_RELEASES[system]
    return os.path.join(get_slskd_dir(), info["executable"])


def is_slskd_installed():
    """Check if slskd is already downloaded"""
    exe_path = get_slskd_executable()
    return os.path.exists(exe_path)


def download_slskd(progress_callback=None):
    """Download slskd for the current platform"""
    system = platform.system()
    if system not in SLSKD_RELEASES:
        raise Exception(f"Unsupported platform: {system}")
    
    info = SLSKD_RELEASES[system]
    url = info["url"]
    archive_type = info["archive_type"]
    
    slskd_dir = get_slskd_dir()
    os.makedirs(slskd_dir, exist_ok=True)
    
    # Download
    if progress_callback:
        progress_callback("Downloading slskd...")
    
    archive_path = os.path.join(slskd_dir, f"slskd.{archive_type}")
    
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise Exception("No internet connection. Please check your network and try again.")
    except requests.exceptions.Timeout:
        raise Exception("Download timed out. Please check your connection and try again.")
    except requests.exceptions.HTTPError as e:
        raise Exception(f"Download failed: {e}")
    
    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0
    
    try:
        with open(archive_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total_size > 0:
                    pct = int(downloaded / total_size * 100)
                    progress_callback(f"Downloading slskd... {pct}%")
    except IOError as e:
        raise Exception(f"Failed to save download (disk full?): {e}")
    
    # Extract
    if progress_callback:
        progress_callback("Extracting...")
    
    if archive_type == "zip":
        with zipfile.ZipFile(archive_path, 'r') as z:
            z.extractall(slskd_dir)
    else:  # tar.gz
        with tarfile.open(archive_path, 'r:gz') as t:
            t.extractall(slskd_dir)
    
    # Clean up archive
    os.remove(archive_path)
    
    # Make executable on Unix
    if system != "Windows":
        exe_path = get_slskd_executable()
        os.chmod(exe_path, 0o755)
    
    if progress_callback:
        progress_callback("slskd installed!")
    
    return True


def create_slskd_config(soulseek_username, soulseek_password, web_port=5030):
    """Create slskd configuration file"""
    slskd_dir = get_slskd_dir()
    config_path = os.path.join(slskd_dir, "slskd.yml")
    
    download_dir = get_download_dir()
    
    # Ensure forward slashes for YAML
    download_dir_yaml = download_dir.replace("\\", "/")
    
    config = f"""# slskd configuration - auto-generated by spotify2slsk
web:
  port: {web_port}
  authentication:
    username: slskd
    password: slskd

soulseek:
  username: {soulseek_username}
  password: {soulseek_password}
  description: spotify2slsk user
  
directories:
  downloads: {download_dir_yaml}

shares:
  directories: []

flags:
  no_logo: true
  no_version_check: true

logger:
  console: false
"""
    
    with open(config_path, 'w') as f:
        f.write(config)
    
    return config_path


def is_slskd_running(port=5030):
    """Check if slskd is already running"""
    try:
        response = requests.get(f"http://localhost:{port}/api/v0/application", timeout=2)
        return response.status_code in [200, 401]
    except:
        return False


def start_slskd(soulseek_username, soulseek_password, web_port=5030, progress_callback=None):
    """Start slskd process"""
    global slskd_process
    
    # Check if already running
    if is_slskd_running(web_port):
        if progress_callback:
            progress_callback("slskd already running")
        return True
    
    # Download if needed
    if not is_slskd_installed():
        if progress_callback:
            progress_callback("slskd not found, downloading...")
        download_slskd(progress_callback)
    
    # Create config
    config_path = create_slskd_config(soulseek_username, soulseek_password, web_port)
    
    # Start process
    exe_path = get_slskd_executable()
    slskd_dir = get_slskd_dir()
    
    if progress_callback:
        progress_callback("Starting slskd...")
    
    # Start slskd
    system = platform.system()
    
    if system == "Windows":
        # Use CREATE_NO_WINDOW flag on Windows
        CREATE_NO_WINDOW = 0x08000000
        slskd_process = subprocess.Popen(
            [exe_path, "--config", config_path],
            cwd=slskd_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW
        )
    else:
        slskd_process = subprocess.Popen(
            [exe_path, "--config", config_path],
            cwd=slskd_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    
    # Wait for it to start
    for i in range(30):  # Wait up to 30 seconds
        time.sleep(1)
        if is_slskd_running(web_port):
            if progress_callback:
                progress_callback("slskd started!")
            return True
        if progress_callback:
            progress_callback(f"Waiting for slskd... {i+1}s")
    
    raise Exception("slskd failed to start within 30 seconds")


def stop_slskd():
    """Stop slskd process"""
    global slskd_process
    
    if slskd_process is not None:
        try:
            slskd_process.terminate()
            slskd_process.wait(timeout=5)
        except:
            try:
                slskd_process.kill()
            except:
                pass
        slskd_process = None


def cleanup_on_exit():
    """Cleanup handler for when the app exits"""
    stop_slskd()


# Register cleanup
atexit.register(cleanup_on_exit)


def get_slskd_status():
    """Get detailed slskd status"""
    if not is_slskd_running():
        return {"running": False}
    
    try:
        # Try to get application info
        session = requests.Session()
        
        # Login
        r = session.post(
            "http://localhost:5030/api/v0/session",
            json={"username": "slskd", "password": "slskd"},
            timeout=5
        )
        
        if r.status_code != 200:
            return {"running": True, "authenticated": False}
        
        token = r.json()['token']
        session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Get state
        state = session.get("http://localhost:5030/api/v0/application").json()
        
        return {
            "running": True,
            "authenticated": True,
            "connected": state.get("server", {}).get("isConnected", False),
            "username": state.get("server", {}).get("username", "")
        }
    except Exception as e:
        return {"running": True, "error": str(e)}


# For testing
if __name__ == "__main__":
    print(f"App dir: {get_app_dir()}")
    print(f"slskd dir: {get_slskd_dir()}")
    print(f"Data dir: {get_data_dir()}")
    print(f"Download dir: {get_download_dir()}")
    print(f"slskd installed: {is_slskd_installed()}")
    print(f"slskd running: {is_slskd_running()}")
