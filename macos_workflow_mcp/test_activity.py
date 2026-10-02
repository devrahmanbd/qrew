"""
Unit and Integration Test Suite for macOS Activity Tracker & Database Module.
Verifies all DB operations, aggregations, focus detection, and daemon polling.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure package is discoverable
sys.path.insert(0, "/working_dir/c_76f216dfff90f6b4")

from macos_workflow_mcp.db import ActivityDB
from macos_workflow_mcp.activity_tracker import (
    ActivityMonitorDaemon,
    get_current_focus,
    get_running_apps,
    set_mock_focus,
    set_mock_running_apps,
)


class TestActivityDB(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_activity.db"
        self.db = ActivityDB(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_record_and_get_recent_events(self):
        now = datetime.now(timezone.utc)
        t1 = now - timedelta(minutes=10)
        t2 = now - timedelta(minutes=5)

        rec_id_1 = self.db.record_activity(
            app_name="Code",
            window_title="main.go — myproject",
            bundle_id="com.microsoft.VSCode",
            start_time=t1,
            end_time=t2,
            duration_seconds=300.0,
        )
        self.assertGreater(rec_id_1, 0)

        t3 = now - timedelta(minutes=4)
        t4 = now
        rec_id_2 = self.db.record_activity(
            app_name="Terminal",
            window_title="bash — 120x40",
            bundle_id="com.apple.Terminal",
            start_time=t3,
            end_time=t4,
            duration_seconds=240.0,
        )
        self.assertGreater(rec_id_2, rec_id_1)

        events = self.db.get_recent_events(limit=10)
        self.assertEqual(len(events), 2)
        # Most recent first
        self.assertEqual(events[0]["app_name"], "Terminal")
        self.assertEqual(events[0]["duration_seconds"], 240.0)
        self.assertEqual(events[1]["app_name"], "Code")
        self.assertEqual(events[1]["duration_seconds"], 300.0)

    def test_get_activity_summary(self):
        now = datetime.now(timezone.utc)

        # 20 mins in Code across 2 windows
        self.db.record_activity(
            app_name="Code",
            window_title="db.py",
            bundle_id="com.microsoft.VSCode",
            start_time=now - timedelta(minutes=50),
            end_time=now - timedelta(minutes=30),
            duration_seconds=1200.0,
        )
        self.db.record_activity(
            app_name="Code",
            window_title="tracker.py",
            bundle_id="com.microsoft.VSCode",
            start_time=now - timedelta(minutes=30),
            end_time=now - timedelta(minutes=20),
            duration_seconds=600.0,
        )

        # 10 mins in Chrome
        self.db.record_activity(
            app_name="Google Chrome",
            window_title="Model Context Protocol Spec",
            bundle_id="com.google.Chrome",
            start_time=now - timedelta(minutes=20),
            end_time=now - timedelta(minutes=10),
            duration_seconds=600.0,
        )

        # Total duration = 1200 + 600 + 600 = 2400 seconds (40 mins)
        # Code = 1800s (75.0%), Chrome = 600s (25.0%)
        summary = self.db.get_activity_summary(since_minutes=60)
        self.assertEqual(len(summary), 2)

        code_summary = summary[0]
        self.assertEqual(code_summary["app_name"], "Code")
        self.assertEqual(code_summary["total_duration_seconds"], 1800.0)
        self.assertEqual(code_summary["percentage"], 75.0)
        self.assertEqual(code_summary["event_count"], 2)
        self.assertIn("tracker.py", code_summary["sample_window_titles"])
        self.assertIn("db.py", code_summary["sample_window_titles"])
        self.assertEqual(code_summary["formatted_duration"], "30m")

        chrome_summary = summary[1]
        self.assertEqual(chrome_summary["app_name"], "Google Chrome")
        self.assertEqual(chrome_summary["total_duration_seconds"], 600.0)
        self.assertEqual(chrome_summary["percentage"], 25.0)
        self.assertEqual(chrome_summary["event_count"], 1)
        self.assertEqual(chrome_summary["sample_window_titles"], ["Model Context Protocol Spec"])
        self.assertEqual(chrome_summary["formatted_duration"], "10m")

    def test_clean_old_logs(self):
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=40)
        recent_time = now - timedelta(days=5)

        self.db.record_activity(
            app_name="OldApp",
            window_title="Old Window",
            bundle_id="com.old.app",
            start_time=old_time,
            end_time=old_time + timedelta(minutes=5),
            duration_seconds=300.0,
        )

        self.db.record_activity(
            app_name="NewApp",
            window_title="New Window",
            bundle_id="com.new.app",
            start_time=recent_time,
            end_time=recent_time + timedelta(minutes=5),
            duration_seconds=300.0,
        )

        # Total events initially = 2
        events = self.db.get_recent_events(limit=10)
        self.assertEqual(len(events), 2)

        # Clean logs older than 30 days
        deleted = self.db.clean_old_logs(days=30)
        self.assertEqual(deleted, 1)

        # Only NewApp remains
        remaining = self.db.get_recent_events(limit=10)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["app_name"], "NewApp")


class TestActivityTracker(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "tracker_test.db"
        self.db = ActivityDB(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_current_focus_and_mock(self):
        set_mock_focus("Obsidian", "Daily Note - 2026-09-26", "md.obsidian")
        focus = get_current_focus(force_mock=True)
        self.assertEqual(focus["app_name"], "Obsidian")
        self.assertEqual(focus["window_title"], "Daily Note - 2026-09-26")
        self.assertEqual(focus["bundle_id"], "md.obsidian")

    def test_get_running_apps_and_mock(self):
        apps = ["Finder", "Obsidian", "Terminal", "Goose"]
        set_mock_running_apps(apps)
        running = get_running_apps(force_mock=True)
        self.assertEqual(running, apps)

    def test_daemon_poll_once_and_focus_switching(self):
        state = {"app_name": "AppOne", "window_title": "Win 1", "bundle_id": "com.one"}

        def mock_focus_provider():
            return dict(state)

        daemon = ActivityMonitorDaemon(
            db=self.db,
            poll_interval=1.0,
            min_duration_seconds=0.1,
            focus_fn=mock_focus_provider,
        )

        # Tick 1: Initial focus, no recorded event
        evt1 = daemon.poll_once()
        self.assertIsNone(evt1)
        self.assertEqual(len(self.db.get_recent_events()), 0)

        # Wait a brief moment to accumulate duration
        time.sleep(0.2)

        # Tick 2: Same focus, no change recorded
        evt2 = daemon.poll_once()
        self.assertIsNone(evt2)
        self.assertEqual(len(self.db.get_recent_events()), 0)

        # Change focus to AppTwo
        state = {"app_name": "AppTwo", "window_title": "Win 2", "bundle_id": "com.two"}

        # Tick 3: Focus changed, records previous AppOne event
        evt3 = daemon.poll_once()
        self.assertIsNotNone(evt3)
        self.assertEqual(evt3["app_name"], "AppOne")
        self.assertEqual(evt3["window_title"], "Win 1")
        self.assertGreaterEqual(evt3["duration_seconds"], 0.15)

        # Verify DB has 1 event
        events = self.db.get_recent_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["app_name"], "AppOne")

        # Test flush() for AppTwo
        time.sleep(0.2)
        flush_evt = daemon.flush()
        self.assertIsNotNone(flush_evt)
        self.assertEqual(flush_evt["app_name"], "AppTwo")
        self.assertEqual(len(self.db.get_recent_events()), 2)

    def test_daemon_background_thread_lifecycle(self):
        state = {"app_name": "ThreadApp1", "window_title": "Doc1", "bundle_id": "com.thread.app1"}

        def mock_focus_provider():
            return dict(state)

        daemon = ActivityMonitorDaemon(
            db=self.db,
            poll_interval=0.1,
            min_duration_seconds=0.05,
            focus_fn=mock_focus_provider,
        )

        daemon.start()
        self.assertTrue(daemon.is_running)

        # Run with initial app
        time.sleep(0.25)

        # Switch app
        state = {"app_name": "ThreadApp2", "window_title": "Doc2", "bundle_id": "com.thread.app2"}
        time.sleep(0.25)

        # Stop daemon
        daemon.stop()
        self.assertFalse(daemon.is_running)

        # Both ThreadApp1 and ThreadApp2 should have been recorded
        events = self.db.get_recent_events()
        self.assertGreaterEqual(len(events), 2)
        app_names = [e["app_name"] for e in events]
        self.assertIn("ThreadApp1", app_names)
        self.assertIn("ThreadApp2", app_names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
