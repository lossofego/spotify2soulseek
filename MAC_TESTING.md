# Running spotify2slsk on Mac

## Step 1: Install Python
Open Terminal (search "Terminal" in Spotlight) and paste:
```
brew install python3
```
If that doesn't work, download Python from https://www.python.org/downloads/

## Step 2: Download the app
Download and unzip the project folder.

## Step 3: Run it
In Terminal:
```
cd ~/Downloads/spotify2slsk
pip3 install -r requirements.txt
python3 downloader.py
```

## If you see a security warning
Mac might say something like "slskd can't be opened because it's from an unidentified developer."

**Fix:** Go to System Preferences → Security & Privacy → click "Allow Anyway"

Then run the app again.

---

**Something broke?** Screenshot the error and send it to me!
