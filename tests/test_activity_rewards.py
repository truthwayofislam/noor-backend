import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from models.schemas import ActivityLog
from routes import users


class ActivityRewardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = {
            "id": "user-1",
            "email": "person@example.com",
            "username": "NoorUser",
            "country": "Pakistan",
            "level": "Beginner",
            "points": 5,
            "streak_days": 1,
            "quran_progress": 0.0,
            "prayers_logged": 1,
            "lessons_completed": 0,
            "avatar": None,
            "created": "2025-01-01T00:00:00+00:00",
            "updated": "2025-01-01T00:00:00+00:00",
        }

    async def test_server_chooses_reward_instead_of_client_points(self):
        activity = ActivityLog(
            user_id="user-1",
            activity_type="prayer_logged",
            points=999999,
            metadata={"prayer": "Fajr"},
        )
        storage_result = {"user": self.user, "points_earned": 5}

        with patch.object(
            users.storage,
            "log_activity",
            new_callable=AsyncMock,
            return_value=storage_result,
        ) as log_activity:
            response = await users.log_activity(activity, self.user)

        self.assertEqual(log_activity.await_args.kwargs["points"], 5)
        self.assertEqual(response["points_earned"], 5)
        self.assertEqual(response["user"]["points"], 5)

    async def test_unknown_activities_are_rejected(self):
        activity = ActivityLog(
            user_id="user-1",
            activity_type="unknown",
            points=50,
        )

        with self.assertRaises(HTTPException) as error:
            await users.log_activity(activity, self.user)

        self.assertEqual(error.exception.status_code, 422)

    async def test_prayer_task_uses_the_same_reward_event_as_prayer_logging(self):
        today = datetime.now(timezone.utc).date()
        activity = ActivityLog(
            user_id="user-1",
            activity_type="daily_task_completed",
            points=999999,
            metadata={"task_id": "fajr"},
            activity_date=today,
        )
        storage_result = {"user": self.user, "points_earned": 5}

        with patch.object(
            users.storage,
            "log_activity",
            new_callable=AsyncMock,
            return_value=storage_result,
        ) as log_activity:
            await users.log_activity(activity, self.user)

        self.assertEqual(log_activity.await_args.kwargs["activity_type"], "prayer_logged")
        self.assertEqual(log_activity.await_args.kwargs["points"], 5)
        self.assertEqual(log_activity.await_args.kwargs["metadata"], {"prayer": "fajr"})
        self.assertEqual(
            log_activity.await_args.kwargs["event_key"],
            f"prayer:{today.isoformat()}:fajr",
        )


if __name__ == "__main__":
    unittest.main()
