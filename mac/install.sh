#!/bin/bash
# One-time setup on a Mac. In Terminal:  bash install.sh
#
# Afterwards, every day the first time your Mac is awake and online, the posts
# you saved on Instagram are downloaded into ~/Pictures/Instagram Saved.
# Google Photos (open in Chrome) then uploads that folder for you.
set -euo pipefail

APP_DIR="$HOME/.insta-saved"
PHOTOS_DIR="$HOME/Pictures/Instagram Saved"
LABEL="com.instasaved.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# --------------------------------------------------------------------------- #
say "1/4  Installing Instaloader (the downloader)…"
# --------------------------------------------------------------------------- #
if ! python3 -c 'import sys' >/dev/null 2>&1; then
  echo "macOS needs its free developer tools first. A window should have opened:"
  echo "click Install, wait for it to finish, then run this script again."
  exit 1
fi
mkdir -p "$APP_DIR" "$PHOTOS_DIR"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet --upgrade instaloader browser_cookie3

# --------------------------------------------------------------------------- #
say "2/4  Connecting to your Instagram account…"
# --------------------------------------------------------------------------- #
read -rp "Your Instagram username (without @): " IG_USER </dev/tty
IG_USER="${IG_USER#@}"
read -rp "Browser where you're logged in to Instagram [chrome/safari/firefox/brave/edge] (chrome): " BROWSER </dev/tty
BROWSER="$(echo "${BROWSER:-chrome}" | tr '[:upper:]' '[:lower:]')"

echo "Reading your Instagram login from $BROWSER."
echo "(If macOS asks for your password to access '$BROWSER Safe Storage', click Always Allow.)"
if ! "$APP_DIR/venv/bin/instaloader" --quiet --load-cookies "$BROWSER" \
     --sessionfile "$APP_DIR/session" >/dev/null 2>&1 || [ ! -s "$APP_DIR/session" ]; then
  echo
  echo "Couldn't read the login from $BROWSER automatically. Let's do it by hand:"
  echo "  1. Open instagram.com in your browser (logged in)."
  echo "  2. Open the developer tools (⌥⌘I) → Application (Safari/Firefox: Storage) → Cookies."
  echo "  3. Copy the values of the cookies named sessionid and csrftoken."
  read -rp "sessionid: " IG_SESSIONID </dev/tty
  read -rp "csrftoken: " IG_CSRFTOKEN </dev/tty
  "$APP_DIR/venv/bin/python" - "$IG_USER" "$APP_DIR/session" "$IG_SESSIONID" "$IG_CSRFTOKEN" <<'PY'
import sys, urllib.parse, instaloader
user, path, sessionid, csrftoken = sys.argv[1:]
loader = instaloader.Instaloader(quiet=True)
loader.load_session(user, {
    "sessionid": sessionid,
    "csrftoken": csrftoken,
    "ds_user_id": urllib.parse.unquote(sessionid).split(":")[0],
})
loader.save_session_to_file(path)
PY
fi
# Check the login works and belongs to the right account.
"$APP_DIR/venv/bin/python" - "$IG_USER" "$APP_DIR/session" <<'PY'
import sys, instaloader
user, path = sys.argv[1:]
loader = instaloader.Instaloader(quiet=True)
loader.load_session_from_file(user, path)
who = loader.test_login()
if who != user:
    found = "@%s" % who if who else "no account"
    sys.exit("That login belongs to %s, not @%s. Log in to Instagram as @%s and run this again." % (found, user, user))
PY
chmod 600 "$APP_DIR/session"
echo "Connected as @$IG_USER."

# --------------------------------------------------------------------------- #
say "3/4  Setting up the daily download…"
# --------------------------------------------------------------------------- #
{
  printf 'IG_USER=%q\n' "$IG_USER"
  printf 'PHOTOS_DIR=%q\n' "$PHOTOS_DIR"
} > "$APP_DIR/config"

cat > "$APP_DIR/run.sh" <<'RUN'
#!/bin/bash
# Downloads posts newly saved on Instagram into PHOTOS_DIR.
# launchd starts it at login and every hour; it does the work once a day.
#   bash ~/.insta-saved/run.sh          normal daily run
#   bash ~/.insta-saved/run.sh --all    also fetch older saves (slow, run by hand)
APP_DIR="$HOME/.insta-saved"
source "$APP_DIR/config"
LOG="$APP_DIR/log.txt"
TODAY="$(date +%F)"

if [ "$1" != "--all" ]; then
  [ "$(cat "$APP_DIR/last-success" 2>/dev/null)" = "$TODAY" ] && exit 0
  EXTRA=(--fast-update --count 100)
fi
# Offline (just woke up, no Wi-Fi yet)? Try again next hour, quietly.
curl -s -o /dev/null --max-time 10 https://www.instagram.com || exit 0

echo "--- $(date)" >> "$LOG"
MARKER="$(mktemp)"
mkdir -p "$PHOTOS_DIR"
"$APP_DIR/venv/bin/instaloader" --quiet \
  --login "$IG_USER" --sessionfile "$APP_DIR/session" \
  --dirname-pattern "$PHOTOS_DIR" --filename-pattern "{profile}_{shortcode}" \
  --no-videos --no-video-thumbnails --no-captions --no-metadata-json --no-profile-pic \
  "${EXTRA[@]}" :saved >> "$LOG" 2>&1
STATUS=$?

# Instaloader dates each file to when the post was published (often years ago).
# Re-date new files to now, so they show up as today in Google Photos.
find "$PHOTOS_DIR" -type f -cnewer "$MARKER" -exec touch {} + 2>/dev/null
rm -f "$MARKER"

if [ $STATUS -eq 0 ]; then
  echo "$TODAY" > "$APP_DIR/last-success"
  echo "ok" >> "$LOG"
elif [ "$(cat "$APP_DIR/last-alert" 2>/dev/null)" != "$TODAY" ]; then
  echo "$TODAY" > "$APP_DIR/last-alert"
  osascript -e 'display notification "Couldn'"'"'t download your saved posts. Your Instagram login has probably expired: run the installer again." with title "Instagram Saved"'
fi
RUN
chmod +x "$APP_DIR/run.sh"

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$APP_DIR/run.sh</string></array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>3600</integer>
  <key>StandardErrorPath</key><string>$APP_DIR/launchd.log</string>
</dict>
</plist>
PLIST

# --------------------------------------------------------------------------- #
say "4/4  First download (your 100 most recent saves)…"
# --------------------------------------------------------------------------- #
rm -f "$APP_DIR/last-success"
bash "$APP_DIR/run.sh"
if [ "$(cat "$APP_DIR/last-success" 2>/dev/null)" != "$(date +%F)" ]; then
  echo "The first download failed. Last lines of the log:"
  tail -n 15 "$APP_DIR/log.txt"
  exit 1
fi
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

COUNT="$(find "$PHOTOS_DIR" -type f | wc -l | tr -d ' ')"
say "Done. $COUNT images are in ~/Pictures/Instagram Saved."
cat <<'NEXT'

Last step, in Google Chrome:
  1. Go to photos.google.com → Upload (top right) → Back up folders
     → choose Pictures/Instagram Saved → allow access.
  2. Chrome menu ⋮ → Cast, save, and share → Install page as app.
  3. System Settings → General → Login Items → +
     → your home folder → Applications → Chrome Apps → Google Photos.
Google Photos now opens when you log in and uploads new saves on its own.
NEXT
open "$PHOTOS_DIR"
