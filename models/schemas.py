from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import date, datetime

ARABIC_COURSE_LESSON_IDS = frozenset({
    *(f"basic-alphabet-{index:02d}" for index in range(1, 6)),
    *(f"basic-reading-{index:02d}" for index in range(1, 13)),
    *(f"words-{index:02d}" for index in range(1, 13)),
    *(
        f"{level_id}-{index:02d}"
        for level_id in (
            "conversation",
            "places",
            "descriptions",
            "sentences",
            "verbs",
            "routine",
            "tenses",
            "dialogues",
        )
        for index in range(1, 11)
    ),
})


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
    last_activity_date: Optional[date] = None
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

class ArabicCourseProgressSync(BaseModel):
    completed_lesson_ids: List[str] = Field(
        default_factory=list,
        max_length=len(ARABIC_COURSE_LESSON_IDS),
    )
    hearts: int = Field(ge=0, le=5)
    heart_date: Optional[date] = None
    heart_spend_ids: List[str] = Field(default_factory=list, max_length=5)

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
