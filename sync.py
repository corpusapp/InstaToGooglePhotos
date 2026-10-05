"""Copy the posts you saved on Instagram into a Google Photos album.

Run with no arguments for a normal daily sync: it walks your saved posts from
newest to oldest, stops at the first one it has already copied, and uploads
everything newer than that. Use --backfill once to work through older saves.

Configuration comes from environment variables (see README.md).
"""

import argparse
import json
import mimetypes
import os
import sys
import time
from pathlib import Path

import instaloader
import requests

STATE_FILE = Path(os.environ.get("STATE_FILE", "state/synced.json"))
ALBUM_TITLE = os.environ.get("GPHOTOS_ALBUM_TITLE", "Instagram Saved")
INCLUDE_VIDEOS = os.environ.get("INCLUDE_VIDEOS", "false").lower() == "true"

PHOTOS_API = "https://photoslibrary.googleapis.com/v1"


def log(msg):
    print(msg, flush=True)


def env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Missing environment variable {name} (see README.md)")
    return value


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"album_id": None, "synced": []}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1) + "\n")


# --------------------------------------------------------------------------- #
# Instagram
# --------------------------------------------------------------------------- #

def instagram_saved_posts():
    username = env("IG_USERNAME")
    sessionid = env("IG_SESSIONID")
    loader = instaloader.Instaloader(quiet=True, resume_prefix=None, save_metadata=False)
    loader.load_session(username, {
        "sessionid": sessionid,
        "csrftoken": env("IG_CSRFTOKEN"),
        # The sessionid cookie starts with the numeric user id.
        "ds_user_id": requests.utils.unquote(sessionid).split(":")[0],
    })
    if loader.test_login() != username:
        sys.exit("Instagram session is not valid any more: refresh IG_SESSIONID / IG_CSRFTOKEN.")
    profile = instaloader.Profile.from_username(loader.context, username)
    return profile.get_saved_posts()


def media_of(post):
    """Yield (url, is_video) for every image/video in a post."""
    if post.typename == "GraphSidecar":
        for node in post.get_sidecar_nodes():
            yield (node.video_url, True) if node.is_video else (node.display_url, False)
    elif post.is_video:
        yield post.video_url, True
    else:
        yield post.url, False


def collect_new_posts(posts, synced, limit, backfill):
    """Return unsynced posts, newest first, at most `limit` of them."""
    new = []
    for post in posts:
        if post.shortcode in synced:
            if backfill:
                continue
            break
        new.append(post)
        if len(new) >= limit:
            break
    return new


# --------------------------------------------------------------------------- #
# Google Photos
# --------------------------------------------------------------------------- #

class GooglePhotos:
    def __init__(self):
        resp = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": env("GOOGLE_CLIENT_ID"),
            "client_secret": env("GOOGLE_CLIENT_SECRET"),
            "refresh_token": env("GOOGLE_REFRESH_TOKEN"),
            "grant_type": "refresh_token",
        }, timeout=30)
        if resp.status_code != 200:
            sys.exit(f"Could not refresh the Google token: {resp.text}")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"

    def _call(self, method, path, **kwargs):
        resp = self.session.request(method, f"{PHOTOS_API}/{path}", timeout=120, **kwargs)
        resp.raise_for_status()
        return resp

    def find_or_create_album(self, title):
        # Google only lets an app see albums it created itself, which is exactly
        # what we want: this finds the album from a previous run.
        page_token = None
        while True:
            params = {"pageSize": 50, "excludeNonAppCreatedData": "true"}
            if page_token:
                params["pageToken"] = page_token
            data = self._call("GET", "albums", params=params).json()
            for album in data.get("albums", []):
                if album.get("title") == title:
                    return album["id"]
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return self._call("POST", "albums", json={"album": {"title": title}}).json()["id"]

    def upload(self, content, filename, mime_type):
        resp = self._call("POST", "uploads", data=content, headers={
            "Content-Type": "application/octet-stream",
            "X-Goog-Upload-Content-Type": mime_type,
            "X-Goog-Upload-Protocol": "raw",
        })
        return resp.text

    def add_to_album(self, album_id, items):
        """items: list of (upload_token, filename, description)."""
        body = {
            "albumId": album_id,
            "newMediaItems": [
                {
                    "description": description[:1000],
                    "simpleMediaItem": {"uploadToken": token, "fileName": filename},
                }
                for token, filename, description in items
            ],
        }
        results = self._call("POST", "mediaItems:batchCreate", json=body).json()
        for result in results.get("newMediaItemResults", []):
            status = result.get("status", {})
            if status.get("code", 0) != 0:
                raise RuntimeError(f"Google Photos rejected an item: {status}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def describe(post):
    caption = (post.caption or "").strip()
    header = f"@{post.owner_username} · https://www.instagram.com/p/{post.shortcode}/"
    return f"{header}\n\n{caption}" if caption else header


def sync_post(post, photos, album_id):
    items = []
    for index, (url, is_video) in enumerate(media_of(post), start=1):
        if is_video and not INCLUDE_VIDEOS:
            continue
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        mime_type = resp.headers.get("Content-Type", "").split(";")[0] or (
            "video/mp4" if is_video else "image/jpeg")
        ext = mimetypes.guess_extension(mime_type) or (".mp4" if is_video else ".jpg")
        filename = f"{post.owner_username}_{post.shortcode}_{index}{ext}"
        items.append((photos.upload(resp.content, filename, mime_type), filename, describe(post)))
    if items:
        photos.add_to_album(album_id, items)
    return len(items)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=int(os.environ.get("MAX_POSTS_PER_RUN", 50)),
                        help="maximum number of new posts to copy in one run (default 50)")
    parser.add_argument("--backfill", action="store_true",
                        help="look through all saved posts, not just the ones newer than the last sync")
    parser.add_argument("--dry-run", action="store_true",
                        help="list what would be copied without uploading anything")
    args = parser.parse_args()

    state = load_state()
    synced = set(state["synced"])

    log("Reading saved posts from Instagram…")
    new_posts = collect_new_posts(instagram_saved_posts(), synced, args.limit, args.backfill)
    log(f"{len(new_posts)} new saved post(s) to copy.")
    if not new_posts or args.dry_run:
        for post in new_posts:
            log(f"  would copy https://www.instagram.com/p/{post.shortcode}/")
        return

    photos = GooglePhotos()
    if not state["album_id"]:
        state["album_id"] = photos.find_or_create_album(ALBUM_TITLE)
        save_state(state)

    # Oldest first, saving progress after each post, so an interrupted run
    # resumes cleanly and the album stays in the order you saved things.
    copied = 0
    for post in reversed(new_posts):
        count = sync_post(post, photos, state["album_id"])
        state["synced"].append(post.shortcode)
        save_state(state)
        copied += 1
        log(f"  copied {post.shortcode} by @{post.owner_username} ({count} file(s))")
        time.sleep(2)  # be gentle with Instagram
    log(f"Done: {copied} post(s) added to the '{ALBUM_TITLE}' album.")


if __name__ == "__main__":
    main()
