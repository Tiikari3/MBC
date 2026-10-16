import os
import re
import statistics
from datetime import datetime, date, timedelta
from typing import Optional

import bcrypt
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, HttpUrl
from sqlalchemy import inspect, text
from sqlmodel import SQLModel, Field, Session, create_engine, select

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-dev-key-for-local-testing")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_MARKET = os.getenv("SPOTIFY_MARKET", "US")

# Thursday theme rotation begins with the oldest-created Moosic user on
# Thursday, September 17, 2026. Change this date if you want a different
# starting point for the rotation.
ROTATION_START_DATE = date(2026, 9, 17)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///mbc_local.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    hashed_password: str


class Song(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    artist: str
    submitter_id: int
    submission_date: date
    spotify_url: Optional[str] = None
    spotify_track_id: Optional[str] = None


class Vote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    song_id: int
    voter_id: int
    score: int


class SongCreate(BaseModel):
    title: str
    artist: str
    spotify_url: Optional[str] = None
    spotify_track_id: Optional[str] = None
    submission_date: Optional[date] = None


class SongUpdate(BaseModel):
    title: str
    artist: str
    spotify_url: Optional[str] = None
    spotify_track_id: Optional[str] = None


class VoteCreate(BaseModel):
    song_id: int
    score: int


class ProfileUpdate(BaseModel):
    new_username: str
    new_password: Optional[str] = None


class SpotifyUrlRequest(BaseModel):
    url: HttpUrl


class FridayThemeProposal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: str
    proposer_id: int = Field(index=True)
    status: str = Field(default="pending", index=True)  # pending, approved, denied
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class FridayThemeProposalVote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    proposal_id: int = Field(index=True)
    voter_id: int = Field(index=True)
    in_favor: bool


class FridayThemeWheelSelection(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    proposal_id: int = Field(index=True, unique=True)
    selected_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    spun_by_id: int


class FridayThemeProposalCreate(BaseModel):
    name: str
    description: str


class FridayThemeVoteCreate(BaseModel):
    in_favor: bool


def get_session():
    with Session(engine) as session:
        yield session


def ensure_database_columns():
    """Add Spotify columns to existing song tables without destroying data."""
    inspector = inspect(engine)
    if not inspector.has_table("song"):
        return

    existing = {c["name"] for c in inspector.get_columns("song")}
    backend = engine.url.get_backend_name()

    with engine.begin() as connection:
        if "spotify_url" not in existing:
            if backend == "postgresql":
                connection.execute(
                    text("ALTER TABLE song ADD COLUMN IF NOT EXISTS spotify_url TEXT")
                )
            else:
                connection.execute(
                    text("ALTER TABLE song ADD COLUMN spotify_url TEXT")
                )

        if "spotify_track_id" not in existing:
            if backend == "postgresql":
                connection.execute(
                    text("ALTER TABLE song ADD COLUMN IF NOT EXISTS spotify_track_id TEXT")
                )
            else:
                connection.execute(
                    text("ALTER TABLE song ADD COLUMN spotify_track_id TEXT")
                )


def create_access_token(data: dict):
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8")
    )


def get_password_hash(password):
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")
optional_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/login",
    auto_error=False
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = session.exec(
        select(User).where(User.username == username)
    ).first()

    if user is None:
        raise credentials_exception

    return user


def get_optional_user(
    token: Optional[str] = Depends(optional_oauth2_scheme),
    session: Session = Depends(get_session)
):
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None

    return session.exec(
        select(User).where(User.username == username)
    ).first()


def extract_spotify_track_id(url: str) -> str:
    uri_match = re.match(r"^spotify:track:([A-Za-z0-9]+)$", url)
    if uri_match:
        return uri_match.group(1)

    web_match = re.search(
        r"open\.spotify\.com/track/([A-Za-z0-9]+)",
        url
    )

    if web_match:
        return web_match.group(1)

    raise HTTPException(
        status_code=400,
        detail="Invalid Spotify track URL. Please paste a Spotify track link.",
    )


def get_spotify_access_token() -> str:
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Spotify API credentials are not configured on the server.",
        )

    try:
        response = httpx.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
            timeout=10.0,
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Unable to connect to Spotify."
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Spotify authentication failed."
        )

    token = response.json().get("access_token")
    if not token:
        raise HTTPException(
            status_code=502,
            detail="Spotify did not return an access token."
        )

    return token


def is_thursday(target_date: date) -> bool:
    return target_date.weekday() == 3


def get_rotation_users(session: Session):
    # User IDs follow account-creation order, which gives us a stable
    # rotation order without hard-coding everyone's usernames.
    return sorted(
        session.exec(select(User)).all(),
        key=lambda user: (user.id or 0)
    )


def get_skipped_dates_before(
    target_date: date,
    session: Session
):
    return session.exec(
        select(ThursdayTheme).where(
            ThursdayTheme.target_date >= ROTATION_START_DATE,
            ThursdayTheme.target_date < target_date,
            ThursdayTheme.status == "skipped"
        )
    ).all()


