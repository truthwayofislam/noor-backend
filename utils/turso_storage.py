import asyncio
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import libsql

from utils.auth import get_password_hash, verify_password


USER_COLUMNS = """
    id, email, username, country, level, points, streak_days,
    quran_progress, prayers_logged, lessons_completed, avatar,
    last_activity_date, created, updated
"""


class TursoStorage:
    def __init__(
        self,
        database_url: Optional[str] = None,
        auth_token: Optional[str] = None,
    ):
        self.database_url = database_url
        self.auth_token = auth_token

    def _connect(self):
        database_url = self.database_url or os.getenv("TURSO_DATABASE_URL")
        auth_token = self.auth_token or os.getenv("TURSO_AUTH_TOKEN")
        if not database_url:
            raise RuntimeError("TURSO_DATABASE_URL is not configured.")
        if database_url.startswith("libsql://") and not auth_token:
            raise RuntimeError(
                "TURSO_AUTH_TOKEN is required for a remote Turso database."
            )
        if auth_token:
            return libsql.connect(database=database_url, auth_token=auth_token)
        return libsql.connect(database=database_url)

    async def _run(self, operation, *args):
        return await asyncio.to_thread(operation, *args)

    async def initialize(self) -> None:
        await self._run(self._initialize)

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash TEXT NOT NULL,
                    username TEXT NOT NULL,
                    country TEXT NOT NULL,
                    level TEXT NOT NULL,
                    points INTEGER NOT NULL DEFAULT 0,
                    streak_days INTEGER NOT NULL DEFAULT 0,
                    quran_progress REAL NOT NULL DEFAULT 0,
                    prayers_logged INTEGER NOT NULL DEFAULT 0,
                    lessons_completed INTEGER NOT NULL DEFAULT 0,
                    avatar TEXT,
                    last_activity_date TEXT,
                    created TEXT NOT NULL,
                    updated TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS activities (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    activity_type TEXT NOT NULL,
                    points INTEGER NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    event_key TEXT,
                    created TEXT NOT NULL
                )
                """
            )
            user_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            needs_streak_migration = "last_activity_date" not in user_columns
            if needs_streak_migration:
                connection.execute(
                    "ALTER TABLE users ADD COLUMN last_activity_date TEXT"
                )
            activity_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(activities)"
                ).fetchall()
            }
            needs_activity_migration = "event_key" not in activity_columns
            if needs_activity_migration:
                connection.execute("ALTER TABLE activities ADD COLUMN event_key TEXT")
            if needs_activity_migration:
                self._backfill_activity_event_keys(connection)
                self._backfill_user_activity_counts(connection)
            if needs_streak_migration:
                self._backfill_user_streaks(connection)
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS activities_user_event_idx "
                "ON activities(user_id, event_key)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS users_points_idx ON users(points DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS users_country_points_idx "
                "ON users(country, points DESC)"
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _backfill_activity_event_keys(connection) -> None:
        rows = connection.execute(
            "SELECT id, user_id, activity_type, metadata, event_key, created "
            "FROM activities ORDER BY created, id"
        ).fetchall()
        seen_keys = {
            (user_id, event_key)
            for _, user_id, _, _, event_key, _ in rows
            if event_key is not None
        }
        for activity_id, user_id, activity_type, raw_metadata, event_key, created in rows:
            if event_key is not None:
                continue
            try:
                metadata = json.loads(raw_metadata or "{}")
                activity_date = datetime.fromisoformat(
                    created.replace("Z", "+00:00")
                ).date().isoformat()
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(metadata, dict):
                continue

            if activity_type == "prayer_logged":
                prayer = metadata.get("prayer")
                key = (
                    f"prayer:{activity_date}:{prayer.strip().lower()}"
                    if isinstance(prayer, str) and prayer.strip()
                    else None
                )
            elif activity_type == "quran_read":
                surah_number = metadata.get("surah_number")
                key = (
                    f"quran:{activity_date}:{surah_number}"
                    if isinstance(surah_number, int)
                    and not isinstance(surah_number, bool)
                    and 1 <= surah_number <= 114
                    else None
                )
            elif activity_type == "lesson_completed":
                lesson = metadata.get("lesson")
                key = (
                    f"lesson:{' '.join(lesson.strip().lower().split())[:120]}"
                    if isinstance(lesson, str) and lesson.strip()
                    else None
                )
            elif activity_type == "dua_memorized":
                title = metadata.get("dua_title")
                key = (
                    f"dua:{' '.join(title.strip().lower().split())[:120]}"
                    if isinstance(title, str) and title.strip()
                    else None
                )
            else:
                key = None

            if key is None or (user_id, key) in seen_keys:
                continue
            connection.execute(
                "UPDATE activities SET event_key = ? WHERE id = ?",
                (key, activity_id),
            )
            seen_keys.add((user_id, key))

    @staticmethod
    def _backfill_user_streaks(connection) -> None:
        today = datetime.now(timezone.utc).date()
        users = connection.execute(
            "SELECT id FROM users WHERE last_activity_date IS NULL"
        ).fetchall()
        for (user_id,) in users:
            rows = connection.execute(
                "SELECT created FROM activities WHERE user_id = ? ORDER BY created DESC",
                (user_id,),
            ).fetchall()
            activity_dates = set()
            for (created,) in rows:
                try:
                    activity_dates.add(
                        datetime.fromisoformat(created.replace("Z", "+00:00")).date()
                    )
                except (AttributeError, TypeError, ValueError):
                    continue
            if not activity_dates:
                continue

            latest_date = max(activity_dates)
            streak_days = 0
            if latest_date >= today - timedelta(days=1):
                streak_days = 1
                current_date = latest_date
                while current_date - timedelta(days=1) in activity_dates:
                    current_date -= timedelta(days=1)
                    streak_days += 1
            connection.execute(
                "UPDATE users SET last_activity_date = ?, streak_days = ? "
                "WHERE id = ? AND last_activity_date IS NULL",
                (latest_date.isoformat(), streak_days, user_id),
            )

    @staticmethod
    def _backfill_user_activity_counts(connection) -> None:
        users = connection.execute("SELECT id FROM users").fetchall()
        for (user_id,) in users:
            rows = connection.execute(
                "SELECT activity_type, metadata, event_key FROM activities "
                "WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            prayer_events = set()
            lesson_events = set()
            completed_surahs = set()
            for activity_type, raw_metadata, event_key in rows:
                if activity_type == "prayer_logged" and event_key is not None:
                    prayer_events.add(event_key)
                elif activity_type == "lesson_completed" and event_key is not None:
                    lesson_events.add(event_key)
                elif activity_type == "quran_read":
                    try:
                        metadata = json.loads(raw_metadata or "{}")
                        surah_number = metadata.get("surah_number")
                    except (AttributeError, TypeError, ValueError):
                        continue
                    if (
                        isinstance(metadata, dict)
                        and isinstance(surah_number, int)
                        and not isinstance(surah_number, bool)
                        and 1 <= surah_number <= 114
                    ):
                        completed_surahs.add(surah_number)

            connection.execute(
                """
                UPDATE users
                SET prayers_logged = ?,
                    lessons_completed = ?,
                    quran_progress = ?
                WHERE id = ?
                """,
                (
                    len(prayer_events),
                    len(lesson_events),
                    round(len(completed_surahs) * 100 / 114, 1),
                    user_id,
                ),
            )

    @staticmethod
    def _row_dict(cursor, row) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        return dict(zip((column[0] for column in cursor.description), row))

    @classmethod
    def _get_user(cls, connection, user_id: str) -> Optional[Dict[str, Any]]:
        cursor = connection.execute(
            f"SELECT {USER_COLUMNS} FROM users WHERE id = ?", (user_id,)
        )
        return cls._row_dict(cursor, cursor.fetchone())

    async def create_user(
        self,
        email: str,
        password: str,
        username: str,
        country: str,
        level: str,
    ) -> Dict[str, Any]:
        return await self._run(
            self._create_user, email, password, username, country, level
        )

    def _create_user(
        self, email: str, password: str, username: str, country: str, level: str
    ) -> Dict[str, Any]:
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        password_hash = get_password_hash(password)
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO users (
                    id, email, password_hash, username, country, level, created, updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, email, password_hash, username, country, level, now, now),
            )
            connection.commit()
            return self._get_user(connection, user_id)
        except Exception as error:
            connection.rollback()
            if "UNIQUE constraint failed: users.email" in str(error):
                raise ValueError("An account with this email already exists.") from error
            raise
        finally:
            connection.close()

    async def authenticate_user(
        self, email: str, password: str
    ) -> Optional[Dict[str, Any]]:
        return await self._run(self._authenticate_user, email, password)

    def _authenticate_user(
        self, email: str, password: str
    ) -> Optional[Dict[str, Any]]:
        connection = self._connect()
        try:
            cursor = connection.execute(
                "SELECT password_hash FROM users WHERE email = ? COLLATE NOCASE",
                (email,),
            )
            row = cursor.fetchone()
            if row is None or not verify_password(password, row[0]):
                return None
            cursor = connection.execute(
                f"SELECT {USER_COLUMNS} FROM users WHERE email = ? COLLATE NOCASE",
                (email,),
            )
            return self._row_dict(cursor, cursor.fetchone())
        finally:
            connection.close()

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self._run(self._get_user_by_id, user_id)

    def _get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        connection = self._connect()
        try:
            return self._get_user(connection, user_id)
        finally:
            connection.close()

    async def update_user(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._run(self._update_user, user_id, data)

    def _update_user(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        allowed_columns = {"username", "country", "level", "avatar"}
        updates = {key: value for key, value in data.items() if key in allowed_columns}
        if not updates:
            user = self._get_user_by_id(user_id)
            if user is None:
                raise ValueError("User not found.")
            return user

        updates["updated"] = datetime.now(timezone.utc).isoformat()
        assignments = ", ".join(f"{column} = ?" for column in updates)
        connection = self._connect()
        try:
            cursor = connection.execute(
                f"UPDATE users SET {assignments} WHERE id = ?",
                (*updates.values(), user_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("User not found.")
            connection.commit()
            return self._get_user(connection, user_id)
        finally:
            connection.close()

    async def log_activity(
        self,
        user_id: str,
        activity_type: str,
        points: int,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        event_key: str,
        activity_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        return await self._run(
            self._log_activity,
            user_id,
            activity_type,
            points,
            metadata,
            event_key,
            activity_date,
        )

    def _log_activity(
        self,
        user_id: str,
        activity_type: str,
        points: int,
        metadata: Optional[Dict[str, Any]],
        event_key: str,
        activity_date: Optional[date],
    ) -> Dict[str, Any]:
        connection = self._connect()
        try:
            user = self._get_user(connection, user_id)
            if user is None:
                raise ValueError("User not found.")

            now = datetime.now(timezone.utc).isoformat()
            today = activity_date or datetime.now(timezone.utc).date()
            yesterday = today - timedelta(days=1)
            try:
                connection.execute(
                    """
                    INSERT INTO activities (
                        id, user_id, activity_type, points, metadata, event_key, created
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        user_id,
                        activity_type,
                        points,
                        json.dumps(metadata or {}),
                        event_key,
                        now,
                    ),
                )
            except Exception as error:
                if "UNIQUE constraint failed: activities.user_id, activities.event_key" not in str(error):
                    raise
                connection.rollback()
                return {"user": self._get_user(connection, user_id), "points_earned": 0}

            quran_progress = user["quran_progress"]
            if activity_type == "quran_read":
                cursor = connection.execute(
                    "SELECT metadata FROM activities "
                    "WHERE user_id = ? AND activity_type = 'quran_read'",
                    (user_id,),
                )
                completed_surahs = set()
                for (raw_metadata,) in cursor.fetchall():
                    try:
                        surah_number = json.loads(raw_metadata).get("surah_number")
                    except (TypeError, json.JSONDecodeError):
                        continue
                    if isinstance(surah_number, int) and 1 <= surah_number <= 114:
                        completed_surahs.add(surah_number)
                quran_progress = round(len(completed_surahs) * 100 / 114, 1)

            connection.execute(
                """
                UPDATE users
                SET points = points + ?,
                    streak_days = CASE
                        WHEN last_activity_date = ? THEN streak_days
                        WHEN last_activity_date = ? THEN streak_days + 1
                        ELSE 1
                    END,
                    last_activity_date = ?,
                    quran_progress = ?,
                    prayers_logged = prayers_logged + ?,
                    lessons_completed = lessons_completed + ?,
                    updated = ?
                WHERE id = ?
                """,
                (
                    points,
                    today.isoformat(),
                    yesterday.isoformat(),
                    today.isoformat(),
                    quran_progress,
                    1 if activity_type == "prayer_logged" else 0,
                    1 if activity_type == "lesson_completed" else 0,
                    now,
                    user_id,
                ),
            )
            connection.commit()
            return {
                "user": self._get_user(connection, user_id),
                "points_earned": points,
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    async def get_leaderboard(
        self, limit: int = 100, country: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return await self._run(self._get_leaderboard, limit, country)

    def _get_leaderboard(
        self, limit: int, country: Optional[str]
    ) -> List[Dict[str, Any]]:
        connection = self._connect()
        try:
            if country:
                cursor = connection.execute(
                    """
                    SELECT id AS user_id, username, country, points, avatar
                    FROM users WHERE country = ?
                    ORDER BY points DESC, username COLLATE NOCASE
                    LIMIT ?
                    """,
                    (country, limit),
                )
            else:
                cursor = connection.execute(
                    """
                    SELECT id AS user_id, username, country, points, avatar
                    FROM users
                    ORDER BY points DESC, username COLLATE NOCASE
                    LIMIT ?
                    """,
                    (limit,),
                )
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]
            return [
                {**dict(zip(columns, row)), "rank": rank}
                for rank, row in enumerate(rows, start=1)
            ]
        finally:
            connection.close()

    async def get_user_rank(self, user_id: str) -> Dict[str, Any]:
        return await self._run(self._get_user_rank, user_id)

    def _get_user_rank(self, user_id: str) -> Dict[str, Any]:
        connection = self._connect()
        try:
            user = self._get_user(connection, user_id)
            if user is None:
                raise ValueError("User not found.")
            cursor = connection.execute(
                "SELECT COUNT(*) FROM users WHERE points > ?", (user["points"],)
            )
            rank = cursor.fetchone()[0] + 1
            return {
                "rank": rank,
                "points": user["points"],
                "username": user["username"],
            }
        finally:
            connection.close()


turso_storage = TursoStorage()
