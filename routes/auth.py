from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from models.schemas import UserRegister, UserLogin, Token, UserProfile
from utils.auth import create_access_token, decode_token
from utils.turso_storage import turso_storage as storage
import logging

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()
logger = logging.getLogger(__name__)

@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister):
    """Create an account and return an access token."""
    try:
        # Create user in Turso
        user = await storage.create_user(
            email=user_data.email,
            password=user_data.password,
            username=user_data.username,
            country=user_data.country,
            level=user_data.level
        )

        # Create access token
        access_token = create_access_token(
            data={"sub": user["id"], "email": user["email"]}
        )

        # Return token and user profile
        user_profile = UserProfile(
            id=user["id"],
            email=user["email"],
            username=user["username"],
            country=user["country"],
            level=user["level"],
            points=user.get("points", 0),
            streak_days=user.get("streak_days", 0),
            quran_progress=user.get("quran_progress", 0.0),
            prayers_logged=user.get("prayers_logged", 0),
            lessons_completed=user.get("lessons_completed", 0),
            avatar=user.get("avatar"),
            created_at=user["created"],
            updated_at=user["updated"]
        )

        return Token(access_token=access_token, user=user_profile)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception("Account registration failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create account right now.",
        ) from e

@router.post("/login", response_model=Token)
async def login(credentials: UserLogin):
    """Authenticate an account using its registered email and password."""
    try:
        # Authenticate against Turso
        user = await storage.authenticate_user(
            email=credentials.email,
            password=credentials.password
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        # Create access token
        access_token = create_access_token(
            data={"sub": user["id"], "email": user["email"]}
        )

        # Return token and user profile
        user_profile = UserProfile(
            id=user["id"],
            email=user["email"],
            username=user["username"],
            country=user["country"],
            level=user["level"],
            points=user.get("points", 0),
            streak_days=user.get("streak_days", 0),
            quran_progress=user.get("quran_progress", 0.0),
            prayers_logged=user.get("prayers_logged", 0),
            lessons_completed=user.get("lessons_completed", 0),
            avatar=user.get("avatar"),
            created_at=user["created"],
            updated_at=user["updated"]
        )

        return Token(access_token=access_token, user=user_profile)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Account login failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to sign in right now.",
        ) from e

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Dependency to get current authenticated user"""
    token = credentials.credentials
    payload = decode_token(token)
    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

    user = await storage.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user
