# spotify2slsk

Easily download your spotify library via soulseek. 

```
  ┌─┐┌─┐┌─┐┌┬┐┬┌─┐┬ ┬┌─┐┌─┐┬  ┌─┐┬┌─
  └─┐├─┘│ │ │ │├┤ └┬┘┌─┘└─┐│  └─┐├┴┐
  └─┘┴  └─┘ ┴ ┴└   ┴ └─┘└─┘┴─┘└─┘┴ ┴
```

## Quick Start

1. Run the "build.bat", which will generate a .exe in a "release" folder 
2. Double-click the .exe to run
3. Follow the prompts (generate account or use existing)
4. Login with Spotify
5. Download all or select certain playlists
6. Have the app sort the downloads into folders and select where to place them
7. :DDDDD yay


## Important Notes

- Windows SmartScreen Warning
When you first run the .exe, Windows may show "Windows protected your PC". This is because the app isn't signed with a certificate (costs $$$). Click "More info" → "Run anyway".

- Firewall Prompt
The app needs network access to connect to Soulseek. Click "Allow access" when Windows Firewall asks.

- First Run Downloads ~50MB
On first launch, the app downloads the Soulseek client (slskd) automatically. This only happens once.

## Menu Options

| Key | Action |
|-----|--------|
| 1 | Login with Spotify / Refresh library |
| 2 | Import from CSV files (alternative) |
| 3 | Download ALL (auto mode) |
| 4 | Download a single playlist |
| 5 | Retry failed tracks |
| 6 | Organize into folders |
| 7 | Open folders |
| s | Settings |
| q | Quit |

## File Locations
Downloads saved to: `%LOCALAPPDATA%\spotify2slsk\downloads\`
*Organized output: Your Desktop → `spotify2slsk Music` folder (or custom location)

Config/Progress: `%LOCALAPPDATA%\spotify2slsk\`

## Troubleshooting
"Windows protected your PC"
- Click "More info" → "Run anyway"
- This is normal for unsigned applications

"No internet connection"
- Check your network connection
- Make sure firewall isn't blocking the app

"Login failed: INVALIDPASS"  
- The username exists with a different password
- Generate a new random account instead

"No results found"
- Some tracks aren't on Soulseek
- Use option 5 to retry with manual search
- Obscure tracks may not be available

Downloads are slow
- Normal for Soulseek (peer-to-peer)
- Let it run in background
- Speed depends on who's sharing

Spotify login fails
- Make sure browser opens the auth page
- Click through any certificate warnings (localhost)
- If stuck, close and retry

## Running from Source

```bash
# Install dependencies
pip install -r requirements.txt

# Run
python downloader.py

# Or on Windows, just double-click:
start.bat
```

## Building the Executable

```bash
# Windows
build.bat

# Mac/Linux  
./build.sh
```

Output: `dist/spotify2slsk.exe` (~25MB)

## Privacy

- Credentials stored locally only (`%LOCALAPPDATA%\spotify2slsk\`)
- No telemetry, no tracking
- Delete `config.json` to remove saved credentials

## License

MIT — meow meow meow meow meow meow

## Legal

For personal use. Support artists n alladat. made by cowgirl
