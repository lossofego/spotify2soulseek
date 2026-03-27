 ```
  ┌─┐┌─┐┌─┐┌┬┐┬┌─┐┬ ┬┌─┐┌─┐┬  ┌─┐┬┌─
  └─┐├─┘│ │ │ │├┤ └┬┘┌─┘└─┐│  └─┐├┴┐
  └─┘┴  └─┘ ┴ ┴└   ┴ └─┘└─┘┴─┘└─┘┴ ┴
```

## Quick Start

1. Download `spotify2slsk.exe`
2. Double-click to run  
3. Follow the prompts (generate account or use existing)
4. Login with Spotify
5. Download ALL or select what playlists to download
6. Organize into folders
7. yay meow

## Important Notes

**Windows SmartScreen Warning**  
When you first run the .exe, windows may show "Windows protected your PC". This is because the app isn't signed with a certificate. Click **"More info"** then **"Run anyway"**.

**Firewall Prompt**  
The app needs network access to connect to Soulseek. Click **"Allow access"** when windows asks

**First Run Downloads**  
On first launch, the app downloads the Soulseek client (slskd) automatically. This only happens once.

## File Locations

**Downloads saved to:** `%LOCALAPPDATA%\spotify2slsk\downloads\`

**Organized output:** Your Desktop → `spotify2slsk Music` folder (or custom location)

**Config/Progress:** `%LOCALAPPDATA%\spotify2slsk\`

## Troubleshooting

**"Windows protected your PC"**  
- Click "More info" then "Run anyway"  
- This is normal for unsigned applications  

**"No internet connection"**    
- Check your network connection  
- Make sure firewall isn't blocking the app  

**"Login failed: INVALIDPASS"**    
- The username exists with a different password  
- Generate a new random account instead  

**"No results found"**   
- Some tracks aren't on Soulseek    
- Use option 5 to retry with manual search  
- Obscure tracks may not be available  

**Downloads are slow**  
- Normal for Soulseek, esp. if on wifi  
- Let it run in background  
- Speed depends on who's sharing  
  
**Spotify login fails**  
- Make sure browser opens the auth page  
- If stuck, close and retry  

you may want to use a VPN when using soulseek - mullvad is a good option  

## Privacy

- Credentials stored locally only (`%LOCALAPPDATA%\spotify2slsk\`)
- No tracking
- Delete `config.json` to remove saved credentials

## License

MIT — meow.

## Legal

For personal use. support artists.