def get_expected_proposer(
    target_date: date,
    session: Session
):
    users = get_rotation_users(session)
    if not users:
        return None

    if target_date < ROTATION_START_DATE:
        return users[0]

    weeks_since_start = (target_date - ROTATION_START_DATE).days // 7
    skipped_count = len(
        get_skipped_dates_before(target_date, session)
    )

    active_turn_index = max(0, weeks_since_start - skipped_count)
    return users[active_turn_index % len(users)]


def get_theme_record(
    target_date: date,
    session: Session
):
    return session.exec(
        select(ThursdayTheme).where(
            ThursdayTheme.target_date == target_date
        )
    ).first()


def build_theme_response(
    target_date: date,
    session: Session,
    current_user: Optional[User] = None
):
    if not is_thursday(target_date):
        raise HTTPException(
            status_code=400,
            detail="Thursday themes can only be assigned to Thursdays."
        )

    users = get_rotation_users(session)
    id_to_username = {
        user.id: user.username
        for user in users
    }

    theme = get_theme_record(target_date, session)
    expected_proposer = get_expected_proposer(target_date, session)

    if theme:
        proposer_id = theme.proposer_id
        status_value = theme.status
        name = theme.name
        description = theme.description
    else:
        proposer_id = expected_proposer.id if expected_proposer else None
        status_value = "pending"
        name = None
        description = None

    votes = []
    yes_count = 0
    no_count = 0
    current_user_vote = None

    if theme:
        theme_votes = session.exec(
            select(ThursdayThemeVote).where(
                ThursdayThemeVote.theme_id == theme.id
            )
        ).all()

        for vote in theme_votes:
            username = id_to_username.get(
                vote.voter_id,
                "Unknown"
            )

            if vote.in_favor:
                yes_count += 1
            else:
                no_count += 1

            if current_user and vote.voter_id == current_user.id:
                current_user_vote = vote.in_favor

            votes.append({
                "username": username,
                "in_favor": vote.in_favor,
            })

    majority_needed = (len(users) // 2) + 1 if users else 0

    return {
        "date": target_date.isoformat(),
        "exists": theme is not None,
        "id": theme.id if theme else None,
        "name": name,
        "description": description,
        "status": status_value,
        "proposer_id": proposer_id,
        "proposer_username": id_to_username.get(proposer_id),
        "expected_proposer_id": expected_proposer.id if expected_proposer else None,
        "expected_proposer_username": expected_proposer.username if expected_proposer else None,
        "votes": sorted(
            votes,
            key=lambda item: item["username"].lower()
        ),
        "yes_count": yes_count,
        "no_count": no_count,
        "vote_count": yes_count + no_count,
        "user_count": len(users),
        "majority_needed": majority_needed,
        "current_user_vote": current_user_vote,
    }


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)
    ensure_database_columns()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):
    user = session.exec(
        select(User).where(User.username == form_data.username)
    ).first()

    if not user or not verify_password(
        form_data.password,
        user.hashed_password
    ):
        raise HTTPException(
            status_code=400,
            detail="Incorrect username or password"
        )

    access_token = create_access_token({"sub": user.username})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
    }


@app.put("/api/users/update-profile")
def update_profile(
    update_data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    existing_user = session.exec(
        select(User).where(
            User.username == update_data.new_username
        )
    ).first()

    if existing_user and existing_user.id != current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Username is already taken."
        )

    current_user.username = update_data.new_username

    if update_data.new_password:
        current_user.hashed_password = get_password_hash(
            update_data.new_password
        )

    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    new_token = create_access_token({"sub": current_user.username})

    return {
        "status": "success",
        "message": "Profile updated!",
        "access_token": new_token,
        "username": current_user.username,
    }


@app.get("/api/songs/daily/{target_date}")
def get_daily_songs(
    target_date: date,
    session: Session = Depends(get_session)
):
    songs = session.exec(
        select(Song).where(
            Song.submission_date == target_date
        )
    ).all()

    users = session.exec(select(User)).all()
    id_to_username = {
        user.id: user.username
        for user in users
    }

    song_ids = [song.id for song in songs]
    votes = []

    if song_ids:
        votes = session.exec(
            select(Vote).where(
                Vote.song_id.in_(song_ids)
            )
        ).all()

    votes_by_song = {
        song_id: []
        for song_id in song_ids
    }

    for vote in votes:
        votes_by_song.setdefault(
            vote.song_id,
            []
        ).append(vote)

    result = []

    for song in songs:
        song_votes = votes_by_song.get(
            song.id,
            []
        )
        scores = [vote.score for vote in song_votes]
        average = (
            sum(scores) / len(scores)
            if scores
            else None
        )
        stdev = (
            statistics.stdev(scores)
            if len(scores) > 1
            else 0
        )

        visible_votes = [
            {
                "username": id_to_username.get(
                    vote.voter_id,
                    "Unknown"
                ),
                "score": vote.score,
            }
            for vote in sorted(
                song_votes,
                key=lambda vote: id_to_username.get(
                    vote.voter_id,
                    "Unknown"
                ).lower()
            )
        ]

        result.append({
            "id": song.id,
            "title": song.title,
            "artist": song.artist,
            "submitter_id": song.submitter_id,
            "submittedBy": id_to_username.get(
                song.submitter_id,
                "Unknown"
            ),
            "submission_date": song.submission_date,
            "spotify_url": song.spotify_url,
            "spotify_track_id": song.spotify_track_id,
            "votes": visible_votes,
            "vote_count": len(visible_votes),
            "average": average,
            "stdev": stdev,
        })

    return result


