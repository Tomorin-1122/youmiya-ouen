@echo off
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9223 --remote-allow-origins=* --user-data-dir="%USERPROFILE%\.chrome-debug"
echo Chrome started with CDP on port 9223
echo Run: python cdp_scrape.py
