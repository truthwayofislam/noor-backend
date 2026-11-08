import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import libsql
from utils.turso_storage import TursoStorage


class TursoStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temp_dir.name) / "noor.db")
        self.storage = TursoStorage(database_url=self.database_path)
        await self.storage.initialize()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def _create_user(self, email="person@example.com"):
        return await self.storage.create_user(
            email=email,
            password="secure-pass-123",
            username="NoorUser",
            country="Pakistan",
            level="Beginner",
        )

    async def test_accounts_persist_and_passwords_are_verified(self):
        user = await self._create_user()
        reopened_storage = TursoStorage(database_url=self.database_path)
        authenticated_user = await reopened_storage.authenticate_user(
            "PERSON@example.com", "secure-pass-123"
        )

        self.assertEqual(authenticated_user["id"], user["id"])
        self.assertIsNone(
            await reopened_storage.authenticate_user(
                "person@example.com", "wrong-password"
            )
        )

    async def test_profile_activity_and_leaderboard_are_persisted(self):
        user = await self._create_user()
        activity_result = await self.storage.log_activity(
            user["id"],
            "prayer_logged",
            5,
            {"prayer": "Fajr"},
            event_key="prayer:2025-01-01:fajr",
            activity_date=date(2025, 1, 1),
        )
        updated_user = await self.storage.update_user(
            user["id"], {"username": "UpdatedUser"}
        )
        leaderboard = await self.storage.get_leaderboard(country="Pakistan")
        rank = await self.storage.get_user_rank(user["id"])

        self.assertEqual(updated_user["prayers_logged"], 1)
        self.assertEqual(updated_user["points"], 5)
        self.assertEqual(updated_user["streak_days"], 1)
        self.assertEqual(activity_result["points_earned"], 5)
        self.assertEqual(leaderboard[0]["user_id"], user["id"])
        self.assertEqual(rank["rank"], 1)

    async def test_activity_retries_are_idempotent_and_streaks_follow_days(self):
        user = await self._create_user()
        first_day = date(2025, 1, 1)
        first_result = await self.storage.log_activity(
            user["id"],
            "prayer_logged",
            5,
            {"prayer": "Fajr"},
            event_key="prayer:2025-01-01:fajr",
            activity_date=first_day,
        )
        duplicate_result = await self.storage.log_activity(
            user["id"],
            "prayer_logged",
            5,
            {"prayer": "Fajr"},
            event_key="prayer:2025-01-01:fajr",
            activity_date=first_day,
        )
        same_day_result = await self.storage.log_activity(
            user["id"],
            "prayer_logged",
            5,
            {"prayer": "Dhuhr"},
            event_key="prayer:2025-01-01:dhuhr",
            activity_date=first_day,
        )
        next_day_result = await self.storage.log_activity(
            user["id"],
            "prayer_logged",
            5,
            {"prayer": "Asr"},
            event_key="prayer:2025-01-02:asr",
            activity_date=date(2025, 1, 2),
        )
        after_gap_result = await self.storage.log_activity(
            user["id"],
            "quran_read",
            10,
            {"surah_number": 1},
            event_key="quran:2025-01-04:1",
            activity_date=date(2025, 1, 4),
        )

        self.assertEqual(first_result["points_earned"], 5)
        self.assertEqual(duplicate_result["points_earned"], 0)
        self.assertEqual(duplicate_result["user"]["points"], 5)
        self.assertEqual(same_day_result["user"]["streak_days"], 1)
        self.assertEqual(same_day_result["user"]["prayers_logged"], 2)
        self.assertEqual(next_day_result["user"]["streak_days"], 2)
        self.assertEqual(after_gap_result["user"]["streak_days"], 1)
        self.assertEqual(after_gap_result["user"]["quran_progress"], 0.9)
        self.assertEqual(after_gap_result["user"]["points"], 25)

    async def test_duplicate_email_is_rejected_case_insensitively(self):
        await self._create_user()

        with self.assertRaisesRegex(ValueError, "already exists"):
            await self._create_user(email="PERSON@example.com")

    async def test_legacy_database_migration_preserves_activity_and_streak(self):
        legacy_path = str(Path(self.temp_dir.name) / "legacy.db")
        connection = libsql.connect(database=legacy_path)
        today = datetime.now(timezone.utc).date()
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY, email TEXT NOT NULL, password_hash TEXT NOT NULL,
                username TEXT NOT NULL, country TEXT NOT NULL, level TEXT NOT NULL,
                points INTEGER NOT NULL DEFAULT 0, streak_days INTEGER NOT NULL DEFAULT 0,
                quran_progress REAL NOT NULL DEFAULT 0, prayers_logged INTEGER NOT NULL DEFAULT 0,
                lessons_completed INTEGER NOT NULL DEFAULT 0, avatar TEXT,
                created TEXT NOT NULL, updated TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE activities (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, activity_type TEXT NOT NULL,
                points INTEGER NOT NULL, metadata TEXT NOT NULL DEFAULT '{}',
                created TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO users (
                id, email, password_hash, username, country, level, points,
                quran_progress, prayers_logged, lessons_completed, created, updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-user",
                "legacy@example.com",
                "password-hash",
                "Legacy",
                "Pakistan",
                "Beginner",
                5,
                50.0,
                2,
                2,
                now,
                now,
            ),
        )
        legacy_activities = (
            ("legacy-prayer", "prayer_logged", '{"prayer":"Fajr"}'),
            ("legacy-prayer-duplicate", "prayer_logged", '{"prayer":"Fajr"}'),
            ("legacy-lesson", "lesson_completed", '{"lesson":"Basics"}'),
            ("legacy-lesson-duplicate", "lesson_completed", '{"lesson":" basics "}'),
            ("legacy-quran-one", "quran_read", '{"surah_number":1}'),
            ("legacy-quran-one-duplicate", "quran_read", '{"surah_number":1}'),
            ("legacy-quran-two", "quran_read", '{"surah_number":2}'),
        )
        for activity_id, activity_type, metadata in legacy_activities:
            connection.execute(
                """
                INSERT INTO activities (
                    id, user_id, activity_type, points, metadata, created
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (activity_id, "legacy-user", activity_type, 5, metadata, now),
            )
        connection.commit()
        connection.close()

        migrated_storage = TursoStorage(database_url=legacy_path)
        await migrated_storage.initialize()
        duplicate = await migrated_storage.log_activity(
            "legacy-user",
            "prayer_logged",
            5,
            {"prayer": "Fajr"},
            event_key=f"prayer:{today.isoformat()}:fajr",
            activity_date=today,
        )

        self.assertEqual(duplicate["points_earned"], 0)
        self.assertEqual(duplicate["user"]["points"], 5)
        self.assertEqual(duplicate["user"]["streak_days"], 1)
        self.assertEqual(duplicate["user"]["prayers_logged"], 1)
        self.assertEqual(duplicate["user"]["lessons_completed"], 1)
        self.assertEqual(duplicate["user"]["quran_progress"], 1.8)


if __name__ == "__main__":
    unittest.main()