@app.get("/api/votes/me/{target_date}")
def get_my_votes_for_date(
    target_date: date,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    songs = session.exec(
        select(Song).where(
            Song.submission_date == target_date
        )
    ).all()

    song_ids = [song.id for song in songs]

    if not song_ids:
        return {}

    votes = session.exec(
        select(Vote).where(
            Vote.voter_id == current_user.id,
            Vote.song_id.in_(song_ids)
        )
    ).all()

    return {
        vote.song_id: vote.score
        for vote in votes
    }


@app.post("/api/songs/fetch-metadata")
def fetch_spotify_metadata(
    req: SpotifyUrlRequest,
    current_user: User = Depends(get_current_user)
):
    spotify_url = str(req.url)
    track_id = extract_spotify_track_id(spotify_url)
    access_token = get_spotify_access_token()

    try:
        response = httpx.get(
            f"https://api.spotify.com/v1/tracks/{track_id}",
            headers={
                "Authorization": f"Bearer {access_token}"
            },
            params={"market": SPOTIFY_MARKET},
            timeout=10.0,
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Unable to connect to Spotify."
        )

    if response.status_code == 401:
        raise HTTPException(
            status_code=502,
            detail="Spotify authorization was rejected."
        )

    if response.status_code == 403:
        raise HTTPException(
            status_code=403,
            detail="Spotify denied access to this track."
        )

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail="Spotify track not found. Make sure the link points to a track."
        )

    if response.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="Spotify is temporarily rate limiting requests. Please try again shortly."
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Spotify returned HTTP {response.status_code}."
        )

    track = response.json()
    artist_names = ", ".join(
        artist.get("name", "")
        for artist in (track.get("artists") or [])
        if artist.get("name")
    )

    album = track.get("album") or {}
    images = album.get("images") or []
    cover_art_url = (
        images[0].get("url")
        if images
        else None
    )

    return {
        "title": track.get("name"),
        "artist": artist_names,
        "cover_art_url": cover_art_url,
        "spotify_url": spotify_url,
        "spotify_track_id": track_id,
        "album": album.get("name"),
        "duration_ms": track.get("duration_ms"),
        "external_url": (
            track.get("external_urls") or {}
        ).get("spotify"),
    }


