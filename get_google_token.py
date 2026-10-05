"""One-time helper: sign in to Google and print the refresh token for sync.py.

Run this on your own computer (it opens a browser window):

    python get_google_token.py path/to/client_secret.json
"""

import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    # Upload photos and create albums.
    "https://www.googleapis.com/auth/photoslibrary.appendonly",
    # Find the album this tool created on an earlier run.
    "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    secrets_file = sys.argv[1]
    flow = InstalledAppFlow.from_client_secrets_file(secrets_file, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    client = json.load(open(secrets_file))["installed"]

    print("\nAdd these three values as secrets (see README.md):\n")
    print(f"GOOGLE_CLIENT_ID      = {client['client_id']}")
    print(f"GOOGLE_CLIENT_SECRET  = {client['client_secret']}")
    print(f"GOOGLE_REFRESH_TOKEN  = {creds.refresh_token}")


if __name__ == "__main__":
    main()
