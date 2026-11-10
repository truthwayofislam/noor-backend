from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status, Depends
from models.schemas import (
    ActivityLog,
    ARABIC_COURSE_LESSON_IDS,
    ArabicCourseProgressSync,
    UserProfile,
    UserUpdate,
)
from routes.auth import get_current_user
from utils.turso_storage import turso_storage as storage

router = APIRouter(prefix="/users", tags=["Users"])

ACTIVITY_REWARDS = {
    "quran_read": 10,
    "prayer_logged": 5,
    "lesson_completed": 20,
    "dua_memorized": 15,
    "game_completed": 10,
}

DAILY_TASK_REWARDS = {
    "fajr": 5,
    "dhuhr": 5,
    "asr": 5,
    "maghrib": 5,
    "isha": 5,
    "quran_1page": 5,
    "quran_1juz": 20,
    "quran_memorize": 15,
    "morning_adhkar": 10,
    "evening_adhkar": 10,
    "tasbih_100": 5,
    "charity": 10,
    "help_someone": 10,
    "smile": 2,
}

GAME_LEVEL_LIMITS = {
    "memory_match": 50,
    "prayer_quiz": 50,
    "names_puzzle": 99,
    "wudu_steps": 12,
}

def _normalized_metadata_value(metadata: dict, key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Activity metadata must include {key}.",
        )
    return " ".join(value.strip().lower().split())


def _activity_event_key(activity: ActivityLog, today: str) -> str:
    metadata = activity.metadata or {}
    activity_type = activity.activity_type
    if activity_type == "prayer_logged":
        prayer = _normalized_metadata_value(metadata, "prayer")
        if prayer not in {"fajr", "dhuhr", "asr", "maghrib", "isha"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unknown prayer.",
            )
        return f"prayer:{today}:{prayer}"
    if activity_type == "quran_read":
        surah_number = metadata.get("surah_number")
        if (
            not isinstance(surah_number, int)
            or isinstance(surah_number, bool)
            or not 1 <= surah_number <= 114
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="surah_number must be between 1 and 114.",
            )
        return f"quran:{today}:{surah_number}"
    if activity_type == "lesson_completed":
        return f"lesson:{_normalized_metadata_value(metadata, 'lesson')[:120]}"
    if activity_type == "dua_memorized":
        return f"dua:{_normalized_metadata_value(metadata, 'dua_title')[:120]}"
    if activity_type == "game_completed":
        game_id = metadata.get("game_id")
        level = metadata.get("level")
        if (
            not isinstance(game_id, str)
            or game_id not in GAME_LEVEL_LIMITS
            or not isinstance(level, int)
            or isinstance(level, bool)
            or not 1 <= level <= GAME_LEVEL_LIMITS[game_id]
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A valid game_id and level are required.",
            )
        return f"game:{game_id}:{level}"
    if activity_type == "daily_task_completed":
        task_id = metadata.get("task_id")
        if not isinstance(task_id, str) or task_id not in DAILY_TASK_REWARDS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unknown daily task.",
            )
        return f"task:{today}:{task_id}"
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Unsupported activity type.",
    )


def _user_profile(user: dict) -> UserProfile:
    return UserProfile(
        id=user["id"],
        email=user["email"],
        username=user["username"],
        country=user["country"],
        level=user["level"],
        points=user.get("points", 0),
        streak_days=user.get("streak_days", 0),
        last_activity_date=user.get("last_activity_date"),
        quran_progress=user.get("quran_progress", 0.0),
        prayers_logged=user.get("prayers_logged", 0),
        lessons_completed=user.get("lessons_completed", 0),
        avatar=user.get("avatar"),
        created_at=user["created"],
        updated_at=user["updated"],
    )


@router.get("/me", response_model=UserProfile)
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """Get current user's profile"""
    return _user_profile(current_user)

