import os
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("SPOTIFY_CLIENT_ID")
client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

if not client_id or not client_secret:
    raise SystemExit("Missing Spotify credentials in .env")

token_response = requests.post(
    "https://accounts.spotify.com/api/token",
    data={"grant_type": "client_credentials"},
    auth=(client_id, client_secret),
    timeout=20,
)

print("Token endpoint status:", token_response.status_code)

if token_response.status_code != 200:
    print("Token error:", token_response.text[:500])
    raise SystemExit(1)

token = token_response.json()["access_token"]

response = requests.get(
    "https://api.spotify.com/v1/search",
    headers={"Authorization": f"Bearer {token}"},
    params={
        "q": 'track:"Earthquake" artist:"Ferdous"',
        "type": "track",
        "limit": 1,
        "market": "US",
    },
    timeout=20,
)

print("Search endpoint status:", response.status_code)
print("Response:", response.text[:1000])
print("Retry-After:", response.headers.get("Retry-After"))
print("Rate-limit headers:", {
    key: value
    for key, value in response.headers.items()
    if "rate" in key.lower() or "retry" in key.lower()
})