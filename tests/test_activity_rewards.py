import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from models.schemas import ActivityLog, ArabicCourseProgressSync
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

    async def test_client_activity_date_cannot_create_another_daily_reward(self):
        today = datetime.now(timezone.utc).date()
        event_keys = []

        async def record_activity(**kwargs):
            event_keys.append(kwargs["event_key"])
            return {"user": self.user, "points_earned": 0}

        with patch.object(
            users.storage,
            "log_activity",
            new_callable=AsyncMock,
            side_effect=record_activity,
        ):
            for requested_date in (
                today - timedelta(days=1),
                today,
                today + timedelta(days=1),
            ):
                activity = ActivityLog(
                    user_id="user-1",
                    activity_type="prayer_logged",
                    metadata={"prayer": "Fajr"},
                    activity_date=requested_date,
                )
                await users.log_activity(activity, self.user)

        self.assertEqual(
            event_keys,
            [f"prayer:{today.isoformat()}:fajr"] * 3,
        )

    async def test_arabic_progress_rejects_unknown_lessons(self):
        progress = ArabicCourseProgressSync(
            completed_lesson_ids=["not-a-course-lesson"],
            hearts=5,
            heart_date=datetime.now(timezone.utc).date(),
        )

        with self.assertRaises(HTTPException) as error:
            await users.sync_arabic_course_progress(progress, self.user)

        self.assertEqual(error.exception.status_code, 422)

    async def test_arabic_progress_accepts_levels_three_through_ten(self):
        lesson_ids = [
            "conversation-01",
            "places-10",
            "descriptions-05",
            "sentences-10",
            "verbs-08",
            "routine-10",
            "tenses-10",
            "dialogues-10",
        ]
        progress = ArabicCourseProgressSync(
            completed_lesson_ids=lesson_ids,
            hearts=5,
            heart_date=datetime.now(timezone.utc).date(),
        )
        storage_result = {
            "completed_lesson_ids": lesson_ids,
            "hearts": 5,
            "heart_date": progress.heart_date.isoformat(),
            "user": self.user,
        }

        with patch.object(
            users.storage,
            "sync_arabic_course_progress",
            new_callable=AsyncMock,
            return_value=storage_result,
        ) as sync_progress:
            response = await users.sync_arabic_course_progress(progress, self.user)

        self.assertEqual(
            sync_progress.await_args.kwargs["completed_lesson_ids"],
            lesson_ids,
        )
        self.assertEqual(
            response["progress"]["completed_lesson_ids"],
            lesson_ids,
        )

    async def test_arabic_progress_sync_returns_server_merged_state(self):
        today = datetime.now(timezone.utc).date()
        progress = ArabicCourseProgressSync(
            completed_lesson_ids=["basic-alphabet-01"],
            hearts=4,
            heart_date=today,
            heart_spend_ids=["device-a-spend-1"],
        )
        storage_result = {
            "completed_lesson_ids": ["basic-alphabet-01", "basic-alphabet-02"],
            "hearts": 3,
            "heart_date": today.isoformat(),
            "user": self.user,
        }

        with patch.object(
            users.storage,
            "sync_arabic_course_progress",
            new_callable=AsyncMock,
            return_value=storage_result,
        ) as sync_progress:
            response = await users.sync_arabic_course_progress(progress, self.user)

        self.assertEqual(
            sync_progress.await_args.kwargs,
            {
                "user_id": "user-1",
                "completed_lesson_ids": ["basic-alphabet-01"],
                "hearts": 4,
                "heart_date": today,
                "heart_spend_ids": ["device-a-spend-1"],
            },
        )
        self.assertEqual(
            response["progress"]["completed_lesson_ids"],
            ["basic-alphabet-01", "basic-alphabet-02"],
        )
        self.assertEqual(response["progress"]["hearts"], 3)
        self.assertEqual(response["user"]["id"], "user-1")


if __name__ == "__main__":
    unittest.main()
