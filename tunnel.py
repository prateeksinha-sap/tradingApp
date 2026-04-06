"""
Ngrok Tunnel Manager
Creates a public URL for the Streamlit dashboard so it's accessible on mobile.
"""

import os
import subprocess
import time
import json
import requests

from config import NGROK_CONFIG


def _get_auth_token() -> str:
    """Get ngrok auth token from config or environment."""
    return NGROK_CONFIG.get("auth_token", "") or os.environ.get("NGROK_AUTH_TOKEN", "")


def is_ngrok_installed() -> bool:
    """Check if ngrok is installed and available."""
    try:
        result = subprocess.run(["ngrok", "version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_active_tunnel() -> str | None:
    """Check if there's already an active ngrok tunnel and return its URL."""
    try:
        resp = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=3)
        if resp.status_code == 200:
            tunnels = resp.json().get("tunnels", [])
            for t in tunnels:
                if t.get("proto") == "https":
                    return t["public_url"]
            # Fallback to any tunnel
            if tunnels:
                return tunnels[0].get("public_url")
    except Exception:
        pass
    return None


def start_tunnel(port: int = 8501) -> tuple[bool, str]:
    """
    Start an ngrok tunnel to the given port.
    Returns (success, url_or_error_message).
    """
    auth_token = _get_auth_token()

    if not is_ngrok_installed():
        return False, (
            "ngrok is not installed. To install:\n"
            "1. Download from https://ngrok.com/download\n"
            "2. Unzip and add to PATH\n"
            "3. Run: ngrok config add-authtoken YOUR_TOKEN"
        )

    # Check if tunnel already exists
    existing = get_active_tunnel()
    if existing:
        return True, existing

    # Set auth token if provided
    if auth_token:
        subprocess.run(
            ["ngrok", "config", "add-authtoken", auth_token],
            capture_output=True, text=True
        )

    # Start ngrok in background
    try:
        process = subprocess.Popen(
            ["ngrok", "http", str(port), "--log=stdout"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for tunnel to be established
        for _ in range(15):
            time.sleep(1)
            url = get_active_tunnel()
            if url:
                return True, url

        return False, "ngrok started but no tunnel URL found. Check ngrok dashboard."

    except Exception as e:
        return False, f"Failed to start ngrok: {e}"


def stop_tunnel():
    """Kill any running ngrok processes."""
    try:
        if os.name == "nt":  # Windows
            subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"],
                         capture_output=True, text=True)
        else:
            subprocess.run(["pkill", "ngrok"], capture_output=True, text=True)
    except Exception:
        pass


def get_install_instructions() -> str:
    """Return platform-appropriate install instructions."""
    return """
### 📱 Setup ngrok for Mobile Access

1. **Sign up** (free): [ngrok.com/signup](https://ngrok.com/signup)

2. **Download**: [ngrok.com/download](https://ngrok.com/download)
   - Download the Windows ZIP
   - Unzip `ngrok.exe` to a folder (e.g., `C:\\ngrok\\`)
   - Add that folder to your system PATH

3. **Authenticate** (one-time):
   - Copy your auth token from [ngrok dashboard](https://dashboard.ngrok.com/get-started/your-authtoken)
   - Run in terminal: `ngrok config add-authtoken YOUR_TOKEN`
   - Or paste the token in `config.py` → `NGROK_CONFIG["auth_token"]`

4. **Enable in config.py**:
   ```python
   NGROK_CONFIG = {
       "auth_token": "your_token_here",
       "enabled": True,
   }
   ```

5. **Restart the app** — the tunnel will start automatically and show you a mobile-friendly URL.
"""
