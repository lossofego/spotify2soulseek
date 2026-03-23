# config management + soulseek account generation
# soulseek auto-creates accounts on first login if username doesn't exist

import os, json, random, string, re
from slskd_manager import get_data_dir, get_download_dir, get_organized_dir, get_import_dir

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "soulseek_username": "",
    "soulseek_password": "",
    "slskd_port": 5030,
    "min_bitrate": 192,
    "search_timeout": 90,
    "auto_accept_min_size_mb": 3,
    "auto_accept_max_size_mb": 200,
    "format_preference": "mp3"  # "mp3" for best mp3, "lossless" for flac/wav
}

# soulseek username rules
SLSK_USERNAME_MAX_LENGTH = 30
SLSK_USERNAME_PATTERN = re.compile(r'^[\x20-\x7E]+$')  # printable ascii


def get_config_path():
    return os.path.join(get_data_dir(), CONFIG_FILE)


def load_config():
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                cfg = DEFAULT_CONFIG.copy()
                cfg.update(saved)
                return cfg
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    path = get_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)


def get_paths():
    return {
        "data_dir": get_data_dir(),
        "download_dir": get_download_dir(),
        "organized_dir": get_organized_dir(),
        "import_dir": get_import_dir()
    }


def is_configured():
    cfg = load_config()
    return bool(cfg.get("soulseek_username")) and bool(cfg.get("soulseek_password"))


def generate_username():
    """
    Generate a random Soulseek username.
    Format: s2s_XXXXXX (total 10 chars, well under 30 limit)
    """
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"s2s_{suffix}"


def generate_password():
    """
    Generate a random secure password.
    12 characters, alphanumeric.
    """
    return ''.join(random.choices(string.ascii_letters + string.digits, k=12))


def validate_soulseek_username(username):
    """
    Validate Soulseek username format.
    
    Rules (from Soulseek protocol documentation):
    - Cannot be empty
    - Max 30 characters
    - Only printable ASCII characters (0x20-0x7E)
    - No leading or trailing spaces
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if not username:
        return False, "Username cannot be empty"
    
    if len(username) > SLSK_USERNAME_MAX_LENGTH:
        return False, f"Username must be {SLSK_USERNAME_MAX_LENGTH} characters or less"
    
    if username != username.strip():
        return False, "Username cannot have leading or trailing spaces"
    
    # Check for printable ASCII only
    if not SLSK_USERNAME_PATTERN.match(username):
        return False, "Username can only contain printable ASCII characters (letters, numbers, basic symbols)"
    
    return True, None


def validate_soulseek_password(password):
    """
    Validate Soulseek password.
    
    Rules:
    - Cannot be empty (server returns EMPTYPASSWORD)
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if not password:
        return False, "Password cannot be empty"
    
    return True, None


def setup_wizard():
    """
    Interactive first-run setup wizard.
    
    Offers two modes:
    1. Auto-generate: Creates a random username/password
    2. Manual: User enters their own credentials
    
    The Soulseek server automatically creates accounts on first login,
    so no separate registration step is needed.
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich import box
    
    console = Console()
    
    console.print(Panel(
        "[bold]Welcome to spotify2slsk![/bold]\n\n"
        "Download your Spotify library from Soulseek.",
        box=box.ROUNDED
    ))
    
    config = load_config()
    paths = get_paths()
    
    console.print("\n[bold cyan]Soulseek Account Setup[/bold cyan]\n")
    console.print("You need a Soulseek account to download music.")
    console.print("[dim]New accounts are created automatically when you first connect.[/dim]\n")
    
    # Option to auto-generate or use existing account
    console.print("  [bold]y[/bold] = Generate a new random account")
    console.print("  [bold]n[/bold] = Use my existing Soulseek account\n")
    
    auto_generate = Confirm.ask(
        "Generate a random account automatically?",
        default=True
    )
    
    if auto_generate:
        # Generate random credentials
        config['soulseek_username'] = generate_username()
        config['soulseek_password'] = generate_password()
        
        console.print(f"\n[green]✓ Generated account:[/green]")
        console.print(f"  Username: [bold cyan]{config['soulseek_username']}[/bold cyan]")
        console.print(f"  Password: [bold cyan]{config['soulseek_password']}[/bold cyan]")
        console.print("\n[dim]These credentials will be saved. You can use them to log in[/dim]")
        console.print("[dim]from other Soulseek clients if you want.[/dim]")
    else:
        # Manual entry
        console.print("\nEnter your credentials:")
        console.print("[dim]If the username is new, an account will be created automatically.[/dim]")
        console.print("[dim]If it exists, you'll need the correct password.[/dim]\n")
        
        # Get username with validation
        while True:
            username = Prompt.ask("Username")
            valid, error = validate_soulseek_username(username)
            if valid:
                config['soulseek_username'] = username
                break
            else:
                console.print(f"[red]✗ {error}[/red]")
        
        # Get password with validation
        while True:
            password = Prompt.ask("Password", password=True)
            valid, error = validate_soulseek_password(password)
            if valid:
                config['soulseek_password'] = password
                break
            else:
                console.print(f"[red]✗ {error}[/red]")
    
    # Save configuration
    save_config(config)
    
    console.print("\n[green]✓ Configuration saved![/green]")
    console.print(f"\n[dim]Data directory:[/dim] {paths['data_dir']}")
    console.print(f"[dim]Downloads:[/dim] {paths['download_dir']}")
    
    return config


def ensure_config():
    """Make sure we have valid config, run setup if needed"""
    if not is_configured():
        return setup_wizard()
    return load_config()


def reset_credentials():
    """Clear saved Soulseek credentials"""
    config = load_config()
    config['soulseek_username'] = ""
    config['soulseek_password'] = ""
    save_config(config)
    return config
