"""
Task Graph Engine for macOS Workflow MCP.
Constructs Directed Acyclic Graphs (DAGs) for tasks, detects dependencies
(e.g., "(first)", "Create" before "Share"), and computes topological priority scores and clusters.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class TaskNode:
    """Represents a node in the task dependency graph."""

    id: str
    text: str
    completed: bool = False
    line_number: int = 0
    section: str = "General"
    tags: List[str] = field(default_factory=list)
    dependencies: Set[str] = field(default_factory=set)  # IDs of tasks that must be done before this one
    dependents: Set[str] = field(default_factory=set)    # IDs of tasks waiting on this one
    priority_score: float = 0.0
    cluster: str = "General"
    raw_line: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert task node to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "text": self.text,
            "completed": self.completed,
            "line_number": self.line_number,
            "section": self.section,
            "tags": list(self.tags),
            "dependencies": sorted(list(self.dependencies)),
            "dependents": sorted(list(self.dependents)),
            "priority_score": round(self.priority_score, 3),
            "cluster": self.cluster,
        }


class TaskGraphEngine:
    """
    Constructs a dependency DAG from a task list and computes topological priorities.
    Supports heuristic sequence detection (e.g. Create -> Share, Setup -> Run),
    explicit keyword flags like '(first)' or '(after X)', and semantic clustering.
    """

    # Keyword patterns indicating immediate priority
    FIRST_PATTERNS = [
        re.compile(r"\(first\)", re.IGNORECASE),
        re.compile(r"\(urgent\)", re.IGNORECASE),
        re.compile(r"\(priority\)", re.IGNORECASE),
        re.compile(r"\[p0\]", re.IGNORECASE),
        re.compile(r"#p0\b", re.IGNORECASE),
    ]

    # Paired workflow verbs: First action must precede second action
    WORKFLOW_VERB_PAIRS: List[Tuple[str, str]] = [
        ("create", "share"),
        ("create", "send"),
        ("create", "publish"),
        ("create", "upload"),
        ("record", "edit"),
        ("edit", "share"),
        ("edit", "publish"),
        ("setup", "configure"),
        ("configure", "deploy"),
        ("setup", "run"),
        ("build", "deploy"),
        ("build", "test"),
        ("test", "release"),
        ("recovery", "login"),
    ]

    # Cluster keyword mappings
    CLUSTER_RULES: Dict[str, List[str]] = {
        "Account & Auth": ["account", "recovery", "login", "auth", "password", "signup", "user", "profile"],
        "Media & Content": ["video", "audio", "record", "stream", "edit", "youtube", "tiktok", "podcast"],
        "Data & Backend": ["db", "database", "sql", "postgres", "redis", "migrate", "text", "script", "api"],
        "Distribution & Marketing": ["share", "send", "ghost", "post", "social", "email", "campaign", "facebook", "twitter"],
        "Development & Code": ["build", "code", "deploy", "frontend", "backend", "test", "docker", "fix", "framique"],
    }

    def __init__(self) -> None:
        self.nodes: Dict[str, TaskNode] = {}

    @staticmethod
    def _normalize_id(text: str) -> str:
        """Create a clean unique slug from task text."""
        cleaned = re.sub(r"\(.*?\)", "", text).strip().lower()
        cleaned = re.sub(r"[^\w\s-]", "", cleaned)
        slug = re.sub(r"[\s_]+", "-", cleaned)
        return slug or "task"

    def _detect_cluster(self, text: str, section: str) -> str:
        """Assign task to a functional cluster based on keywords and section."""
        lower_text = f"{text} {section}".lower()
        scores: Dict[str, int] = {}
        for cluster_name, keywords in self.CLUSTER_RULES.items():
            count = sum(1 for kw in keywords if re.search(r"\b" + re.escape(kw) + r"\b", lower_text))
            if count > 0:
                scores[cluster_name] = count

        if scores:
            return max(scores.items(), key=lambda item: item[1])[0]
        return section.lstrip("#").strip() if section else "General"

    def build_graph(self, raw_tasks: List[Any]) -> Dict[str, TaskNode]:
        """
        Builds TaskNode objects and establishes dependency edges.
        raw_tasks can be dicts or Task dataclass instances.
        """
        self.nodes.clear()

        # Step 1: Create initial nodes
        id_counts: Dict[str, int] = {}
        for item in raw_tasks:
            if hasattr(item, "text"):
                text = item.text
                completed = getattr(item, "completed", False)
                line_no = getattr(item, "line_number", 0)
                sec = getattr(item, "section", "General")
                tags = getattr(item, "tags", [])
                raw_l = getattr(item, "raw_line", "")
            else:
                text = item.get("text", "")
                completed = item.get("completed", False)
                line_no = item.get("line_number", 0)
                sec = item.get("section", "General")
                tags = item.get("tags", [])
                raw_l = item.get("raw_line", "")

            if not text.strip():
                continue

            base_id = self._normalize_id(text)
            id_counts[base_id] = id_counts.get(base_id, 0) + 1
            node_id = base_id if id_counts[base_id] == 1 else f"{base_id}-{id_counts[base_id]}"

            cluster = self._detect_cluster(text, sec)
            self.nodes[node_id] = TaskNode(
                id=node_id,
                text=text,
                completed=completed,
                line_number=line_no,
                section=sec,
                tags=tags,
                cluster=cluster,
                raw_line=raw_l,
            )

        # Step 2: Detect heuristic and explicit dependencies
        node_list = list(self.nodes.values())
        for i, node_a in enumerate(node_list):
            text_a = node_a.text.lower()

            for j, node_b in enumerate(node_list):
                if i == j:
                    continue
                text_b = node_b.text.lower()

                # Check verb pairs with shared or related domain words
                for v_pre, v_post in self.WORKFLOW_VERB_PAIRS:
                    has_pre = re.search(r"\b" + re.escape(v_pre) + r"\b", text_a)
                    has_post = re.search(r"\b" + re.escape(v_post) + r"\b", text_b)
                    if has_pre and has_post:
                        tokens_a = set(re.findall(r"\b\w{3,}\b", text_a)) - {v_pre, "the", "and", "for"}
                        tokens_b = set(re.findall(r"\b\w{3,}\b", text_b)) - {v_post, "the", "and", "for"}
                        overlap = tokens_a & tokens_b
                        
                        if overlap or (node_a.cluster == node_b.cluster and node_a.cluster != "General"):
                            node_b.dependencies.add(node_a.id)
                            node_a.dependents.add(node_b.id)

            # Check explicit '(after <keyword>)' in text
            after_match = re.search(r"\(after\s+([^)]+)\)", node_a.text, re.IGNORECASE)
            if after_match:
                target_word = after_match.group(1).strip().lower()
                for target_node in node_list:
                    if target_node.id != node_a.id and target_word in target_node.text.lower():
                        node_a.dependencies.add(target_node.id)
                        target_node.dependents.add(node_a.id)

        # Step 3: Break any inadvertent cycles to ensure valid DAG
        self._break_cycles()

        # Step 4: Calculate topological priority scores
        self._calculate_priorities()

        return self.nodes

    def _break_cycles(self) -> None:
        """Cycle detection via DFS; removes feedback edges to maintain strict DAG."""
        visited: Dict[str, int] = {}

        def dfs(node_id: str, path: List[str]) -> None:
            visited[node_id] = 1
            node = self.nodes[node_id]
            for dep_id in list(node.dependents):
                if visited.get(dep_id, 0) == 1:
                    node.dependents.discard(dep_id)
                    if dep_id in self.nodes:
                        self.nodes[dep_id].dependencies.discard(node_id)
                elif visited.get(dep_id, 0) == 0:
                    dfs(dep_id, path + [dep_id])
            visited[node_id] = 2

        for nid in list(self.nodes.keys()):
            if visited.get(nid, 0) == 0:
                dfs(nid, [nid])

    def _calculate_priorities(self) -> None:
        """
        Computes priority scores:
        - Base score: Completed tasks = 0.0, open tasks = 10.0
        - Explicit keyword boost: '(first)', '[p0]' = +50.0
        - Dependent unlock multiplier: each unblocked dependent adds +15.0
        - Dependency penalty: unfulfilled dependencies lower current readiness
        """
        for node in self.nodes.values():
            if node.completed:
                node.priority_score = 0.0
                continue

            score = 10.0

            # Explicit priority keywords
            for pat in self.FIRST_PATTERNS:
                if pat.search(node.text):
                    score += 50.0
                    break

            # Unlock potential
            descendant_count = self._count_descendants(node.id, set())
            score += descendant_count * 15.0

            # Readiness check: are prerequisites already done?
            unmet_deps = sum(
                1 for dep_id in node.dependencies
                if dep_id in self.nodes and not self.nodes[dep_id].completed
            )
            if unmet_deps > 0:
                score -= unmet_deps * 12.0

            node.priority_score = max(1.0, score)

    def _count_descendants(self, node_id: str, visited: Set[str]) -> int:
        """Recursively count all downstream dependents."""
        if node_id not in self.nodes:
            return 0
        count = 0
        for dep_id in self.nodes[node_id].dependents:
            if dep_id not in visited:
                visited.add(dep_id)
                count += 1 + self._count_descendants(dep_id, visited)
        return count

    def get_topological_order(self) -> List[TaskNode]:
        """
        Returns all open tasks ordered by priority score and topological viability.
        """
        open_nodes = [n for n in self.nodes.values() if not n.completed]
        return sorted(open_nodes, key=lambda n: (-n.priority_score, n.line_number))

    def get_actionable_tasks(self) -> List[TaskNode]:
        """
        Returns tasks ready to be executed immediately (dependencies satisfied).
        """
        actionable: List[TaskNode] = []
        for node in self.nodes.values():
            if node.completed:
                continue
            is_ready = True
            for dep_id in node.dependencies:
                dep_node = self.nodes.get(dep_id)
                if dep_node and not dep_node.completed:
                    is_ready = False
                    break
            if is_ready:
                actionable.append(node)

        return sorted(actionable, key=lambda n: -n.priority_score)

    def get_focus_clusters(self) -> Dict[str, List[Dict[str, Any]]]:
        """Group tasks into categorized focus clusters with aggregated status."""
        clusters: Dict[str, List[Dict[str, Any]]] = {}
        for node in self.get_topological_order():
            c = node.cluster
            if c not in clusters:
                clusters[c] = []
            clusters[c].append(node.to_dict())
        return clusters
