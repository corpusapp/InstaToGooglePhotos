# Insta → Google Photos

Copies the posts you **saved** on Instagram (the bookmark icon) to Google Photos, every
day, without you doing anything.

There are two versions. **Start with the Mac one**: no Google Cloud setup, no keys
to copy around, about 5 minutes.

| | **Mac version** (recommended) | Cloud version (advanced) |
| --- | --- | --- |
| Setup | one script + 3 clicks in Google Photos | Google Cloud project, OAuth, 6 GitHub secrets |
| Runs | when your Mac is open (once a day) | on GitHub's servers, Mac can be off |
| Google Photos | uploaded to your library | uploaded to an album with captions & links |
| Instagram | runs from your home connection (less likely to be blocked) | runs from GitHub's servers (more likely to be blocked) |

## Mac version

```
your Mac, once a day (at login or when it wakes up)
  └─ Instaloader downloads new saves ─→ ~/Pictures/Instagram Saved
                                           └─ Google Photos (open in Chrome) uploads new files
```

### Setup

1. Make sure you're logged in to <https://www.instagram.com> in your browser (Chrome is
   simplest).
2. Download [`mac/install.sh`](mac/install.sh) (on GitHub: open it → **Download raw file**).
3. Open **Terminal** and run:

   ```bash
   bash ~/Downloads/install.sh
   ```

   It asks for your Instagram username and your browser, reads your Instagram login from
   the browser (macOS may ask for your password: click **Always Allow**), then downloads
   your 100 most recent saves into `~/Pictures/Instagram Saved`.
4. Hand that folder to Google Photos, in **Google Chrome**:
   1. <https://photos.google.com> → **Upload** (top right) → **Back up folders** → choose
      `Pictures/Instagram Saved` → allow access.
   2. Chrome menu **⋮ → Cast, save, and share → Install page as app**.
   3. **System Settings → General → Login Items → +** → in the Finder sidebar pick your
      home folder → *Applications → Chrome Apps → Google Photos*.

That's it. Each day, the first time your Mac is awake and online, new saves are
downloaded. Google Photos opens at login and uploads them. It only uploads while the
Google Photos window is open, so leave it open (minimised is fine) for a few minutes.

### Good to know

- **Private accounts work.** It logs in as you, so it sees exactly what you see.
- **Photos only.** Reels and videos are skipped. To include them, remove `--no-videos`
  from `~/.insta-saved/run.sh`.
- New saves show up in Google Photos **dated the day they were downloaded**, not the
  day they were originally posted.
- **Older saves:** to download everything you ever saved (can take a while), run
  `bash ~/.insta-saved/run.sh --all` once.
- **If the Instagram login expires**, the Mac shows a notification. Log in to Instagram
  in your browser again and rerun the installer. Your photos stay where they are.
- What happened: `~/.insta-saved/log.txt`.
- **Uninstall:**
  ```bash
  launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.instasaved.daily.plist
  rm -rf ~/.insta-saved ~/Library/LaunchAgents/com.instasaved.daily.plist
  ```
