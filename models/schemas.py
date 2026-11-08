from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import date, datetime

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    username: str = Field(min_length=3, max_length=30)
    country: str
    level: str = "Beginner"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserProfile(BaseModel):
    id: str
    email: str
    username: str
    country: str
    level: str
    points: int = 0
    streak_days: int = 0
    quran_progress: float = 0.0
    prayers_logged: int = 0
    lessons_completed: int = 0
    avatar: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class UserUpdate(BaseModel):
    username: Optional[str] = None
    country: Optional[str] = None
    level: Optional[str] = None
    avatar: Optional[str] = None

class ActivityLog(BaseModel):
    user_id: str
    activity_type: str
    points: int = Field(default=0, ge=0)
    metadata: Optional[dict] = None
    activity_date: Optional[date] = None

class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    username: str
    country: str
    points: int
    avatar: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile
