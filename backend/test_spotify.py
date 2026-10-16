import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load the .env file located beside this script.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: Spotify credentials are missing.")
        print("Check SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env.")
        return

    print("Requesting Spotify access token...")

    try:
        token_response = requests.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(CLIENT_ID, CLIENT_SECRET),
            timeout=20,
        )

        if token_response.status_code != 200:
            print("Spotify authentication failed.")
            print("HTTP status:", token_response.status_code)
            print("Response:", token_response.text[:500])
            return

        access_token = token_response.json()["access_token"]
        print("Authentication successful!")

        print("\nSearching Spotify for a test song...")

        search_response = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "q": "track:Earthquake artist:Ferdous",
                "type": "track",
                "limit": 3,
                "market": "US",
            },
            timeout=20,
        )

        if search_response.status_code != 200:
            print("Spotify search failed.")
            print("HTTP status:", search_response.status_code)
            print("Response:", search_response.text[:500])
            return

        tracks = search_response.json().get("tracks", {}).get("items", [])

        if not tracks:
            print("Authentication worked, but no matching tracks were found.")
            return

        print("\nSearch results:")
        for index, track in enumerate(tracks, start=1):
            artists = ", ".join(
                artist["name"] for artist in track.get("artists", [])
            )
            print(f"\n{index}. {track['name']} — {artists}")
            print("   Spotify URL:", track.get("external_urls", {}).get("spotify"))
            print("   Track ID:", track.get("id"))

        print("\nTest complete. No database records were changed.")

    except requests.RequestException as exc:
        print("Could not connect to Spotify:", exc)


if __name__ == "__main__":
    main()