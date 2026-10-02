"""SQLite Database Manager for macOS Activity Logging."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class ActivityDB:
    """Manages SQLite storage for application and window focus sessions."""

    DEFAULT_DB_PATH = os.path.expanduser("~/.macos_workflow_mcp/activity.db")

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = Path(os.path.expanduser(db_path or self.DEFAULT_DB_PATH)).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name TEXT NOT NULL,
                    window_title TEXT,
                    bundle_id TEXT,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    duration_seconds REAL NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_start ON activity_log(start_time);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_app ON activity_log(app_name);")
            conn.commit()

    def record_activity(
        self,
        app_name: str,
        window_title: str,
        bundle_id: str,
        start_time: Any,
        end_time: Any,
        duration_seconds: float,
    ) -> int:
        """Insert a completed activity duration record."""
        def to_iso(t: Any) -> str:
            if isinstance(t, datetime):
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                return t.isoformat()
            if isinstance(t, (int, float)):
                return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
            return str(t)

        st_str = to_iso(start_time)
        et_str = to_iso(end_time)

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO activity_log (app_name, window_title, bundle_id, start_time, end_time, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (app_name, window_title, bundle_id, st_str, et_str, float(duration_seconds)),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_activity_summary(self, since_minutes: int = 60, limit: int = 20) -> List[Dict[str, Any]]:
        """Get total duration and percentage per app over recent minutes."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                f"""
                SELECT 
                    app_name,
                    ROUND(SUM(duration_seconds), 1) as total_seconds,
                    COUNT(*) as focus_switches,
                    GROUP_CONCAT(DISTINCT window_title) as sample_windows
                FROM activity_log
                WHERE datetime(start_time) >= datetime('now', '-{int(since_minutes)} minutes')
                GROUP BY app_name
                ORDER BY total_seconds DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = cursor.fetchall()

        total_time = sum(r["total_seconds"] for r in rows) or 1.0
        results: List[Dict[str, Any]] = []
        for r in rows:
            dur = r["total_seconds"]
            pct = round((dur / total_time) * 100, 1)
            windows = [w for w in (r["sample_windows"] or "").split(",") if w.strip()][:3]
            results.append({
                "app_name": r["app_name"],
                "total_seconds": dur,
                "total_duration_seconds": dur,
                "percentage": pct,
                "event_count": r["focus_switches"],
                "sample_window_titles": windows,
                "formatted_duration": f"{int(dur // 3600)}h {int((dur % 3600) // 60)}m" if dur >= 3600 else (f"{int(dur // 60)}m" if dur >= 60 else f"{int(dur)}s"),
                "focus_switches": r["focus_switches"],
                "sample_windows": windows,
            })
        return results

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent chronological activity logs."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, app_name, window_title, bundle_id, start_time, end_time, duration_seconds
                FROM activity_log
                ORDER BY id DESC
                LIMIT ?;
                """,
                (limit,),
            )
            return [dict(r) for r in cursor.fetchall()]

    def clean_old_logs(self, days: int = 30) -> int:
        """Purge records older than N days."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                f"DELETE FROM activity_log WHERE datetime(start_time) < datetime('now', '-{int(days)} days');"
            )
            conn.commit()
            return cursor.rowcount
