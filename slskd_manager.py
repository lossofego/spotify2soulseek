"""
slskd Manager - Automatically download and manage slskd

Handles downloading, configuring, starting, and monitoring the slskd process.
Includes port conflict detection and automatic process recovery.
"""

import os
import sys
import platform
import subprocess
import time
import zipfile
import tarfile
import socket
import atexit
import logging
import requests

logger = logging.getLogger(__name__)

# slskd release info
SLSKD_VERSION = "0.24.4"

SLSKD_RELEASES = {
    "Windows": {
        "url": f"https://github.com/slskd/slskd/releases/download/{SLSKD_VERSION}/slskd-{SLSKD_VERSION}-win-x64.zip",
        "executable": "slskd.exe",
        "archive_type": "zip"
    },
    "Darwin": {  # macOS
        "url": f"https://github.com/slskd/slskd/releases/download/{SLSKD_VERSION}/slskd-{SLSKD_VERSION}-osx-x64.zip",
        "executable": "slskd",
        "archive_type": "zip"
    },
    "Linux": {
        "url": f"https://github.com/slskd/slskd/releases/download/{SLSKD_VERSION}/slskd-{SLSKD_VERSION}-linux-x64.zip",
        "executable": "slskd",
        "archive_type": "zip"
    }
}

# Port scanning range
DEFAULT_PORT = 5030
PORT_RANGE_START = 5030
PORT_RANGE_END = 5039

# Global process reference
slskd_process = None
active_port = None  # Track which port slskd is actually running on


def get_app_dir():
    """Get the application directory"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))


def get_slskd_app_dir():
    """Get directory for slskd binary - always in user data, not exe dir"""
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


def _is_port_in_use(port):
    """Check if a TCP port is currently in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.bind(('127.0.0.1', port))
            return False
        except OSError:
            return True


def _is_slskd_on_port(port):
    """Check if the thing running on a port is actually slskd"""
    try:
        response = requests.get(f"http://localhost:{port}/api/v0/application", timeout=2)
        return response.status_code in [200, 401]
    except Exception:
        return False


def find_available_port(preferred_port=DEFAULT_PORT):
    """
    Find an available port for slskd.

    Logic:
    1. If preferred port has slskd already running, reuse it
    2. If preferred port is free, use it
    3. If preferred port is taken by something else, scan PORT_RANGE for a free one
    4. If all ports in range are taken, raise an error

    Returns:
        tuple: (port, is_existing_slskd) — port to use, and whether slskd is already there
    """
    # Check if slskd is already running on the preferred port
    if _is_slskd_on_port(preferred_port):
        logger.info(f"Found existing slskd on port {preferred_port}")
        return preferred_port, True

    # Check if preferred port is free
    if not _is_port_in_use(preferred_port):
        return preferred_port, False

    # Preferred port is taken by something else — scan for alternatives
    logger.warning(f"Port {preferred_port} is in use by another application, scanning alternatives...")

    for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
        if port == preferred_port:
            continue

        # Check if slskd is already here
        if _is_slskd_on_port(port):
            logger.info(f"Found existing slskd on port {port}")
            return port, True

        # Check if port is free
        if not _is_port_in_use(port):
            logger.info(f"Using alternate port {port}")
            return port, False

    raise Exception(
        f"All ports {PORT_RANGE_START}-{PORT_RANGE_END} are in use. "
        f"Please free up a port or close conflicting applications."
    )


def get_active_port():
    """Get the port slskd is currently running on"""
    global active_port
    return active_port or DEFAULT_PORT


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


def is_slskd_running(port=None):
    """Check if slskd is already running"""
    if port is None:
        port = get_active_port()
    return _is_slskd_on_port(port)


def is_slskd_process_alive():
    """Check if our managed slskd process is still running"""
    global slskd_process
    if slskd_process is None:
        return False
    return slskd_process.poll() is None


