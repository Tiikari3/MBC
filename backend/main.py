import os
import re
import statistics
from datetime import datetime, date, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True,)


class FridayThemeProposalVote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    proposal_id: int = Field(index=True)
    voter_id: int = Field(index=True)
    in_favor: bool


class FridayThemeWheelSelection(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    proposal_id: int = Field(index=True, unique=True)
    selected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True,)
    spun_by_id: int
    winning_song_id: Optional[int] = Field(default=None)
    winner_id: Optional[int] = Field(default=None)
    theme_date: Optional[date] = Field(default=None)


class FridayThemeProposalCreate(BaseModel):
    name: str
    description: str


class FridayThemeVoteCreate(BaseModel):
    in_favor: bool

# --- Song bracket tables ---

class BracketTournament(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    bracket_type: str = Field(index=True)  # "month" or "year"
    year: int = Field(index=True)
    month: Optional[int] = None
    voter_target: int = Field(default=6)
    status: str = Field(default="active", index=True)
    champion_song_id: Optional[int] = None
    created_by_user_id: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BracketMatch(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tournament_id: int = Field(index=True)
    round_number: int
    matchup_number: int
    song_a_id: Optional[int] = None
    song_b_id: Optional[int] = None
    winner_song_id: Optional[int] = None
    status: str = Field(default="open", index=True)


class BracketVote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    match_id: int = Field(index=True)
    voter_id: int = Field(index=True)
    song_id: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BracketCreateRequest(BaseModel):
    bracket_type: str  # "month" or "year"
    year: int
    month: Optional[int] = None


class BracketTargetRequest(BaseModel):
    voter_target: int


class BracketVoteRequest(BaseModel):
    song_id: int


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


def ensure_friday_theme_columns():
    """Add the assigned Friday date without deleting existing selections."""
    table_name = "fridaythemewheelselection"

    inspector = inspect(engine)

    if not inspector.has_table(table_name):
        return

    existing = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }

    if "theme_date" in existing:
        return

    backend = engine.url.get_backend_name()

    with engine.begin() as connection:
        if backend == "postgresql":
            connection.execute(
                text(
                    "ALTER TABLE fridaythemewheelselection "
                    "ADD COLUMN IF NOT EXISTS theme_date DATE"
                )
            )
        else:
            connection.execute(
                text(
                    "ALTER TABLE fridaythemewheelselection "
                    "ADD COLUMN theme_date DATE"
                )
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
    ensure_friday_theme_columns()


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


def get_next_friday_date() -> date:
    """Return the next Friday in Eastern Time, never today."""
    today = datetime.now(
        ZoneInfo("America/New_York")
    ).date()

    # Monday = 0, Friday = 4.
    days_until_friday = (4 - today.weekday()) % 7

    # If today is Friday, assign the following Friday instead.
    if days_until_friday == 0:
        days_until_friday = 7

    return today + timedelta(days=days_until_friday)


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
        "theme_date": (selection.theme_date.isoformat() if selection and selection.theme_date else None),
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

@app.post("/api/friday-themes/proposals/{proposal_id}/approve")
def manually_approve_friday_theme_proposal(
    proposal_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    # Only an authorized administrator/wheel spinner can approve manually.
    _require_friday_wheel_spinner(current_user)

    proposal = session.get(FridayThemeProposal, proposal_id)

    if not proposal:
        raise HTTPException(
            status_code=404,
            detail="Theme proposal not found.",
        )

    if proposal.status == "approved":
        return _friday_proposal_response(
            proposal, session, current_user
        )

    # Allow manually overriding either pending or denied status.
    proposal.status = "approved"
    session.add(proposal)
    session.commit()
    session.refresh(proposal)

    return _friday_proposal_response(
        proposal, session, current_user
    )

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
    # Reject immediately when there are 3 or more no votes.
    # Otherwise, require at least 8 total votes before approval.
    MIN_VOTES_FOR_AUTOMATIC_DECISION = 8

    total_votes = yes_count + no_count

    if no_count >= 3:
        proposal.status = "denied"
    elif total_votes >= MIN_VOTES_FOR_AUTOMATIC_DECISION and yes_count > no_count:
        proposal.status = "approved"
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
       # Reject immediately when there are 3 or more no votes.
    # Otherwise, require at least 8 total votes before approval.
    MIN_VOTES_FOR_AUTOMATIC_DECISION = 8

    total_votes = yes_count + no_count

    if no_count >= 3:
        proposal.status = "denied"
    elif total_votes >= MIN_VOTES_FOR_AUTOMATIC_DECISION and yes_count > no_count:
        proposal.status = "approved"
    else:
        proposal.status = "pending"

    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    return _friday_proposal_response(proposal, session, current_user)


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
        theme_date=get_next_friday_date(),
    )
    session.add(selection)
    session.commit()
    session.refresh(selection)
    return {
        "selection": _friday_proposal_response(winner, session, current_user),
        "selected_at": selection.selected_at.isoformat() + "Z",
        "theme_date": selection.theme_date.isoformat(),
        "spun_by": current_user.username,
        "remaining_count": len(available) - 1,
    }


@app.get("/api/friday-themes/upcoming")
def get_upcoming_friday_theme(
    session: Session = Depends(get_session),
):
    """Return the theme assigned to the nearest upcoming Friday."""
    today = datetime.now(
        ZoneInfo("America/New_York")
    ).date()

    selection = session.exec(
        select(FridayThemeWheelSelection)
        .where(
            FridayThemeWheelSelection.theme_date >= today
        )
        .order_by(
            FridayThemeWheelSelection.theme_date.asc(),
            FridayThemeWheelSelection.selected_at.desc(),
        )
    ).first()

    if not selection:
        return {"theme": None}

    proposal = session.get(
        FridayThemeProposal,
        selection.proposal_id,
    )

    if not proposal:
        return {"theme": None}

    return {
        "theme": {
            "name": proposal.name,
            "description": proposal.description,
            "theme_date": selection.theme_date.isoformat(),
            "selected_at": selection.selected_at.isoformat(),
        }
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
        proposal = session.get(
            FridayThemeProposal,
            selection.proposal_id,
        )
        spinner = session.get(User, selection.spun_by_id)

        # Look up the winner
        winner = (
            session.get(User, selection.winner_id)
            if selection.winner_id is not None
            else None
        )

        # Look up the winning song
        song = (
            session.get(Song, selection.winning_song_id)
            if selection.winning_song_id is not None
            else None
        )

        if proposal:
            item = _friday_proposal_response(
                proposal,
                session,
                current_user,
            )

            item["selected_at"] = selection.selected_at.isoformat() + "Z"
            item["spun_by"] = (
                spinner.username if spinner else "Unknown"
            )
            item["winner_username"] = (
                winner.username if winner else None
            )
            item["winning_song_title"] = (
                song.title if song else None
            )

            results.append(item)

    return results

#--------------------- Bracket Definitions-----------------------------------

def _bracket_admin_usernames():
    # Set BRACKET_ADMIN_USERNAMES in Render to your account's username.
    raw = os.getenv(
        "BRACKET_ADMIN_USERNAMES",
        os.getenv("THEME_WHEEL_SPINNERS", "wheel_admin")
    )
    return {
        username.strip().casefold()
        for username in raw.split(",")
        if username.strip()
    }


def _require_bracket_admin(user):
    if user.username.casefold() not in _bracket_admin_usernames():
        raise HTTPException(
            status_code=403,
            detail="Only a bracket administrator can change bracket settings."
        )


def _get_daily_winners(session, year, month=None):
    """
    Get one winner per regular competition date.
    This uses existing Song and Vote records; it does not duplicate songs.
    """
    if month is not None:
        start = date(year, month, 1)
        end = (
            date(year + 1, 1, 1)
            if month == 12
            else date(year, month + 1, 1)
        )
    else:
        start = date(year, 1, 1)
        end = date(year + 1, 1, 1)

    songs = session.exec(
        select(Song).where(
            Song.submission_date >= start,
            Song.submission_date < end
        )
    ).all()

    if not songs:
        return []

    song_ids = [song.id for song in songs]
    votes = session.exec(
        select(Vote).where(Vote.song_id.in_(song_ids))
    ).all()

    votes_by_song = {}
    for vote in votes:
        votes_by_song.setdefault(vote.song_id, []).append(vote.score)

    songs_by_date = {}
    for song in songs:
        songs_by_date.setdefault(song.submission_date, []).append(song)

    winners = []

    for competition_date in sorted(songs_by_date):
        ranked = []

        for song in songs_by_date[competition_date]:
            scores = votes_by_song.get(song.id, [])
            # A song with no regular votes cannot be a daily winner.
            if not scores:
                continue

            average = sum(scores) / len(scores)
            stdev = statistics.stdev(scores) if len(scores) > 1 else 0

            ranked.append({
                "song": song,
                "average": average,
                "stdev": stdev,
                "selection_date": competition_date,
            })

        if not ranked:
            continue

        # Match the existing daily-history rule: lowest average, then
        # lowest standard deviation. Song ID makes any remaining tie stable.
        ranked.sort(
            key=lambda item: (
                item["average"],
                item["stdev"],
                item["song"].id
            )
        )
        winners.append(ranked[0])

    # This order is also the final tie-breaker for bracket seeding.
    # Stronger daily results are seeded first.
    winners.sort(
        key=lambda item: (
            item["average"],
            item["stdev"],
            item["selection_date"],
            item["song"].id
        )
    )
    return winners


def _create_bracket_round(session, tournament, song_ids, round_number):
    """Create the seeded first round, preserving matchup positions."""
    if not song_ids or round_number != 1:
        return

    bracket_size = 2
    while bracket_size < len(song_ids):
        bracket_size *= 2

    # Standard seed order, for example:
    # 4 slots: [1, 4, 2, 3]
    # 8 slots: [1, 8, 4, 5, 2, 7, 3, 6]
    seed_order = [1, 2]

    while len(seed_order) < bracket_size:
        next_size = len(seed_order) * 2
        seed_order = [
            value
            for seed in seed_order
            for value in (seed, next_size + 1 - seed)
        ]

    slots = [
        song_ids[seed - 1] if seed <= len(song_ids) else None
        for seed in seed_order
    ]

    for index in range(0, bracket_size, 2):
        song_a_id = slots[index]
        song_b_id = slots[index + 1]
        matchup_number = index // 2 + 1

        if song_a_id is None and song_b_id is None:
            continue

        if song_a_id is None or song_b_id is None:
            # A bye advances automatically, without a vote.
            advancing_song_id = song_a_id or song_b_id
            match = BracketMatch(
                tournament_id=tournament.id,
                round_number=1,
                matchup_number=matchup_number,
                song_a_id=advancing_song_id,
                song_b_id=None,
                winner_song_id=advancing_song_id,
                status="complete",
            )
        else:
            match = BracketMatch(
                tournament_id=tournament.id,
                round_number=1,
                matchup_number=matchup_number,
                song_a_id=song_a_id,
                song_b_id=song_b_id,
                status="open",
            )

        session.add(match)

    session.flush()


def _create_future_bracket_rounds(session, tournament, entrant_count):
    """Pre-create future matchups so winners can advance independently."""
    bracket_size = 2
    while bracket_size < entrant_count:
        bracket_size *= 2

    total_rounds = bracket_size.bit_length() - 1

    for round_number in range(2, total_rounds + 1):
        match_count = bracket_size // (2 ** round_number)

        for matchup_number in range(1, match_count + 1):
            session.add(
                BracketMatch(
                    tournament_id=tournament.id,
                    round_number=round_number,
                    matchup_number=matchup_number,
                    song_a_id=None,
                    song_b_id=None,
                    status="pending",
                )
            )

    session.flush()


def _advance_bracket_if_ready(session, tournament):
    """
    Update future matchups independently as feeder matches complete.
    Matches waiting for a winner remain pending and show TBD.
    """
    while tournament.status == "active":
        matches = session.exec(
            select(BracketMatch)
            .where(BracketMatch.tournament_id == tournament.id)
            .order_by(
                BracketMatch.round_number,
                BracketMatch.matchup_number,
            )
        ).all()

        if not matches:
            return

        rounds = {}
        for match in matches:
            rounds.setdefault(match.round_number, {})[
                match.matchup_number
            ] = match

        max_round = max(rounds)

        # Fill each later round using its two feeder matchups.
        for round_number in range(2, max_round + 1):
            previous_round = rounds.get(round_number - 1, {})
            current_round_matches = rounds.get(round_number, {})

            for matchup_number, match in current_round_matches.items():
                if match.status == "complete":
                    continue

                feeder_a = previous_round.get(
                    matchup_number * 2 - 1
                )
                feeder_b = previous_round.get(
                    matchup_number * 2
                )

                feeder_a_done = (
                    feeder_a is not None
                    and feeder_a.status == "complete"
                )
                feeder_b_done = (
                    feeder_b is not None
                    and feeder_b.status == "complete"
                )

                match.song_a_id = (
                    feeder_a.winner_song_id if feeder_a_done else None
                )
                match.song_b_id = (
                    feeder_b.winner_song_id if feeder_b_done else None
                )

                if not feeder_a_done or not feeder_b_done:
                    match.status = "pending"
                    match.winner_song_id = None

                elif match.song_a_id is None and match.song_b_id is None:
                    match.status = "pending"
                    match.winner_song_id = None

                elif match.song_a_id is None or match.song_b_id is None:
                    # A bye in a future round also advances automatically.
                    match.winner_song_id = (
                        match.song_a_id or match.song_b_id
                    )
                    match.status = "complete"

                else:
                    match.winner_song_id = None
                    match.status = "open"

                session.add(match)

        session.flush()

        # Reload after updating the later-round slots.
        matches = session.exec(
            select(BracketMatch)
            .where(BracketMatch.tournament_id == tournament.id)
            .order_by(
                BracketMatch.round_number,
                BracketMatch.matchup_number,
            )
        ).all()

        rounds = {}
        for match in matches:
            rounds.setdefault(match.round_number, {})[
                match.matchup_number
            ] = match

        final_round_number = max(rounds)
        final_matches = list(rounds[final_round_number].values())

        # A single completed final matchup determines the champion.
        if (
            len(final_matches) == 1
            and final_matches[0].status == "complete"
            and final_matches[0].winner_song_id is not None
        ):
            tournament.champion_song_id = (
                final_matches[0].winner_song_id
            )
            tournament.status = "complete"
            session.add(tournament)
            session.flush()
            return

        # Compatibility for an older tournament that doesn't yet have
        # pre-created future rounds: create its next round as before.
        latest_round_matches = list(rounds[final_round_number].values())

        if any(
            match.status != "complete"
            for match in latest_round_matches
        ):
            return

        winners = [
            match.winner_song_id
            for match in sorted(
                latest_round_matches,
                key=lambda item: item.matchup_number,
            )
            if match.winner_song_id is not None
        ]

        if len(winners) <= 1:
            return

        _create_bracket_round(
            session,
            tournament,
            winners,
            final_round_number + 1,
        )
        session.flush()


def _resolve_match_if_ready(session, tournament, match):
    """Complete a matchup as soon as either song reaches a majority."""

    if match.status != "open":
        return

    if match.song_a_id is None or match.song_b_id is None:
        return

    votes = session.exec(
        select(BracketVote).where(
            BracketVote.match_id == match.id
        )
    ).all()

    counts = {}
    for vote in votes:
        counts[vote.song_id] = counts.get(vote.song_id, 0) + 1

    a_votes = counts.get(match.song_a_id, 0)
    b_votes = counts.get(match.song_b_id, 0)

    # A strict majority of the configured voter target wins immediately.
    votes_needed_to_win = tournament.voter_target // 2 + 1

    if a_votes >= votes_needed_to_win:
        match.winner_song_id = match.song_a_id
        match.status = "complete"
        session.add(match)

    elif b_votes >= votes_needed_to_win:
        match.winner_song_id = match.song_b_id
        match.status = "complete"
        session.add(match)


    
#--------------Bracket Admin Controls------------------------------

def _bracket_song_json(session, song_id):
    if song_id is None:
        return None

    song = session.get(Song, song_id)
    if not song:
        return None

    # Look up the user who submitted the song
    submitter = session.get(User, song.submitter_id)

    return {
        "id": song.id,
        "title": song.title,
        "artist": song.artist,
        "spotify_url": song.spotify_url,
        "spotify_track_id": song.spotify_track_id,
        "submitter_id": song.submitter_id,
        "submittedBy": submitter.username if submitter else "Unknown",
        "submission_date": (
            song.submission_date.isoformat()
            if song.submission_date
            else None
        ),
    }

def _bracket_json(session, tournament, current_user_id=None):
    matches = session.exec(
        select(BracketMatch)
        .where(BracketMatch.tournament_id == tournament.id)
        .order_by(
            BracketMatch.round_number,
            BracketMatch.matchup_number
        )
    ).all()

    result_matches = []

    for match in matches:
        votes = session.exec(
            select(BracketVote).where(BracketVote.match_id == match.id)
        ).all()

        current_user_vote_song_id = next(
            (
                vote.song_id
                for vote in votes
                if vote.voter_id == current_user_id
            ),
            None,
        )

        a_voters = []
        b_voters = []

        for vote in votes:
            user = session.get(User, vote.voter_id)
            voter_info = {
                "user_id": vote.voter_id,
                "username": user.username if user else "Unknown",
            }

            if vote.song_id == match.song_a_id:
                a_voters.append(voter_info)
            elif vote.song_id == match.song_b_id:
                b_voters.append(voter_info)

        result_matches.append({
            "id": match.id,
            "round_number": match.round_number,
            "matchup_number": match.matchup_number,
            "song_a": _bracket_song_json(session, match.song_a_id),
            "song_b": _bracket_song_json(session, match.song_b_id),
            "winner_song_id": match.winner_song_id,
            "status": match.status,
            "song_a_votes": len(a_voters),
            "song_b_votes": len(b_voters),
            "song_a_voters": a_voters,
            "song_b_voters": b_voters,
            "votes_cast": len(votes),
            "current_user_vote_song_id": current_user_vote_song_id,
        })

    return {
        "id": tournament.id,
        "bracket_type": tournament.bracket_type,
        "year": tournament.year,
        "month": tournament.month,
        "voter_target": tournament.voter_target,
        "status": tournament.status,
        "champion": _bracket_song_json(
            session, tournament.champion_song_id
        ),
        "matches": result_matches,
    }


@app.get("/api/brackets")
def list_brackets(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    tournaments = session.exec(
        select(BracketTournament).order_by(
            BracketTournament.year.desc(),
            BracketTournament.month.desc()
        )
    ).all()

    return [
        _bracket_json(session, tournament, current_user.id)
        for tournament in tournaments
    ]


@app.post("/api/brackets")
def create_bracket(
    request: BracketCreateRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_bracket_admin(current_user)

    if request.bracket_type not in ("month", "year"):
        raise HTTPException(
            status_code=400,
            detail="bracket_type must be 'month' or 'year'."
        )

    if request.bracket_type == "month":
        if request.month is None or not 1 <= request.month <= 12:
            raise HTTPException(
                status_code=400,
                detail="A valid month from 1 to 12 is required."
            )
    elif request.month is not None:
        raise HTTPException(
            status_code=400,
            detail="A year bracket must not specify a month."
        )

    existing_query = select(BracketTournament).where(
        BracketTournament.bracket_type == request.bracket_type,
        BracketTournament.year == request.year,
    )

    if request.bracket_type == "month":
        existing_query = existing_query.where(
            BracketTournament.month == request.month
        )
    else:
        existing_query = existing_query.where(
            BracketTournament.month.is_(None)
        )

    if session.exec(existing_query).first():
        raise HTTPException(
            status_code=409,
            detail="That bracket already exists."
        )

    # Both bracket types draw from regular daily competition winners.
    # The annual bracket does NOT use Song of the Month bracket winners.
    entrants = _get_daily_winners(
        session,
        request.year,
        request.month if request.bracket_type == "month" else None
    )

    if not entrants:
        raise HTTPException(
            status_code=400,
            detail="No regular daily competition winners with votes were found."
        )

    tournament = BracketTournament(
        bracket_type=request.bracket_type,
        year=request.year,
        month=request.month if request.bracket_type == "month" else None,
        voter_target=6,
        created_by_user_id=current_user.id,
    )
    session.add(tournament)
    session.commit()
    session.refresh(tournament)

    # Snapshot the entrants and preserve their seeded bracket positions.
    song_ids = [item["song"].id for item in entrants]

    _create_bracket_round(session, tournament, song_ids, 1)

    # Create future rounds now, with TBD placeholders.
    _create_future_bracket_rounds(
        session,
        tournament,
        len(song_ids),
    )

    # Immediately populate any positions already determined by byes.
    _advance_bracket_if_ready(session, tournament)

    session.commit()
    session.refresh(tournament)

    return _bracket_json(session, tournament, current_user.id)

@app.get("/api/brackets/permissions")
def bracket_permissions(
    current_user: User = Depends(get_current_user),
):
    return {
        "is_admin": (
            current_user.username.casefold()
            in _bracket_admin_usernames()
        )
    }


@app.get("/api/brackets/available-years")
def bracket_available_years(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    songs = session.exec(select(Song)).all()
    years = sorted(
        {song.submission_date.year for song in songs},
        reverse=True
    )
    return {"years": years}


@app.get("/api/brackets/{tournament_id}")
def get_bracket(
    tournament_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    tournament = session.get(BracketTournament, tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Bracket not found.")

    return _bracket_json(session, tournament, current_user.id)


@app.put("/api/brackets/{tournament_id}/voter-target")
def update_bracket_voter_target(
    tournament_id: int,
    request: BracketTargetRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_bracket_admin(current_user)

    if not 1 <= request.voter_target <= 8:
        raise HTTPException(
            status_code=400,
            detail="The voter target must be between 1 and 8."
        )

    tournament = session.get(BracketTournament, tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Bracket not found.")

    if tournament.status == "complete":
        raise HTTPException(
            status_code=400,
            detail="A completed bracket's voter target cannot be changed."
        )

    tournament.voter_target = request.voter_target
    session.add(tournament)

    # Apply the new target to open matchups using votes already recorded.
    matches = session.exec(
        select(BracketMatch).where(
            BracketMatch.tournament_id == tournament.id,
            BracketMatch.status == "open",
        )
    ).all()

    for match in matches:
        _resolve_match_if_ready(session, tournament, match)

    _advance_bracket_if_ready(session, tournament)
    session.commit()
    session.refresh(tournament)

    return _bracket_json(session, tournament, current_user.id)


@app.post("/api/brackets/{tournament_id}/matches/{match_id}/vote")
def vote_in_bracket_match(
    tournament_id: int,
    match_id: int,
    request: BracketVoteRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    tournament = session.get(BracketTournament, tournament_id)
    match = session.get(BracketMatch, match_id)

    if (
        not tournament
        or not match
        or match.tournament_id != tournament.id
    ):
        raise HTTPException(
            status_code=404,
            detail="Matchup not found."
        )

    if tournament.status == "complete":
        raise HTTPException(
            status_code=400,
            detail="This tournament is already complete."
        )

    if match.status == "complete":
        raise HTTPException(
            status_code=400,
            detail="This matchup is already complete."
        )

    # Pending matchups with TBD opponents cannot accept votes.
    if (
        match.status != "open"
        or match.song_a_id is None
        or match.song_b_id is None
    ):
        raise HTTPException(
            status_code=400,
            detail="This matchup is not ready for voting yet."
        )

    if request.song_id not in (
        match.song_a_id,
        match.song_b_id,
    ):
        raise HTTPException(
            status_code=400,
            detail="You can only vote for one of the two songs in this matchup."
        )

    existing_vote = session.exec(
        select(BracketVote).where(
            BracketVote.match_id == match.id,
            BracketVote.voter_id == current_user.id,
        )
    ).first()

    if existing_vote:
        # Allow a voter to change their vote while the matchup is open.
        existing_vote.song_id = request.song_id
        existing_vote.created_at = datetime.now(timezone.utc)
        session.add(existing_vote)
    else:
        session.add(
            BracketVote(
                match_id=match.id,
                voter_id=current_user.id,
                song_id=request.song_id,
            )
        )

    session.flush()

    # Resolve only this matchup. Other open matchups stay open.
    _resolve_match_if_ready(session, tournament, match)

    # Update the bracket after this matchup changes.
    _advance_bracket_if_ready(session, tournament)

    session.commit()
    session.refresh(tournament)

    return _bracket_json(session, tournament, current_user.id)