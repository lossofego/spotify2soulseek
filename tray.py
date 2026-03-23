"""
System Tray Support for spotify2slsk

Allows the app to run in the background with notifications.
Optional - gracefully degrades if dependencies not installed.
"""

import os
import sys
import threading
import time

# Try to import tray libraries
TRAY_AVAILABLE = False
NOTIFY_AVAILABLE = False

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    pystray = None
    Image = None

# Skip win10toast entirely - it doesn't work reliably in PyInstaller builds
# and causes ugly background thread exceptions
_win_toaster = None

# Use plyer for cross-platform notifications instead
_plyer_notify = None
try:
    from plyer import notification as _plyer_notify
    NOTIFY_AVAILABLE = True
except ImportError:
    pass


def show_notification(title, message, duration=5):
    """
    Show a system notification.
    Works on Windows, macOS, and Linux (with appropriate backends).
    """
    if not NOTIFY_AVAILABLE:
        return False
    
    try:
        if _win_toaster:
            # Windows toast notification
            try:
                _win_toaster.show_toast(
                    title, 
                    message, 
                    duration=duration, 
                    threaded=True
                )
                return True
            except Exception:
                # win10toast can fail in PyInstaller builds
                return False
        elif _plyer_notify:
            # Cross-platform via plyer
            _plyer_notify.notify(
                title=title,
                message=message,
                app_name="spotify2slsk",
                timeout=duration
            )
            return True
    except Exception as e:
        # Silently fail - notifications are nice-to-have
        pass
    
    return False


class TrayIcon:
    """
    System tray icon with status updates and notifications.
    
    Usage:
        tray = TrayIcon()
        tray.start()
        
        # Update status
        tray.update(status="Downloading...", downloaded=5, total=100)
        
        # Show notification
        tray.notify("Download Complete", "50 tracks downloaded")
        
        # Stop
        tray.stop()
    """
    
    def __init__(self, on_show=None, on_quit=None):
        """
        Initialize tray icon.
        
        Args:
            on_show: Callback when "Show" is clicked
            on_quit: Callback when "Quit" is clicked
        """
        self.on_show = on_show
        self.on_quit = on_quit
        self.icon = None
        self._thread = None
        self._running = False
        
        # Status for menu display
        self.status = "Idle"
        self.downloaded = 0
        self.failed = 0
        self.total = 0
        self.current_track = ""
    
    @property
    def is_available(self):
        """Check if tray functionality is available"""
        return TRAY_AVAILABLE
    
    def _create_icon_image(self, size=64):
        """Create a simple icon image programmatically"""
        if not Image:
            return None
        
        # Create dark background
        img = Image.new('RGBA', (size, size), (30, 30, 30, 255))
        draw = ImageDraw.Draw(img)
        
        # Draw a stylized "S" for Soulseek/Spotify
        margin = size // 8
        
        # Green accent (Spotify-ish)
        green = (30, 215, 96)
        
        # Draw rounded rectangle background
        draw.rounded_rectangle(
            [margin, margin, size - margin, size - margin],
            radius=size // 6,
            fill=(45, 45, 45),
            outline=green,
            width=2
        )
        
        # Draw "S" text
        try:
            text = "S"
            text_x = size // 3
            text_y = size // 4
            draw.text((text_x, text_y), text, fill=green)
        except:
            pass
        
        return img
    
    def _create_menu(self):
        """Create the right-click menu"""
        if not pystray:
            return None
        
        # Build status text
        if self.total > 0:
            progress = f"{self.downloaded}/{self.total}"
        else:
            progress = str(self.downloaded)
        
        menu_items = [
            pystray.MenuItem(
                f"Status: {self.status}",
                None,
                enabled=False
            ),
            pystray.MenuItem(
                f"Downloaded: {progress}",
                None,
                enabled=False
            ),
        ]
        
        if self.failed > 0:
            menu_items.append(
                pystray.MenuItem(
                    f"Failed: {self.failed}",
                    None,
                    enabled=False
                )
            )
        
        if self.current_track:
            # Truncate long track names
            track_display = self.current_track[:40]
            if len(self.current_track) > 40:
                track_display += "..."
            menu_items.append(
                pystray.MenuItem(
                    f"Current: {track_display}",
                    None,
                    enabled=False
                )
            )
        
        menu_items.extend([
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show Window", self._handle_show),
            pystray.MenuItem("Quit", self._handle_quit),
        ])
        
        return pystray.Menu(*menu_items)
    
    def _handle_show(self, icon, item):
        """Handle Show menu click"""
        if self.on_show:
            self.on_show()
    
    def _handle_quit(self, icon, item):
        """Handle Quit menu click"""
        self.stop()
        if self.on_quit:
            self.on_quit()
    
    def start(self):
        """Start the tray icon in a background thread"""
        if not TRAY_AVAILABLE:
            return False
        
        if self._running:
            return True
        
        try:
            self.icon = pystray.Icon(
                name="spotify2slsk",
                icon=self._create_icon_image(),
                title="spotify2slsk",
                menu=self._create_menu()
            )
            
            self._running = True
            self._thread = threading.Thread(target=self.icon.run, daemon=True)
            self._thread.start()
            
            return True
        except Exception as e:
            self._running = False
            return False
    
    def stop(self):
        """Stop the tray icon"""
        self._running = False
        if self.icon:
            try:
                self.icon.stop()
            except:
                pass
            self.icon = None
    
    def update(self, status=None, downloaded=None, failed=None, total=None, current=None):
        """
        Update tray status.
        
        Args:
            status: Current status string (e.g., "Downloading...", "Idle")
            downloaded: Number of successful downloads
            failed: Number of failed downloads
            total: Total tracks to download
            current: Current track being processed
        """
        if status is not None:
            self.status = status
        if downloaded is not None:
            self.downloaded = downloaded
        if failed is not None:
            self.failed = failed
        if total is not None:
            self.total = total
        if current is not None:
            self.current_track = current
        
        # Update the menu
        if self.icon and self._running:
            try:
                self.icon.menu = self._create_menu()
                self.icon.update_menu()
            except:
                pass
    
    def notify(self, title, message, duration=5):
        """Show a system notification"""
        return show_notification(title, message, duration)