def start_slskd(soulseek_username, soulseek_password, web_port=None, progress_callback=None):
    """
    Start slskd process with port conflict detection.

    If slskd is already running on the target port, reuses it.
    If the port is taken by something else, automatically tries alternate ports.
    """
    global slskd_process, active_port

    # Determine port
    preferred_port = web_port or DEFAULT_PORT

    try:
        port, is_existing = find_available_port(preferred_port)
    except Exception as e:
        raise Exception(str(e))

    active_port = port

    # If slskd is already running on this port, just use it
    if is_existing:
        if progress_callback:
            if port != preferred_port:
                progress_callback(f"slskd already running on port {port}")
            else:
                progress_callback("slskd already running")
        return True

    # Download if needed
    if not is_slskd_installed():
        if progress_callback:
            progress_callback("slskd not found, downloading...")
        download_slskd(progress_callback)

    # Create config with the determined port
    config_path = create_slskd_config(soulseek_username, soulseek_password, port)

    # Start process
    exe_path = get_slskd_executable()
    slskd_dir = get_slskd_dir()

    if progress_callback:
        if port != preferred_port:
            progress_callback(f"Starting slskd on port {port}...")
        else:
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

        # Check if process died
        if slskd_process.poll() is not None:
            exit_code = slskd_process.returncode
            slskd_process = None
            raise Exception(f"slskd exited immediately with code {exit_code}. "
                           f"Check if port {port} is available.")

        if is_slskd_running(port):
            if progress_callback:
                progress_callback("slskd started!")
            return True

        if progress_callback:
            progress_callback(f"Waiting for slskd... {i+1}s")

    raise Exception("slskd failed to start within 30 seconds")


def restart_slskd(soulseek_username, soulseek_password, progress_callback=None):
    """
    Restart slskd — used for auto-recovery when the process dies mid-session.

    Reuses the last known port if possible.
    """
    global active_port

    if progress_callback:
        progress_callback("Restarting slskd...")

    # Stop any existing process
    stop_slskd()

    # Brief pause to let the port free up
    time.sleep(2)

    # Restart on the same port we were using
    port = active_port or DEFAULT_PORT
    return start_slskd(soulseek_username, soulseek_password, web_port=port,
                       progress_callback=progress_callback)


def ensure_slskd_healthy(soulseek_username=None, soulseek_password=None, progress_callback=None):
    """
    Health check — call this before any slskd operation.

    If slskd is running, returns True.
    If our managed process died, attempts auto-restart (requires credentials).
    If slskd was never started, returns False.
    """
    port = get_active_port()

    # Quick check — is slskd responding?
    if is_slskd_running(port):
        return True

    # If we have a managed process that died, try to restart
    if slskd_process is not None and slskd_process.poll() is not None:
        logger.warning("slskd process died unexpectedly, attempting restart...")
        if soulseek_username and soulseek_password:
            try:
                return restart_slskd(soulseek_username, soulseek_password,
                                    progress_callback=progress_callback)
            except Exception as e:
                logger.error(f"Failed to restart slskd: {e}")
                return False
        else:
            logger.error("slskd died but no credentials available for restart")
            return False

    return False


def stop_slskd():
    """Stop slskd process"""
    global slskd_process
    if slskd_process is not None:
        try:
            slskd_process.terminate()
            slskd_process.wait(timeout=5)
        except Exception:
            try:
                slskd_process.kill()
            except Exception:
                pass
        slskd_process = None


def cleanup_on_exit():
    """Cleanup handler for when the app exits"""
    stop_slskd()


# Register cleanup
atexit.register(cleanup_on_exit)


def get_slskd_status():
    """Get detailed slskd status"""
    port = get_active_port()

    if not is_slskd_running(port):
        return {"running": False, "port": port}

    try:
        # Try to get application info
        session = requests.Session()

        # Login
        r = session.post(
            f"http://localhost:{port}/api/v0/session",
            json={"username": "slskd", "password": "slskd"},
            timeout=5
        )

        if r.status_code != 200:
            return {"running": True, "authenticated": False, "port": port}

        token = r.json()['token']
        session.headers.update({"Authorization": f"Bearer {token}"})

        # Get state
        state = session.get(f"http://localhost:{port}/api/v0/application").json()

        return {
            "running": True,
            "authenticated": True,
            "connected": state.get("server", {}).get("isConnected", False),
            "username": state.get("server", {}).get("username", ""),
            "port": port
        }
    except Exception as e:
        return {"running": True, "error": str(e), "port": port}


# For testing
if __name__ == "__main__":
    print(f"App dir: {get_app_dir()}")
    print(f"slskd dir: {get_slskd_dir()}")
    print(f"Data dir: {get_data_dir()}")
    print(f"Download dir: {get_download_dir()}")
    print(f"slskd installed: {is_slskd_installed()}")
    print(f"slskd running: {is_slskd_running()}")

    # Test port detection
    print(f"\nPort detection:")
    try:
        port, existing = find_available_port()
        print(f"  Available port: {port} (existing slskd: {existing})")
    except Exception as e:
        print(f"  Error: {e}")