@router.put("/me", response_model=UserProfile)
async def update_my_profile(
    update_data: UserUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update current user's profile"""
    try:
        # Filter out None values
        data_to_update = {k: v for k, v in update_data.dict().items() if v is not None}

        if not data_to_update:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No data to update"
            )

        updated_user = await storage.update_user(current_user["id"], data_to_update)

        return _user_profile(updated_user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

def _arabic_course_progress_response(result: dict) -> dict:
    return {
        "progress": {
            "completed_lesson_ids": result["completed_lesson_ids"],
            "hearts": result["hearts"],
            "heart_date": result["heart_date"],
        },
        "user": _user_profile(result["user"]).model_dump(),
    }


@router.get("/arabic-course-progress")
async def get_arabic_course_progress(
    current_user: dict = Depends(get_current_user),
):
    """Get the authenticated user's Arabic course progress."""
    try:
        result = await storage.get_arabic_course_progress(current_user["id"])
        return _arabic_course_progress_response(result)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load Arabic course progress.",
        ) from error


@router.put("/arabic-course-progress")
async def sync_arabic_course_progress(
    progress: ArabicCourseProgressSync,
    current_user: dict = Depends(get_current_user),
):
    """Merge Arabic course completion and daily hearts across the user's devices."""
    lesson_ids = progress.completed_lesson_ids
    if (
        len(lesson_ids) != len(set(lesson_ids))
        or any(lesson_id not in ARABIC_COURSE_LESSON_IDS for lesson_id in lesson_ids)
        or len(progress.heart_spend_ids) != len(set(progress.heart_spend_ids))
        or any(
            not spend_id or len(spend_id) > 80
            for spend_id in progress.heart_spend_ids
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Arabic progress contains invalid or duplicate entries.",
        )

    try:
        result = await storage.sync_arabic_course_progress(
            user_id=current_user["id"],
            completed_lesson_ids=lesson_ids,
            hearts=progress.hearts,
            heart_date=progress.heart_date,
            heart_spend_ids=progress.heart_spend_ids,
        )
        return _arabic_course_progress_response(result)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to sync Arabic course progress.",
        ) from error


@router.post("/activity", status_code=status.HTTP_201_CREATED)
async def log_activity(
    activity: ActivityLog,
    current_user: dict = Depends(get_current_user)
):
    """
    Log user activity and earn points

    Rewards are assigned on the server and duplicate activity keys are ignored.
    """
    try:
        # Verify user_id matches current user
        if activity.user_id != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot log activity for another user"
            )

        today = datetime.now(timezone.utc).date()
        # Never let a client-supplied date create another daily reward key.
        event_date = today
        if activity.activity_type == "daily_task_completed":
            task_id = (activity.metadata or {}).get("task_id")
            points = (
                DAILY_TASK_REWARDS.get(task_id)
                if isinstance(task_id, str)
                else None
            )
        else:
            points = ACTIVITY_REWARDS.get(activity.activity_type)
        if points is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported activity type or task.",
            )
        storage_activity = activity
        if (
            activity.activity_type == "daily_task_completed"
            and (activity.metadata or {}).get("task_id")
            in {"fajr", "dhuhr", "asr", "maghrib", "isha"}
        ):
            prayer = (activity.metadata or {})["task_id"]
            storage_activity = ActivityLog(
                user_id=activity.user_id,
                activity_type="prayer_logged",
                metadata={"prayer": prayer},
                activity_date=event_date,
            )
        event_key = _activity_event_key(storage_activity, event_date.isoformat())
        result = await storage.log_activity(
            user_id=activity.user_id,
            activity_type=storage_activity.activity_type,
            points=points,
            metadata=storage_activity.metadata,
            event_key=event_key,
            activity_date=today,
        )
        updated_user = result["user"]

        return {
            "message": "Activity logged successfully"
            if result["points_earned"] > 0
            else "Activity was already recorded",
            "points_earned": result["points_earned"],
            "total_points": updated_user["points"],
            "user": _user_profile(updated_user).model_dump(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/rank")
async def get_my_rank(current_user: dict = Depends(get_current_user)):
    """Get current user's rank in global leaderboard"""
    try:
        rank_data = await storage.get_user_rank(current_user["id"])
        return rank_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