class BackgroundDownloader:
    """
    Manages background downloading with tray integration.
    
    Wraps the download process to run in background with:
    - System tray icon showing progress
    - Notifications on completion
    - Ability to continue while minimized
    """
    
    def __init__(self, tray_icon=None):
        self.tray = tray_icon or TrayIcon()
        self._download_thread = None
        self._cancel_requested = False
        
        # Callbacks
        self.on_complete = None
        self.on_error = None
    
    def start_background_download(self, download_func, *args, **kwargs):
        """
        Start a download function in the background.
        
        Args:
            download_func: The function to run (should accept progress_callback)
            *args, **kwargs: Arguments to pass to download_func
        """
        if self._download_thread and self._download_thread.is_alive():
            return False  # Already running
        
        self._cancel_requested = False
        
        def _run():
            try:
                # Add our progress callback
                kwargs['tray_callback'] = self._progress_callback
                kwargs['cancel_check'] = lambda: self._cancel_requested
                
                self.tray.update(status="Downloading...")
                result = download_func(*args, **kwargs)
                
                if not self._cancel_requested:
                    self.tray.update(status="Complete")
                    self.tray.notify(
                        "Download Complete",
                        f"Downloaded {self.tray.downloaded} tracks"
                    )
                    
                    if self.on_complete:
                        self.on_complete(result)
            except Exception as e:
                self.tray.update(status="Error")
                self.tray.notify("Download Error", str(e)[:100])
                
                if self.on_error:
                    self.on_error(e)
        
        self._download_thread = threading.Thread(target=_run, daemon=True)
        self._download_thread.start()
        
        return True
    
    def _progress_callback(self, downloaded, failed, total, current_track):
        """Internal callback to update tray"""
        self.tray.update(
            downloaded=downloaded,
            failed=failed,
            total=total,
            current=current_track
        )
    
    def cancel(self):
        """Request cancellation of background download"""
        self._cancel_requested = True
    
    @property
    def is_running(self):
        """Check if a download is in progress"""
        return self._download_thread and self._download_thread.is_alive()


# === Convenience functions ===

def check_tray_support():
    """Check if system tray is available"""
    return TRAY_AVAILABLE


def check_notification_support():
    """Check if notifications are available"""
    return NOTIFY_AVAILABLE


def get_feature_status():
    """Get a dict of available features"""
    return {
        "tray": TRAY_AVAILABLE,
        "notifications": NOTIFY_AVAILABLE,
        "tray_package": "pystray" if TRAY_AVAILABLE else None,
        "notify_package": "win10toast" if _win_toaster else ("plyer" if _plyer_notify else None)
    }


# === Test ===
if __name__ == "__main__":
    print("System Tray Feature Check")
    print("=" * 40)
    
    status = get_feature_status()
    print(f"Tray support:         {status['tray']}")
    print(f"Notification support: {status['notifications']}")
    print(f"Tray package:         {status['tray_package'] or 'Not installed'}")
    print(f"Notify package:       {status['notify_package'] or 'Not installed'}")
    
    if not TRAY_AVAILABLE:
        print("\nTo enable tray support, install:")
        print("  pip install pystray pillow")
    
    if not NOTIFY_AVAILABLE:
        print("\nTo enable notifications, install:")
        if sys.platform == 'win32':
            print("  pip install win10toast")
        else:
            print("  pip install plyer")
    
    # Test if available
    if TRAY_AVAILABLE:
        print("\n" + "=" * 40)
        print("Testing tray icon for 10 seconds...")
        
        tray = TrayIcon(
            on_show=lambda: print("Show clicked!"),
            on_quit=lambda: print("Quit clicked!")
        )
        
        if tray.start():
            print("Tray icon started!")
            
            for i in range(10):
                time.sleep(1)
                tray.update(
                    status="Downloading...",
                    downloaded=i + 1,
                    total=10,
                    current=f"Artist {i} - Song {i}"
                )
                print(f"  Progress: {i+1}/10")
            
            if NOTIFY_AVAILABLE:
                print("Sending test notification...")
                tray.notify("Test Complete", "Tray functionality working!")
            
            time.sleep(2)
            tray.stop()
            print("Tray icon stopped.")
        else:
            print("Failed to start tray icon.")
    
    print("\nDone!")
