from typing import Optional, List
from datetime import date, datetime
from sqlmodel import SQLModel, Field, Relationship, create_engine
import os
from sqlmodel import SQLModel, create_engine

# 1. USERS TABLE
# Replaces the wide columns in Excel (alappatjoe, danram, etc.)
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    is_active: bool = Field(default=True)
    
    # Relationships
    songs_submitted: List["Song"] = Relationship(back_populates="submitter")
    votes: List["Vote"] = Relationship(back_populates="voter")

# 2. SONGS TABLE
# Stores the daily tracks and the metadata we'll pull from the Spotify API
class Song(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    artist: str
    spotify_uri: str = Field(unique=True, index=True)
    cover_art_url: Optional[str] = None
    parent_genre: Optional[str] = None # Brought over from your Genres sheet
    
    submission_date: date = Field(default_factory=date.today, index=True)
    
    # Foreign Keys
    submitter_id: int = Field(foreign_key="user.id")
    
    # Relationships
    submitter: User = Relationship(back_populates="songs_submitted")
    votes: List["Vote"] = Relationship(back_populates="song")

# 3. VOTES TABLE
# Normalizes the daily voting so we can easily calculate averages and STDEV in SQL
class Vote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    score: int = Field(ge=1, le=5) # Enforces the 1-5 scale
    vote_timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Foreign Keys
    song_id: int = Field(foreign_key="song.id")
    voter_id: int = Field(foreign_key="user.id")
    
    # Relationships
    song: Song = Relationship(back_populates="votes")
    voter: User = Relationship(back_populates="votes")

# 4. THEMES TABLE
# To track "Theme Thursday" submissions
class Theme(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    theme_suggestion: str
    description: Optional[str] = None
    theme_date: Optional[date] = None
    passed: bool = Field(default=False)
    
    # Foreign Key
    proponent_id: int = Field(foreign_key="user.id")

# save Render External Database URL as an environment variable
# For local testing, you can paste it directly here as a string temporarily
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///mbc_local.db")  # Default to local SQLite for development

# Initialize the connection engine
engine = create_engine(DATABASE_URL, echo=True)

# This function reads the models we built and creates the tables in Render
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

if __name__ == "__main__":
    create_db_and_tables()
    print("Database tables created successfully!")