@app.post("/api/songs")
def create_song(
    song_in: SongCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    target_date = song_in.submission_date or date.today()

    existing = session.exec(
        select(Song).where(
            Song.submitter_id == current_user.id,
            Song.submission_date == target_date
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="You have already submitted a song for this date. Edit your existing submission instead."
        )

    song = Song(
        title=song_in.title,
        artist=song_in.artist,
        submitter_id=current_user.id,
        submission_date=target_date,
        spotify_url=song_in.spotify_url,
        spotify_track_id=song_in.spotify_track_id,
    )

    session.add(song)
    session.commit()
    session.refresh(song)

    return song


@app.put("/api/songs/{song_id}")
def update_song(
    song_id: int,
    song_in: SongUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    song = session.get(Song, song_id)

    if not song:
        raise HTTPException(
            status_code=404,
            detail="Song not found."
        )

    if song.submitter_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only edit your own song."
        )

    track_changed = (
        song.spotify_track_id != song_in.spotify_track_id
    )

    if track_changed:
        for vote in session.exec(
            select(Vote).where(
                Vote.song_id == song.id
            )
        ).all():
            session.delete(vote)

    song.title = song_in.title
    song.artist = song_in.artist
    song.spotify_url = song_in.spotify_url
    song.spotify_track_id = song_in.spotify_track_id

    session.add(song)
    session.commit()
    session.refresh(song)

    return {
        "id": song.id,
        "title": song.title,
        "artist": song.artist,
        "submitter_id": song.submitter_id,
        "submission_date": song.submission_date,
        "spotify_url": song.spotify_url,
        "spotify_track_id": song.spotify_track_id,
        "votes_reset": track_changed,
    }


@app.delete("/api/songs/{song_id}")
def delete_song(
    song_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    song = session.get(Song, song_id)

    if not song:
        raise HTTPException(
            status_code=404,
            detail="Song not found."
        )

    if song.submitter_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own song."
        )

    votes = session.exec(
        select(Vote).where(
            Vote.song_id == song.id
        )
    ).all()

    for vote in votes:
        session.delete(vote)

    session.delete(song)
    session.commit()

    return {
        "status": "success",
        "message": "Song deleted successfully.",
        "deleted_song_id": song_id,
        "deleted_vote_count": len(votes),
    }


@app.post("/api/votes")
def cast_vote(
    vote: VoteCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    if vote.score < 1 or vote.score > 5:
        raise HTTPException(
            status_code=400,
            detail="Score must be between 1 and 5."
        )

    target_song = session.get(Song, vote.song_id)

    if not target_song:
        raise HTTPException(
            status_code=404,
            detail="Song not found"
        )

    date_songs = session.exec(
        select(Song).where(
            Song.submission_date == target_song.submission_date
        )
    ).all()

    date_song_ids = [song.id for song in date_songs]

    existing_score_vote = session.exec(
        select(Vote).where(
            Vote.voter_id == current_user.id,
            Vote.score == vote.score,
            Vote.song_id.in_(date_song_ids),
            Vote.song_id != vote.song_id,
        )
    ).first()

    if existing_score_vote:
        raise HTTPException(
            status_code=400,
            detail=f"Score {vote.score} is already assigned to another track on this day."
        )

    existing_vote = session.exec(
        select(Vote).where(
            Vote.song_id == vote.song_id,
            Vote.voter_id == current_user.id
        )
    ).first()

    if existing_vote:
        existing_vote.score = vote.score
        session.add(existing_vote)
    else:
        session.add(
            Vote(
                song_id=vote.song_id,
                voter_id=current_user.id,
                score=vote.score
            )
        )

    session.commit()

    return {
        "status": "success",
        "message": "Vote recorded"
    }


@app.delete("/api/votes/{song_id}")
def delete_vote(
    song_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    existing_vote = session.exec(
        select(Vote).where(
            Vote.song_id == song_id,
            Vote.voter_id == current_user.id
        )
    ).first()

    if existing_vote:
        session.delete(existing_vote)
        session.commit()

    return {
        "status": "success",
        "message": "Vote removed"
    }


@app.delete("/api/votes/date/{target_date}")
def clear_date_votes(
    target_date: date,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    songs = session.exec(
        select(Song).where(
            Song.submission_date == target_date
        )
    ).all()

    ids = [song.id for song in songs]

    if ids:
        votes = session.exec(
            select(Vote).where(
                Vote.voter_id == current_user.id,
                Vote.song_id.in_(ids)
            )
        ).all()

        for vote in votes:
            session.delete(vote)

        session.commit()

    return {
        "status": "success",
        "message": "All votes cleared"
    }


# ---------------------------------------------------------------------------
# Thursday Themes
# ---------------------------------------------------------------------------

@app.get("/api/themes/{target_date}")
def get_thursday_theme(
    target_date: date,
    current_user: Optional[User] = Depends(get_optional_user),
    session: Session = Depends(get_session)
):
    return build_theme_response(
        target_date,
        session,
        current_user
    )


@app.get("/api/themes")
def get_thursday_themes(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: Optional[User] = Depends(get_optional_user),
    session: Session = Depends(get_session)
):
    start = start_date or ROTATION_START_DATE
    end = end_date or (start + timedelta(days=12 * 7))

    if end < start:
        raise HTTPException(
            status_code=400,
            detail="end_date must be on or after start_date."
        )

    # Snap the beginning to the first Thursday on/after start.
    current = start + timedelta(
        days=(3 - start.weekday()) % 7
    )

    results = []
    while current <= end:
        results.append(
            build_theme_response(
                current,
                session,
                current_user
            )
        )
        current += timedelta(days=7)

    return results


@app.put("/api/themes/{target_date}")
def create_or_update_thursday_theme(
    target_date: date,
    theme_in: ThursdayThemeUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    if not is_thursday(target_date):
        raise HTTPException(
            status_code=400,
            detail="Themes can only be proposed for Thursdays."
        )

    name = theme_in.name.strip()
    description = theme_in.description.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Theme name cannot be empty."
        )

    if not description:
        raise HTTPException(
            status_code=400,
            detail="Theme description cannot be empty."
        )

    expected_proposer = get_expected_proposer(
        target_date,
        session
    )

    if not expected_proposer:
        raise HTTPException(
            status_code=400,
            detail="No users are available for theme rotation."
        )

    theme = get_theme_record(target_date, session)

    if theme and theme.status == "skipped":
        raise HTTPException(
            status_code=400,
            detail="This Thursday is currently marked as skipped. Unskip it before proposing a theme."
        )

    if current_user.id != expected_proposer.id:
        proposer_name = expected_proposer.username
        raise HTTPException(
            status_code=403,
            detail=f"{proposer_name} is the assigned proposer for this Thursday."
        )

    if theme and theme.proposer_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the assigned proposer can edit this theme."
        )

    if theme and theme.status in {"approved", "denied"}:
        raise HTTPException(
            status_code=400,
            detail="This theme has already been decided and can no longer be edited."
        )

    if theme:
        changed = (
            theme.name != name
            or theme.description != description
        )

        theme.name = name
        theme.description = description
        theme.proposer_id = current_user.id
        theme.status = "pending"
        session.add(theme)

        if changed:
            for theme_vote in session.exec(
                select(ThursdayThemeVote).where(
                    ThursdayThemeVote.theme_id == theme.id
                )
            ).all():
                session.delete(theme_vote)
    else:
        theme = ThursdayTheme(
            target_date=target_date,
            proposer_id=current_user.id,
            name=name,
            description=description,
            status="pending"
        )
        session.add(theme)

    session.commit()
    session.refresh(theme)

    return build_theme_response(
        target_date,
        session,
        current_user
    )


@app.post("/api/themes/{target_date}/vote")
def vote_on_thursday_theme(
    target_date: date,
    vote_in: ThursdayThemeVoteCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    if not is_thursday(target_date):
        raise HTTPException(
            status_code=400,
            detail="Themes can only be voted on for Thursdays."
        )

    theme = get_theme_record(target_date, session)

    if not theme or not theme.name:
        raise HTTPException(
            status_code=400,
            detail="There is no theme proposal to vote on yet."
        )

    if theme.status == "skipped":
        raise HTTPException(
            status_code=400,
            detail="This Thursday is marked as skipped."
        )

    if theme.status in {"approved", "denied"}:
        raise HTTPException(
            status_code=400,
            detail="Voting has already closed for this theme."
        )

    existing_vote = session.exec(
        select(ThursdayThemeVote).where(
            ThursdayThemeVote.theme_id == theme.id,
            ThursdayThemeVote.voter_id == current_user.id
        )
    ).first()

    if existing_vote:
        existing_vote.in_favor = vote_in.in_favor
        session.add(existing_vote)
    else:
        session.add(
            ThursdayThemeVote(
                theme_id=theme.id,
                voter_id=current_user.id,
                in_favor=vote_in.in_favor
            )
        )

    session.commit()

    # Recalculate the decision after every vote.
    users = get_rotation_users(session)
    votes = session.exec(
        select(ThursdayThemeVote).where(
            ThursdayThemeVote.theme_id == theme.id
        )
    ).all()

    yes_count = sum(
        1 for item in votes
        if item.in_favor
    )
    no_count = sum(
        1 for item in votes
        if not item.in_favor
    )

    majority_needed = (
        len(users) // 2 + 1
        if users
        else 0
    )

    if yes_count >= majority_needed:
        theme.status = "approved"
    elif no_count >= majority_needed:
        theme.status = "denied"
    else:
        theme.status = "pending"

    session.add(theme)
    session.commit()

    return build_theme_response(
        target_date,
        session,
        current_user
    )


@app.delete("/api/themes/{target_date}/vote")
def delete_thursday_theme_vote(
    target_date: date,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    theme = get_theme_record(target_date, session)

    if not theme:
        return {
            "status": "success",
            "message": "Theme vote removed"
        }

    if theme.status in {"approved", "denied", "skipped"}:
        raise HTTPException(
            status_code=400,
            detail="Voting is closed for this theme."
        )

    existing_vote = session.exec(
        select(ThursdayThemeVote).where(
            ThursdayThemeVote.theme_id == theme.id,
            ThursdayThemeVote.voter_id == current_user.id
        )
    ).first()

    if existing_vote:
        session.delete(existing_vote)

    session.commit()

    return {
        "status": "success",
        "message": "Theme vote removed"
    }


@app.post("/api/themes/{target_date}/skip")
def set_thursday_theme_skip(
    target_date: date,
    skip_request: ThursdayThemeSkipRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    if not is_thursday(target_date):
        raise HTTPException(
            status_code=400,
            detail="Only Thursdays can be marked as skipped."
        )

    theme = get_theme_record(target_date, session)

    if skip_request.skipped:
        if theme and theme.status in {"approved", "denied"}:
            raise HTTPException(
                status_code=400,
                detail="A theme that has already been decided cannot be skipped."
            )

        if not theme:
            expected_proposer = get_expected_proposer(
                target_date,
                session
            )

            theme = ThursdayTheme(
                target_date=target_date,
                proposer_id=(
                    expected_proposer.id
                    if expected_proposer
                    else None
                ),
                name=None,
                description=None,
                status="skipped"
            )
            session.add(theme)
        else:
            theme.status = "skipped"
            session.add(theme)

            for theme_vote in session.exec(
                select(ThursdayThemeVote).where(
                    ThursdayThemeVote.theme_id == theme.id
                )
            ).all():
                session.delete(theme_vote)

    else:
        if not theme:
            expected_proposer = get_expected_proposer(
                target_date,
                session
            )

            theme = ThursdayTheme(
                target_date=target_date,
                proposer_id=(
                    expected_proposer.id
                    if expected_proposer
                    else None
                ),
                name=None,
                description=None,
                status="pending"
            )
            session.add(theme)
        elif theme.status == "skipped":
            theme.status = "pending"
            theme.name = None
            theme.description = None
            theme.proposer_id = (
                get_expected_proposer(
                    target_date,
                    session
                ).id
                if get_expected_proposer(
                    target_date,
                    session
                )
                else None
            )
            session.add(theme)
        else:
            raise HTTPException(
                status_code=400,
                detail="This Thursday is not currently skipped."
            )

    session.commit()

    return build_theme_response(
        target_date,
        session,
        current_user
    )


@app.get("/api/history")
def get_history(
    skip: int = 0,
    limit: int = 10,
    specific_date: Optional[str] = None,
    session: Session = Depends(get_session)
):
    users = session.exec(select(User)).all()
    id_to_username = {
        user.id: user.username
        for user in users
    }

    if specific_date:
        try:
            target = date.fromisoformat(specific_date)
            songs = session.exec(
                select(Song).where(
                    Song.submission_date == target
                )
            ).all()
        except ValueError:
            songs = session.exec(select(Song)).all()
    else:
        songs = session.exec(select(Song)).all()

    songs_by_date = {}
    for song in songs:
        songs_by_date.setdefault(
            song.submission_date,
            []
        ).append(song)

    sorted_dates = sorted(
        songs_by_date.keys(),
        reverse=True
    )

    result = []

    for target in sorted_dates[
        skip:skip + limit
    ]:
        day_songs = songs_by_date[target]
        ids = [song.id for song in day_songs]

        votes = (
            session.exec(
                select(Vote).where(
                    Vote.song_id.in_(ids)
                )
            ).all()
            if ids
            else []
        )

        votes_by_song = {
            song_id: []
            for song_id in ids
        }

        for vote in votes:
            votes_by_song[vote.song_id].append(vote)

        leaderboard = []

        for song in day_songs:
            song_votes = votes_by_song[song.id]
            scores = [vote.score for vote in song_votes]
            avg = (
                sum(scores) / len(scores)
                if scores
                else 0
            )
            stdev = (
                statistics.stdev(scores)
                if len(scores) > 1
                else 0
            )

            leaderboard.append({
                "song_id": song.id,
                "title": song.title,
                "artist": song.artist,
                "submittedBy": id_to_username.get(
                    song.submitter_id,
                    "Unknown"
                ),
                "average": avg,
                "stdev": stdev,
                "votes": [
                    {
                        "username": id_to_username.get(
                            vote.voter_id,
                            "Unknown"
                        ),
                        "score": vote.score
                    }
                    for vote in song_votes
                ],
                "spotify_url": song.spotify_url,
                "spotify_track_id": song.spotify_track_id,
            })

        leaderboard.sort(
            key=lambda item: (
                item["average"],
                item["stdev"]
            )
        )

        winner = (
            {"submittedBy": leaderboard[0]["submittedBy"]}
            if leaderboard
            else {"submittedBy": "No votes cast"}
        )

        result.append({
            "date": target,
            "winner": winner,
            "leaderboard": leaderboard
        })

    return result


@app.get("/api/stats")
def get_global_stats(
    days: int = 28,
    session: Session = Depends(get_session)
):
    users = session.exec(select(User)).all()
    songs = session.exec(select(Song)).all()
    votes = session.exec(select(Vote)).all()

    usernames = [user.username for user in users]
    id_to_username = {
        user.id: user.username
        for user in users
    }

    votes_by_song = {
        song.id: []
        for song in songs
    }

    for vote in votes:
        if vote.song_id in votes_by_song:
            votes_by_song[vote.song_id].append(vote)

    songs_by_date = {}
    for song in songs:
        songs_by_date.setdefault(
            song.submission_date,
            []
        ).append(song)

    sorted_dates = sorted(songs_by_date.keys())

    cumulative_wins = {
        username: 0
        for username in usernames
    }

    chart_data = []
    rank_counts = {
        username: {
            1: 0,
            2: 0,
            3: 0,
            4: 0,
            5: 0
        }
        for username in usernames
    }

    sum_avg = {
        username: 0.0
        for username in usernames
    }

    submission_count = {
        username: 0
        for username in usernames
    }

    for target in sorted_dates:
        day_results = []

        for song in songs_by_date[target]:
            song_votes = votes_by_song[song.id]

            if len(song_votes) == len(users):
                scores = [vote.score for vote in song_votes]
                avg = (
                    sum(scores) / len(scores)
                    if scores
                    else 0
                )
                stdev = (
                    statistics.stdev(scores)
                    if len(scores) > 1
                    else 0
                )

                day_results.append({
                    "submitter": id_to_username.get(
                        song.submitter_id,
                        "Unknown"
                    ),
                    "average": avg,
                    "stdev": stdev
                })

        if (
            len(day_results) == len(songs_by_date[target])
            and day_results
        ):
            day_results.sort(
                key=lambda item: (
                    item["average"],
                    item["stdev"]
                )
            )

            cumulative_wins[
                day_results[0]["submitter"]
            ] += 1

            point = {
                "date": target.isoformat(),
                **cumulative_wins
            }

            chart_data.append(point)

            for rank, item in enumerate(
                day_results,
                start=1
            ):
                username = item["submitter"]

                if rank in rank_counts[username]:
                    rank_counts[username][rank] += 1

                sum_avg[username] += item["average"]
                submission_count[username] += 1

    manager_stats = []

    for username in usernames:
        avg = (
            sum_avg[username] / submission_count[username]
            if submission_count[username]
            else 0
        )

        manager_stats.append({
            "manager": username,
            "wins": cumulative_wins[username],
            "sum_avg": round(sum_avg[username], 2),
            "overall_avg": round(avg, 2)
        })

    manager_stats.sort(
        key=lambda item: item["wins"],
        reverse=True
    )

    for index, item in enumerate(
        manager_stats,
        start=1
    ):
        item["place"] = index

    target_dates = (
        sorted_dates[-days:]
        if days > 0
        else sorted_dates
    )

    raw = {
        poster: {
            voter: []
            for voter in usernames
        }
        for poster in usernames
    }

    for target in target_dates:
        for song in songs_by_date[target]:
            poster = id_to_username.get(
                song.submitter_id,
                "Unknown"
            )

            for vote in votes_by_song[song.id]:
                voter = id_to_username.get(
                    vote.voter_id,
                    "Unknown"
                )

                if poster in raw and voter in raw[poster]:
                    raw[poster][voter].append(vote.score)

    matrices = {
        key: {
            poster: {}
            for poster in usernames
        }
        for key in [
            "average",
            "median",
            "stdev",
            "mode",
            "best",
            "worst"
        ]
    }

    for poster in usernames:
        for voter in usernames:
            scores = raw[poster][voter]

            if scores:
                matrices["average"][poster][voter] = round(
                    sum(scores) / len(scores),
                    2
                )
                matrices["median"][poster][voter] = round(
                    statistics.median(scores),
                    2
                )
                matrices["stdev"][poster][voter] = round(
                    statistics.stdev(scores),
                    2
                ) if len(scores) > 1 else 0.0

                try:
                    mode = statistics.mode(scores)
                except statistics.StatisticsError:
                    mode = scores[0]

                matrices["mode"][poster][voter] = round(
                    mode,
                    2
                )
                matrices["best"][poster][voter] = round(
                    min(scores),
                    2
                )
                matrices["worst"][poster][voter] = round(
                    max(scores),
                    2
                )
            else:
                for key in matrices:
                    matrices[key][poster][voter] = 0.0

    return {
        "chart_data": chart_data,
        "manager_stats": manager_stats,
        "rank_counts": rank_counts,
        "matrices": matrices,
        "usernames": usernames,
    }


def _friday_wheel_spinner_usernames() -> set[str]:
    """Comma-separated usernames allowed to spin; configure in backend .env."""
    raw = os.getenv("THEME_WHEEL_SPINNERS", "wheel_admin")
    return {part.strip().casefold() for part in raw.split(",") if part.strip()}


def _require_friday_wheel_spinner(current_user: User) -> None:
    if current_user.username.casefold() not in _friday_wheel_spinner_usernames():
        raise HTTPException(
            status_code=403,
            detail="Only an authorized wheel spinner can spin the theme wheel."
        )


def _friday_proposal_response(
    proposal: FridayThemeProposal,
    session: Session,
    current_user: Optional[User] = None,
) -> dict:
    votes = session.exec(
        select(FridayThemeProposalVote).where(
            FridayThemeProposalVote.proposal_id == proposal.id
        )
    ).all()
    yes_count = sum(1 for vote in votes if vote.in_favor)
    no_count = len(votes) - yes_count
    current_vote = None
    if current_user:
        own_vote = next((vote for vote in votes if vote.voter_id == current_user.id), None)
        if own_vote:
            current_vote = own_vote.in_favor
    proposer = session.get(User, proposal.proposer_id)
    selection = session.exec(
        select(FridayThemeWheelSelection).where(
            FridayThemeWheelSelection.proposal_id == proposal.id
        )
    ).first()
    return {
        "id": proposal.id,
        "name": proposal.name,
        "description": proposal.description,
        "status": proposal.status,
        "proposer_username": proposer.username if proposer else "Unknown",
        "created_at": proposal.created_at.isoformat() + "Z",
        "yes_count": yes_count,
        "no_count": no_count,
        "vote_count": len(votes),
        "current_user_vote": current_vote,
        "selected_at": selection.selected_at.isoformat() + "Z" if selection else None,
        "is_on_wheel": proposal.status == "approved" and selection is None,
    }


@app.get("/api/friday-themes/proposals")
def list_friday_theme_proposals(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    proposals = session.exec(
        select(FridayThemeProposal).order_by(FridayThemeProposal.created_at.desc())
    ).all()
    return [_friday_proposal_response(item, session, current_user) for item in proposals]


@app.post("/api/friday-themes/proposals")
def create_friday_theme_proposal(
    proposal_in: FridayThemeProposalCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    name = proposal_in.name.strip()
    description = proposal_in.description.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Theme name cannot be empty.")
    if not description:
        raise HTTPException(status_code=400, detail="Theme description cannot be empty.")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Theme name must be 100 characters or fewer.")
    if len(description) > 1000:
        raise HTTPException(status_code=400, detail="Description must be 1,000 characters or fewer.")

    proposal = FridayThemeProposal(
        name=name,
        description=description,
        proposer_id=current_user.id,
        status="pending",
    )
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    return _friday_proposal_response(proposal, session, current_user)


@app.post("/api/friday-themes/proposals/{proposal_id}/vote")
def vote_on_friday_theme_proposal(
    proposal_id: int,
    vote_in: FridayThemeVoteCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    proposal = session.get(FridayThemeProposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Theme proposal not found.")
    if proposal.status in {"approved", "denied"}:
        raise HTTPException(status_code=400, detail="Voting is closed for this proposal.")

    existing = session.exec(
        select(FridayThemeProposalVote).where(
            FridayThemeProposalVote.proposal_id == proposal_id,
            FridayThemeProposalVote.voter_id == current_user.id,
        )
    ).first()
    if existing:
        existing.in_favor = vote_in.in_favor
        session.add(existing)
    else:
        session.add(FridayThemeProposalVote(
            proposal_id=proposal_id,
            voter_id=current_user.id,
            in_favor=vote_in.in_favor,
        ))
    session.commit()

    votes = session.exec(
        select(FridayThemeProposalVote).where(
            FridayThemeProposalVote.proposal_id == proposal_id
        )
    ).all()
    yes_count = sum(1 for vote in votes if vote.in_favor)
    no_count = len(votes) - yes_count
    # Strict majority of votes cast. A tie stays pending and is not approved.
    if yes_count > no_count:
        proposal.status = "approved"
    elif no_count > yes_count:
        proposal.status = "denied"
    else:
        proposal.status = "pending"
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    return _friday_proposal_response(proposal, session, current_user)


@app.delete("/api/friday-themes/proposals/{proposal_id}/vote")
def remove_friday_theme_vote(
    proposal_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    proposal = session.get(FridayThemeProposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Theme proposal not found.")
    if proposal.status in {"approved", "denied"}:
        raise HTTPException(status_code=400, detail="Voting is closed for this proposal.")
    existing = session.exec(
        select(FridayThemeProposalVote).where(
            FridayThemeProposalVote.proposal_id == proposal_id,
            FridayThemeProposalVote.voter_id == current_user.id,
        )
    ).first()
    if existing:
        session.delete(existing)
        session.commit()
        remaining_votes = session.exec(
            select(FridayThemeProposalVote).where(
                FridayThemeProposalVote.proposal_id == proposal_id
            )
        ).all()
        yes_count = sum(1 for vote in remaining_votes if vote.in_favor)
        no_count = len(remaining_votes) - yes_count
        if yes_count > no_count:
            proposal.status = "approved"
        elif no_count > yes_count:
            proposal.status = "denied"
        else:
            proposal.status = "pending"
        session.add(proposal)
        session.commit()
    return {"status": "success", "message": "Vote removed"}


@app.get("/api/friday-themes/wheel")
def get_friday_theme_wheel(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    approved = session.exec(
        select(FridayThemeProposal).where(
            FridayThemeProposal.status == "approved"
        ).order_by(FridayThemeProposal.created_at.asc())
    ).all()
    available = []
    for proposal in approved:
        already_selected = session.exec(
            select(FridayThemeWheelSelection).where(
                FridayThemeWheelSelection.proposal_id == proposal.id
            )
        ).first()
        if not already_selected:
            available.append(_friday_proposal_response(proposal, session, current_user))
    latest = session.exec(
        select(FridayThemeWheelSelection).order_by(
            FridayThemeWheelSelection.selected_at.desc()
        )
    ).first()
    latest_response = None
    if latest:
        latest_proposal = session.get(FridayThemeProposal, latest.proposal_id)
        if latest_proposal:
            latest_response = _friday_proposal_response(latest_proposal, session, current_user)
    allowed = current_user.username.casefold() in _friday_wheel_spinner_usernames()
    return {"available": available, "latest_selection": latest_response, "can_spin": allowed}


@app.post("/api/friday-themes/wheel/spin")
def spin_friday_theme_wheel(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_friday_wheel_spinner(current_user)
    approved = session.exec(
        select(FridayThemeProposal).where(
            FridayThemeProposal.status == "approved"
        ).order_by(FridayThemeProposal.created_at.asc())
    ).all()
    available = []
    for proposal in approved:
        already_selected = session.exec(
            select(FridayThemeWheelSelection).where(
                FridayThemeWheelSelection.proposal_id == proposal.id
            )
        ).first()
        if not already_selected:
            available.append(proposal)
    if not available:
        raise HTTPException(
            status_code=400,
            detail="There are no approved, unused themes on the wheel yet."
        )

    import random
    winner = random.choice(available)
    selection = FridayThemeWheelSelection(
        proposal_id=winner.id,
        spun_by_id=current_user.id,
    )
    session.add(selection)
    session.commit()
    session.refresh(selection)
    return {
        "selection": _friday_proposal_response(winner, session, current_user),
        "selected_at": selection.selected_at.isoformat() + "Z",
        "spun_by": current_user.username,
        "remaining_count": len(available) - 1,
    }


@app.get("/api/friday-themes/history")
def get_friday_theme_history(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    selections = session.exec(
        select(FridayThemeWheelSelection).order_by(
            FridayThemeWheelSelection.selected_at.desc()
        )
    ).all()
    results = []
    for selection in selections:
        proposal = session.get(FridayThemeProposal, selection.proposal_id)
        spinner = session.get(User, selection.spun_by_id)
        if proposal:
            item = _friday_proposal_response(proposal, session, current_user)
            item["selected_at"] = selection.selected_at.isoformat() + "Z"
            item["spun_by"] = spinner.username if spinner else "Unknown"
            results.append(item)
    return results