- Instagram has no official way to read saved posts. This uses
  [Instaloader](https://instaloader.github.io/), which reads your account the way your
  browser does. That's against Instagram's terms, so keep it to normal daily use.

## Cloud version (advanced)

Runs every morning on GitHub Actions, so your computer can be off, and puts everything
in a Google Photos album called **Instagram Saved**. Each photo's description holds the
author, a link to the original post and its caption. It does nothing until you add the
secrets below.

```
GitHub Actions (every day, 06:17 UTC)
  └─ sync.py
       1. signs in to Instagram with your browser session  ─→ lists your saved posts
       2. stops at the first post it already copied
       3. downloads the new images
       4. uploads them to Google Photos  ─→ album "Instagram Saved"
       5. writes the copied post IDs to state/synced.json (committed to the repo)
```

### Read this first

- **Instagram has no official way to read your saved posts.** This tool uses
  [Instaloader](https://instaloader.github.io/), which reads your account the way your
  browser does. That is against Instagram's terms, and Instagram can log the session out
  or ask you to confirm it's you. Keep the volume low (the default is 50 posts a run) and
  if Instagram ever complains, stop and run the tool from your own computer instead
  (see [Running on your own computer](#running-sync-py-on-your-own-computer)).
- **Google Photos only lets apps add photos and manage albums the app created.** That's
  fine here: the tool creates its own album and only ever adds to it.
- **Private accounts work.** The tool signs in as you, so it sees exactly what you see,
  including saves from private accounts you follow. Nothing is made public: the
  Google Photos album is private to your Google account.
- Instagram serves images at up to 1080 px wide. That is the best quality you'll get.
- **Keep this repository private**: it holds the list of posts you saved.

### Setup (≈ 20 minutes, once)

#### 1. Get your Instagram session cookies

1. On a computer, log in to <https://www.instagram.com> in Chrome, Edge or Firefox.
2. Open the developer tools (`F12`, or `⌥⌘I` on Mac) → **Application** tab (Firefox:
   **Storage**) → **Cookies** → `https://www.instagram.com`.
3. Copy the **Value** of two cookies:
   - `sessionid`
   - `csrftoken`

Don't click "Log out" in that browser afterwards: logging out kills the session.
If you want, use a private/incognito window and just close it.

#### 2. Create a Google Cloud project for Google Photos

1. Go to <https://console.cloud.google.com/> and create a project (e.g. "Insta to Photos").
2. **APIs & Services → Library** → search **Photos Library API** → **Enable**.
3. **APIs & Services → OAuth consent screen** (Google Auth Platform):
   - User type **External**, app name anything, your email as support and developer contact.
   - **Audience**: add your Gmail address as a test user.
   - Then click **Publish app** (status "In production"). You do not need Google to verify
     it. This step matters: while an app is in "Testing", Google expires its sign-in
     after 7 days and the daily sync would stop working.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID** →
   type **Desktop app** → **Download JSON** (a `client_secret_….json` file).

#### 3. Get the Google refresh token

On your computer, with Python 3 installed:

```bash
git clone <this repo> && cd InstaToGooglePhotos
pip install -r requirements.txt
python get_google_token.py ~/Downloads/client_secret_XXXX.json
```

A browser opens. Sign in with the Google account whose Photos you want to fill.
Google warns that the app isn't verified: click **Advanced → Go to … (unsafe)**. It's
your own app. Then allow access. The terminal prints three values.

#### 4. Add the secrets to GitHub

In this repository: **Settings → Secrets and variables → Actions → New repository secret**.
Add six secrets:

| Secret | Value |
| --- | --- |
| `IG_USERNAME` | your Instagram username (without `@`) |
| `IG_SESSIONID` | the `sessionid` cookie |
| `IG_CSRFTOKEN` | the `csrftoken` cookie |
| `GOOGLE_CLIENT_ID` | printed by `get_google_token.py` |
| `GOOGLE_CLIENT_SECRET` | printed by `get_google_token.py` |
| `GOOGLE_REFRESH_TOKEN` | printed by `get_google_token.py` |

Optional, under the **Variables** tab:

| Variable | Default | Meaning |
| --- | --- | --- |
| `GPHOTOS_ALBUM_TITLE` | `Instagram Saved` | name of the album |
| `INCLUDE_VIDEOS` | `false` | set to `true` to copy reels and videos too |

#### 5. Test it

**Actions** tab → **Daily Instagram → Google Photos sync** → **Run workflow**.
After a minute or two the album appears in Google Photos with your 50 most recent saves.

From then on it runs on its own every morning. GitHub emails you if a run fails.

### Older saves (backfill)

A normal run only copies what you saved since the last run (and on the first run, your
50 most recent saves). To bring in older saves, run the workflow by hand with
**backfill** ticked. Each run copies up to *limit* more posts. Repeat it until it reports
"0 new saved post(s)". Keep the limit modest (50–200) so Instagram doesn't notice.

### When something breaks

| Message in the Actions log | Fix |
| --- | --- |
| `Instagram session is not valid any more` | Log in to Instagram in your browser again and update `IG_SESSIONID` and `IG_CSRFTOKEN`. |
| `401`, `429` or "Please wait a few minutes" from Instagram | Instagram is rate-limiting GitHub's servers. Wait a day, or run it from your own computer. |
| `Could not refresh the Google token` with `invalid_grant` | The app was still in "Testing" (step 2.3), or you removed its access. Publish it and rerun `get_google_token.py`. |

### Running sync.py on your own computer

Instagram trusts your home connection more than GitHub's servers. If GitHub keeps
getting blocked, run the same script on a Mac, a PC or a Raspberry Pi that's on in the
morning:

```bash
cp .env.example .env    # fill in the six values
set -a; source .env; set +a
python sync.py --dry-run    # shows what it would copy
python sync.py
```

To run it every morning at 8:00, add this line with `crontab -e` (macOS/Linux):

```
0 8 * * * cd /path/to/InstaToGooglePhotos && set -a && . ./.env && set +a && /usr/bin/python3 sync.py >> sync.log 2>&1
```

If you switch to your own computer, disable the GitHub workflow
(**Actions → the workflow → ⋯ → Disable workflow**) and copy `state/synced.json` from
the repo so it doesn't upload the same posts twice.

### Options

```
python sync.py [--limit N] [--backfill] [--dry-run]

  --limit N    maximum number of new posts to copy in one run (default 50)
  --backfill   look through all saved posts, not just the ones newer than the last sync
  --dry-run    list what would be copied without uploading anything
```
