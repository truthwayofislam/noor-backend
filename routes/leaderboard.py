from fastapi import APIRouter, HTTPException, status, Query
from typing import Optional, List
from models.schemas import LeaderboardEntry
from utils.turso_storage import turso_storage as storage

router = APIRouter(prefix="/leaderboard", tags=["Leaderboard"])

@router.get("/global", response_model=List[LeaderboardEntry])
async def get_global_leaderboard(
    limit: int = Query(default=100, le=500, description="Number of users to return")
):
    """
    Get global leaderboard rankings

    Returns top users worldwide sorted by points
    """
    try:
        leaderboard = await storage.get_leaderboard(limit=limit)

        return [
            LeaderboardEntry(
                rank=entry["rank"],
                user_id=entry["user_id"],
                username=entry["username"],
                country=entry["country"],
                points=entry["points"],
                avatar=entry.get("avatar", "")
            )
            for entry in leaderboard
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/country/{country}", response_model=List[LeaderboardEntry])
async def get_country_leaderboard(
    country: str,
    limit: int = Query(default=100, le=500, description="Number of users to return")
):
    """
    Get country-specific leaderboard rankings

    Returns top users from a specific country sorted by points
    """
    try:
        leaderboard = await storage.get_leaderboard(limit=limit, country=country)

        return [
            LeaderboardEntry(
                rank=entry["rank"],
                user_id=entry["user_id"],
                username=entry["username"],
                country=entry["country"],
                points=entry["points"],
                avatar=entry.get("avatar", "")
            )
            for entry in leaderboard
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
