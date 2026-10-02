"""
Test suite verifying TaskGraphEngine, NotificationBridge, and AITaskReasoningEngine.
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macos_workflow_mcp import (
    TaskGraphEngine,
    TaskNode,
    NotificationBridge,
    AITaskReasoningEngine,
)


class TestAdvancedWorkflowFeatures(unittest.TestCase):
    """Test suite for Graph Engine, Notifications, and AI Reasoning Engine."""

    def setUp(self) -> None:
        self.sample_tasks = [
            {"line_number": 3, "text": "Facebook Account Create", "completed": False, "section": "## 17-Sep"},
            {"line_number": 4, "text": "Microsoft Video Create", "completed": False, "section": "## 17-Sep"},
            {"line_number": 5, "text": "Ghost Sender Video Share", "completed": False, "section": "## 17-Sep"},
            {"line_number": 6, "text": "Account Recovery of Flynn, Shaheen(first)", "completed": False, "section": "## 17-Sep"},
            {"line_number": 7, "text": "DB to text old geezer", "completed": False, "section": "## 17-Sep"},
            {"line_number": 8, "text": "Framique", "completed": False, "section": "## 17-Sep"},
        ]

    def test_task_graph_engine_dag_and_dependencies(self) -> None:
        engine = TaskGraphEngine()
        graph = engine.build_graph(self.sample_tasks)

        self.assertEqual(len(graph), 6)

        # 1. Verify "(first)" task gets top priority
        top_tasks = engine.get_topological_order()
        self.assertTrue(len(top_tasks) > 0)
        top_task = top_tasks[0]
        self.assertIn("Shaheen", top_task.text)
        self.assertGreaterEqual(top_task.priority_score, 60.0)

        # 2. Verify "Create" before "Share" workflow dependency
        # Microsoft Video Create -> Ghost Sender Video Share
        video_share_node = next(n for n in graph.values() if "share" in n.text.lower())
        video_create_node = next(n for n in graph.values() if "video create" in n.text.lower())

        self.assertIn(video_create_node.id, video_share_node.dependencies)
        self.assertIn(video_share_node.id, video_create_node.dependents)

        # 3. Verify actionable tasks (Share should not be ready until Create is done)
        actionable = engine.get_actionable_tasks()
        actionable_ids = {n.id for n in actionable}
        self.assertIn(video_create_node.id, actionable_ids)
        self.assertNotIn(video_share_node.id, actionable_ids)

        # 4. Verify Clusters
        clusters = engine.get_focus_clusters()
        self.assertIn("Account & Auth", clusters)
        self.assertIn("Media & Content", clusters)

    def test_notification_bridge(self) -> None:
        bridge = NotificationBridge(ntfy_topic="test_user_topic_12345", default_channel="all")

        # macOS notification (simulated on Linux, osascript on Darwin)
        macos_ok = bridge.notify_macos(
            title="Focus Alert",
            message="Switching to Go backend",
            subtitle="QBX FreeSWITCH",
        )
        self.assertTrue(macos_ok)

        # Remind task convenience method
        res = bridge.remind_task(
            task="Account Recovery of Flynn, Shaheen(first)",
            reason="Blocked user ticket",
            channel="macos",
        )
        self.assertTrue(res["macos"])
        self.assertTrue(res["delivered"])

    def test_ai_reasoning_engine_deterministic_fallback(self) -> None:
        engine = AITaskReasoningEngine(api_key=None)

        # 1. Deterministic embedding test
        emb1 = engine.compute_local_embedding("Microsoft Video Create")
        emb2 = engine.compute_local_embedding("Ghost Sender Video Share")
        emb3 = engine.compute_local_embedding("Database PostgreSQL migration")

        self.assertEqual(len(emb1), 128)
        sim_video = engine.cosine_similarity(emb1, emb2)
        sim_db = engine.cosine_similarity(emb1, emb3)

        # Both video tasks should have higher semantic similarity than database task
        self.assertGreater(sim_video, sim_db)

        # 2. Reasoning with current macOS focus context
        current_focus = {
            "app_name": "Google Chrome",
            "window_title": "Account Settings - Flynn Recovery",
            "bundle_id": "com.google.Chrome",
        }
        reasoning = engine.reason_next_action(self.sample_tasks, current_focus=current_focus)

        self.assertIsNotNone(reasoning["suggested_task"])
        self.assertEqual(reasoning["mode"], "local_deterministic_fallback")
        self.assertIn("Account Recovery", reasoning["suggested_task"]["text"])
        self.assertTrue(len(reasoning["actionable_tasks"]) > 0)


if __name__ == "__main__":
    unittest.main()
