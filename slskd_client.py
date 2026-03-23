"""
slskd API Client

Handles communication with slskd REST API and provides
detailed connection status including Soulseek login state.
"""

import requests
import time


class SoulseekLoginError(Exception):
    """Raised when Soulseek login fails"""
    def __init__(self, reason, detail=None):
        self.reason = reason
        self.detail = detail
        message = f"Soulseek login failed: {reason}"
        if detail:
            message += f" ({detail})"
        super().__init__(message)


class SlskdClient:
    """Client for interacting with slskd REST API"""
    
    def __init__(self, host="http://localhost:5030", username="slskd", password="slskd"):
        self.host = host.rstrip('/')
        self.username = username
        self.password = password
        self.session = None
        self.token = None
    
    def connect(self):
        """Connect to slskd and authenticate"""
        self.session = requests.Session()
        
        try:
            response = self.session.post(
                f"{self.host}/api/v0/session",
                json={"username": self.username, "password": self.password},
                timeout=10
            )
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to slskd at {self.host}")
        except requests.exceptions.Timeout:
            raise ConnectionError("Connection timed out")
        
        if response.status_code == 200:
            self.token = response.json()['token']
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            return True
        elif response.status_code == 401:
            raise PermissionError("Invalid slskd credentials")
        else:
            raise Exception(f"Connection failed: {response.status_code}")
    
    def get_application_state(self):
        """Get detailed application state including Soulseek connection"""
        try:
            r = self.session.get(f"{self.host}/api/v0/application")
            if r.status_code == 200:
                return r.json()
        except:
            pass
        return None
    
    def is_connected_to_soulseek(self):
        """Check if slskd is connected to Soulseek network"""
        state = self.get_application_state()
        if state:
            return state.get("server", {}).get("isConnected", False)
        return False
    
    def get_soulseek_state(self):
        """
        Get detailed Soulseek connection state.
        
        Returns dict with:
            - connected: bool - True if connected to Soulseek
            - state: str - Current state (e.g., "Connected", "Disconnected", "LoggingIn")
            - username: str - Logged in username
            - message: str - Status message (may contain error info)
        """
        state = self.get_application_state()
        if not state:
            return {"connected": False, "state": "Unknown", "username": "", "message": ""}
        
        server = state.get("server", {})
        return {
            "connected": server.get("isConnected", False),
            "state": server.get("state", "Unknown"),
            "username": server.get("username", ""),
            "message": server.get("message", "")
        }
    
    def wait_for_soulseek_connection(self, timeout=60, progress_callback=None):
        """
        Wait for slskd to connect to Soulseek network.
        
        Returns:
            True if connected successfully
            
        Raises:
            SoulseekLoginError if login fails (wrong password, invalid username, etc.)
        """
        last_state = ""
        
        for i in range(timeout):
            state = self.get_soulseek_state()
            
            if state["connected"]:
                return True
            
            # Check for login errors in the message
            message = state.get("message", "").lower()
            current_state = state.get("state", "")
            
            # Detect login failures
            # Based on protocol: INVALIDPASS, INVALIDUSERNAME, etc.
            if "invalidpass" in message or "invalid pass" in message or "wrong password" in message:
                raise SoulseekLoginError("INVALIDPASS", "Username exists but password is incorrect")
            
            if "invalidusername" in message or "invalid username" in message:
                # Extract detail if available
                detail = None
                if "too long" in message:
                    detail = "Username too long (max 30 characters)"
                elif "empty" in message:
                    detail = "Username cannot be empty"
                elif "invalid character" in message:
                    detail = "Username contains invalid characters"
                elif "space" in message:
                    detail = "Username cannot have leading/trailing spaces"
                raise SoulseekLoginError("INVALIDUSERNAME", detail)
            
            if "svrfull" in message or "server full" in message:
                raise SoulseekLoginError("SVRFULL", "Server is not accepting connections")
            
            if "svrprivate" in message or "server private" in message:
                raise SoulseekLoginError("SVRPRIVATE", "Server is not accepting new registrations")
            
            # Update progress
            if progress_callback:
                status = current_state if current_state != last_state else f"{i+1}s"
                progress_callback(f"Connecting to Soulseek... {status}")
                last_state = current_state
            
            time.sleep(1)
        
        return False
    
    def search(self, search_term, timeout=90, progress_callback=None):
        """
        Search for a track on Soulseek
        
        Args:
            search_term: What to search for
            timeout: Maximum seconds to wait
            progress_callback: Optional function(file_count, user_count, seconds, is_complete)
        
        Returns:
            List of user responses with files
        """
        response = self.session.post(
            f"{self.host}/api/v0/searches",
            json={"searchText": search_term}
        )
        
        if response.status_code != 200:
            return []
        
        search_id = response.json()['id']
        file_count = 0
        
        for i in range(timeout):
            time.sleep(1)
            status = self.session.get(f"{self.host}/api/v0/searches/{search_id}")
            data = status.json()
            
            file_count = data.get('fileCount', 0)
            user_count = data.get('responseCount', 0)
            is_complete = data.get('isComplete', False)
            
            if progress_callback:
                progress_callback(file_count, user_count, i + 1, is_complete)
            
            if is_complete:
                break
        
        # Wait then fetch results
        time.sleep(2)
        
        responses = self.session.get(f"{self.host}/api/v0/searches/{search_id}/responses")
        results = responses.json()
        
        # Retry if empty but files exist
        if len(results) == 0 and file_count > 0:
            time.sleep(5)
            responses = self.session.get(f"{self.host}/api/v0/searches/{search_id}/responses")
            results = responses.json()
        
        return results
    
    def queue_download(self, username, file_obj, retries=2):
        """Queue a file for download"""
        for attempt in range(retries + 1):
            try:
                response = self.session.post(
                    f"{self.host}/api/v0/transfers/downloads/{username}",
                    json=[file_obj],
                    timeout=30
                )
                if response.status_code == 201:
                    return True
                # 409 = already in queue (treat as success)
                if response.status_code == 409:
                    return True
                # Wait before retry
                if attempt < retries:
                    time.sleep(2)
            except Exception:
                if attempt < retries:
                    time.sleep(2)
                    continue
                return False
        return False
    
    def get_downloads(self):
        """Get current download queue"""
        response = self.session.get(f"{self.host}/api/v0/transfers/downloads")
        if response.status_code == 200:
            return response.json()
        return []
