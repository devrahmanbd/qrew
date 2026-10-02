"""
AI Task Reasoning Engine for macOS Workflow MCP.
Integrates with OpenRouter API using:
  - 'nvidia/nemotron-3-embed-1b:free' for embeddings
  - 'nvidia/nemotron-3-ultra-550b-a55b:free' for reasoning & thinking
Provides an offline deterministic fallback using character n-gram/hash projection
and heuristic graph-topological weighting.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .graph_engine import TaskGraphEngine, TaskNode

logger = logging.getLogger("macos_workflow_mcp.ai_engine")


class AITaskReasoningEngine:
    """
    Cognitive reasoning engine for tasks and workflow alignment.
    Supports OpenRouter remote AI inference with automatic fallback to
    deterministic local semantic projection and graph topology.
    """

    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    MODEL_EMBED = "nvidia/nemotron-3-embed-1b:free"
    MODEL_THINK = "nvidia/nemotron-3-ultra-550b-a55b:free"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        site_url: str = "https://github.com/macos-workflow-mcp",
        app_name: str = "macOS Workflow MCP",
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = (base_url or self.OPENROUTER_BASE_URL).rstrip("/")
        self.site_url = site_url
        self.app_name = app_name
        self.graph_engine = TaskGraphEngine()

    # --- Embeddings & Local Vector Fallback ---

    def get_embedding(self, text: str) -> List[float]:
        """
        Fetch embedding vector from OpenRouter (nvidia/nemotron-3-embed-1b:free)
        or compute deterministic local n-gram hash vector if offline.
        """
        if self.api_key:
            try:
                return self._fetch_remote_embedding(text)
            except Exception as e:
                logger.warning(f"Remote embedding call failed, falling back to local: {e}")

        return self.compute_local_embedding(text)

    def _fetch_remote_embedding(self, text: str) -> List[float]:
        """Call OpenRouter embeddings API."""
        url = f"{self.base_url}/embeddings"
        payload = json.dumps({
            "model": self.MODEL_EMBED,
            "input": text,
        }).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": self.app_name,
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=12) as response:
            res_json = json.loads(response.read().decode("utf-8"))
            data = res_json.get("data", [])
            if data and "embedding" in data[0]:
                return data[0]["embedding"]
            raise ValueError(f"Invalid embedding response format: {res_json}")

    @staticmethod
    def compute_local_embedding(text: str, dim: int = 128) -> List[float]:
        """
        Deterministic, offline n-gram hash projection into a normalized dense vector.
        Captures semantic similarity across subwords, roots, and task domain tokens.
        """
        vec = [0.0] * dim
        normalized = text.lower().strip()
        tokens = re.findall(r"\w+", normalized)

        # Bag of words + character n-grams (3-grams and 4-grams)
        features: List[str] = list(tokens)
        for token in tokens:
            if len(token) >= 3:
                for i in range(len(token) - 2):
                    features.append(token[i:i+3])
            if len(token) >= 4:
                for i in range(len(token) - 3):
                    features.append(token[i:i+4])

        for feat in features:
            h = int(hashlib.md5(feat.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
            vec[idx] += sign

        # L2 normalization
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """Calculate cosine similarity between two unit vectors."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        return max(-1.0, min(1.0, sum(a * b for a, b in zip(v1, v2))))

    # --- Reasoning & Topological Synthesis ---

    def reason_next_action(
        self,
        tasks: List[Any],
        current_focus: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Synthesizes task DAG with current macOS focus (active app/window).
        Uses Nemotron Ultra 550B via OpenRouter if available, or deterministic
        topological + embedding relevance weighting.
        """
        # Step 1: Construct Graph Topology
        graph = self.graph_engine.build_graph(tasks)
        actionable_nodes = self.graph_engine.get_actionable_tasks()
        all_ordered = self.graph_engine.get_topological_order()
        clusters = self.graph_engine.get_focus_clusters()

        if not actionable_nodes:
            return {
                "suggested_task": None,
                "reasoning": "All tasks are completed or blocked by pending dependencies.",
                "actionable_tasks": [],
                "clusters": clusters,
                "mode": "deterministic_graph",
            }

        # Step 2: Try Remote Thinking via OpenRouter
        if self.api_key:
            try:
                remote_result = self._think_with_openrouter(actionable_nodes, current_focus)
                if remote_result:
                    remote_result["clusters"] = clusters
                    remote_result["mode"] = "openrouter_nemotron_ultra"
                    return remote_result
            except Exception as e:
                logger.warning(f"Remote Nemotron reasoning failed, falling back to local: {e}")

        # Step 3: Offline Deterministic Fallback
        return self._local_deterministic_reasoning(actionable_nodes, current_focus, clusters)

    def _local_deterministic_reasoning(
        self,
        actionable: List[TaskNode],
        current_focus: Optional[Dict[str, str]],
        clusters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Combines topological priority score with cosine similarity against active macOS window.
        """
        focus_text = ""
        if current_focus:
            focus_app = current_focus.get("app_name", "")
            focus_window = current_focus.get("window_title", "")
            focus_text = f"{focus_app} {focus_window}".strip()

        focus_vec = self.compute_local_embedding(focus_text) if focus_text else None

        scored_candidates: List[Tuple[float, TaskNode, str]] = []

        for node in actionable:
            # Base topological score (1.0 to 100+)
            combined_score = node.priority_score

            rationale_parts = []
            if node.priority_score >= 50.0:
                rationale_parts.append("Tagged as immediate priority (e.g., '(first)')")
            if len(node.dependents) > 0:
                rationale_parts.append(f"Unblocks {len(node.dependents)} downstream task(s)")

            # Focus context affinity bonus
            if focus_vec:
                task_vec = self.compute_local_embedding(node.text)
                sim = self.cosine_similarity(focus_vec, task_vec)
                if sim > 0.15:
                    combined_score += sim * 35.0
                    rationale_parts.append(f"Aligns with active macOS focus ({round(sim, 2)} affinity)")

            rationale_str = "; ".join(rationale_parts) or "Next eligible item in DAG sequence"
            scored_candidates.append((combined_score, node, rationale_str))

        scored_candidates.sort(key=lambda item: item[0], reverse=True)
        top_score, best_node, top_rationale = scored_candidates[0]

        return {
            "suggested_task": best_node.to_dict(),
            "reasoning": f"Recommended by topological weighting: {top_rationale}.",
            "actionable_tasks": [node.to_dict() for _, node, _ in scored_candidates],
            "clusters": clusters,
            "mode": "local_deterministic_fallback",
        }

    def _think_with_openrouter(
        self,
        actionable: List[TaskNode],
        current_focus: Optional[Dict[str, str]],
    ) -> Optional[Dict[str, Any]]:
        """Call OpenRouter with nvidia/nemotron-3-ultra-550b-a55b:free."""
        task_prompts = [
            f"- ID: {n.id} | Text: \"{n.text}\" | Priority: {n.priority_score} | Cluster: {n.cluster} | Unblocks: {list(n.dependents)}"
            for n in actionable
        ]
        focus_summary = (
            f"Active App: {current_focus.get('app_name', 'None')}, Window: {current_focus.get('window_title', 'None')}"
            if current_focus
            else "None"
        )

        sys_msg = (
            "You are an expert autonomous developer workflow orchestrator. "
            "Analyze the ready tasks and active macOS focus to select the single best task to do next. "
            "Respond strictly in valid JSON format with keys: 'suggested_task_id' (string), 'reasoning' (string)."
        )

        user_msg = (
            f"Current macOS Focus: {focus_summary}\n\n"
            f"Actionable Tasks (prerequisites satisfied):\n" + "\n".join(task_prompts)
        )

        url = f"{self.base_url}/chat/completions"
        payload = json.dumps({
            "model": self.MODEL_THINK,
            "messages": [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": self.app_name,
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as response:
            res_json = json.loads(response.read().decode("utf-8"))
            content = res_json["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            chosen_id = parsed.get("suggested_task_id")
            reasoning = parsed.get("reasoning", "Selected via Nemotron reasoning.")

            matched_node = next((n for n in actionable if n.id == chosen_id), actionable[0])

            return {
                "suggested_task": matched_node.to_dict(),
                "reasoning": reasoning,
                "actionable_tasks": [n.to_dict() for n in actionable],
            }
