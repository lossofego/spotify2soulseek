# spotify2slsk

Easily download your spotify library via soulseek on windows   
(**MAC USERS SEE NOTES ON BOTTOM OF READ ME**).   

```
  ┌─┐┌─┐┌─┐┌┬┐┬┌─┐┬ ┬┌─┐┌─┐┬  ┌─┐┬┌─
  └─┐├─┘│ │ │ │├┤ └┬┘┌─┘└─┐│  └─┐├┴┐
  └─┘┴  └─┘ ┴ ┴└   ┴ └─┘└─┘┴─┘└─┘┴ ┴
```

## Quick Start

1. Run the "build.bat" file, which will generate a .exe file in a "release" folder 
2. go to "release" folder, then double-click the spotify2slsk.exe to run
3. Let the program intialize and follow the prompts (generate soulseek account or use existing)
4. Login with spotify
5. Download all or select certain playlists to download
6. Have the app sort the downloads into folders and select where to place them
7. :DDDDD yay


## Important Notes

- Windows SmartScreen Warning
When u first run the .exe, windows may show "windows protected your PC". This is because the app isn't signed with a certificate. Just click more info, then run anyway. 

- Firewall Prompt
The app needs network access to connect to Soulseek. Click "allow access" when windows firewall asks.

- First Run Downloads 
On first launch, the app downloads the soulseek client automatically, which is ~50mb. This only happens the first time u run the .exe. 

## Menu Options

| Key | Action |
|-----|--------|
| 1 | Login with spotify / refresh library |
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
Organized output: ur Desktop to `spotify2slsk Music` folder (or custom location)

Config/progress: `%LOCALAPPDATA%\spotify2slsk\`

## Troubleshooting
"Windows protected your PC"
- Click "more info" then "run anyway"
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
- This is normal for soulseek. 
- Let it run in background
- Speed depends on who's sharing
- you may want to consider using a VPN when using soulseek - mullvad is cheap and a good service. 

Spotify login fails
- Make sure browser opens the auth page
- Click through any certificate warnings (localhost)
- if it gets stuck, close and try again. 

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

## NOTES FOR MAC USERS   
Running spotify2slsk on Mac  

Step 1: Install Python  
Open Terminal (search "Terminal" on ur mac), then copy and paste the following:  
  "brew install python3"  

- If that doesn't work, download Python from https://www.python.org/downloads/ <br />

Step 2: Download and unzip the project folder. <br />

Step 3: 
  In the same terminal, copy and paste the following: <br />

"cd ~/Downloads/spotify2slsk  <br />
pip3 install -r requirements.txt <br />
python3 downloader.py" <br />

Mac might give you a security warning, and say something like "slskd can't be opened because it's from an unidentified developer."  
if this is the case, go to system references, then Security & Privacy, then click "allow anyway", then run the app again.  

If Spotify login shows a certificate warning, just click through it. This is normal.   

if this doesnt work or something breaks, please take a picture and let me know! did not get a chance to do as much testing on mac systems.   

## Privacy

- Credentials stored locally only (`%LOCALAPPDATA%\spotify2slsk\`)
- No tracking
- Delete `config.json` to remove saved credentials

## License

MIT — meow meow meow meow meow meow

## Legal

For personal use. Support artists n alladat. made by cowgirl @gondolacrawler
