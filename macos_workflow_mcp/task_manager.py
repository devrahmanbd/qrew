"""Markdown Task Management module for MCP server with Obsidian Vault support."""

from __future__ import annotations

import datetime
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Task:
    """Representation of a markdown task."""

    line_number: int
    text: str
    completed: bool
    section: str
    tags: List[str] = field(default_factory=list)
    raw_line: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
        return asdict(self)


class MarkdownTaskManager:
    """Manages tasks stored in local Markdown files or an Obsidian Task-List folder."""

    TASK_REGEX = re.compile(r"^(\s*[-*+]\s+\[)([ xX])(\]\s*)(.*)$")
    HEADER_REGEX = re.compile(r"^(#+)\s+(.+)$")
    TAG_REGEX = re.compile(r"(?:(?<=^)|(?<=\s))([#@][\w-]+)")
    DATE_FILE_REGEX = re.compile(r"^(\d{1,2}-[A-Za-z]{3})(?:\.md)?$")

    def __init__(
        self,
        default_file: Optional[str] = None,
        task_dir: Optional[str] = None,
    ) -> None:
        self.default_file = os.path.expanduser(default_file) if default_file else None
        self.task_dir = os.path.expanduser(task_dir) if task_dir else None

    def _get_today_filename(self) -> str:
        now = datetime.datetime.now()
        return f"{now.day}-{now.strftime('%b')}.md"

    def _resolve_file_path(self, file_path: Optional[str], create_if_missing: bool = False) -> str:
        path_str = file_path.strip() if file_path else ""
        target: Optional[Path] = None

        if path_str:
            if path_str.lower() in ("today", "current"):
                today_name = self._get_today_filename()
                if self.task_dir:
                    target = Path(self.task_dir) / today_name
                elif self.default_file:
                    target = Path(self.default_file)
                else:
                    target = Path(today_name)
            else:
                date_match = self.DATE_FILE_REGEX.match(path_str)
                if self.task_dir and date_match and not os.path.isabs(path_str):
                    target = Path(self.task_dir) / f"{date_match.group(1)}.md"
                elif self.task_dir and not os.path.isabs(path_str):
                    candidate = Path(self.task_dir) / path_str
                    if candidate.exists():
                        target = candidate
                    elif not path_str.endswith(".md") and (Path(self.task_dir) / f"{path_str}.md").exists():
                        target = Path(self.task_dir) / f"{path_str}.md"
                    else:
                        target = Path(path_str).expanduser()
                else:
                    target = Path(path_str).expanduser()
        else:
            if self.default_file:
                target = Path(self.default_file)
            elif self.task_dir:
                today_name = self._get_today_filename()
                today_path = Path(self.task_dir) / today_name
                if today_path.exists() or create_if_missing:
                    target = today_path
                else:
                    dir_path = Path(self.task_dir)
                    if dir_path.is_dir():
                        md_files = sorted(dir_path.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
                        target = md_files[0] if md_files else today_path
                    else:
                        target = today_path
            else:
                raise ValueError("No file path specified and neither default_file nor task_dir configured.")

        target = target.resolve()
        if not target.exists():
            if create_if_missing:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
                date_m = re.match(r"^(\d{1,2}-[A-Za-z]{3})\.md$", target.name)
                if date_m:
                    target.write_text(f"## {date_m.group(1)}\n\n", encoding="utf-8")
            else:
                raise FileNotFoundError(f"File not found: {target}")

        return str(target)

    @classmethod
    def _extract_tags(cls, text: str) -> List[str]:
        return cls.TAG_REGEX.findall(text)

    def _parse_file(self, file_path: Optional[str]) -> Tuple[List[str], List[Task]]:
        resolved = self._resolve_file_path(file_path)
        with open(resolved, "r", encoding="utf-8") as f:
            lines = f.readlines()

        tasks: List[Task] = []
        current_section = "General"

        for idx, line in enumerate(lines, start=1):
            line_stripped = line.strip()
            header_match = self.HEADER_REGEX.match(line_stripped)
            if header_match:
                current_section = line_stripped
                continue

            task_match = self.TASK_REGEX.match(line)
            if task_match:
                checkbox_char = task_match.group(2)
                task_content = task_match.group(4).strip()
                completed = checkbox_char.lower() == "x"
                tags = self._extract_tags(task_content)

                task = Task(
                    line_number=idx,
                    text=task_content,
                    completed=completed,
                    section=current_section,
                    tags=tags,
                    raw_line=line.rstrip("\r\n"),
                )
                tasks.append(task)

        return lines, tasks

    @staticmethod
    def _atomic_write(file_path: str, lines: List[str]) -> None:
        dir_name = os.path.dirname(os.path.abspath(file_path))
        os.makedirs(dir_name, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=dir_name, encoding="utf-8", delete=False) as tf:
            tf.writelines(lines)
            temp_path = tf.name
        os.replace(temp_path, file_path)

    def list_tasks(
        self,
        file_path: Optional[str] = None,
        status: str = "all",
        section: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        _, tasks = self._parse_file(file_path)
        filtered: List[Task] = []
        norm_status = status.lower().strip()

        for t in tasks:
            if norm_status in ("open", "pending") and t.completed:
                continue
            if norm_status in ("completed", "done") and not t.completed:
                continue
            if norm_status not in ("all", "open", "pending", "completed", "done"):
                raise ValueError(f"Invalid status filter '{status}'. Must be 'all', 'open', or 'completed'.")

            if section:
                target_section = section.strip().lower()
                clean_task_section = t.section.lstrip("#").strip().lower()
                clean_target = target_section.lstrip("#").strip()
                if (target_section not in t.section.lower()) and (clean_target not in clean_task_section):
                    continue

            if tag:
                target_tag = tag.strip().lower()
                matched = any(
                    tg.lower() == target_tag or tg.lower().lstrip("#@") == target_tag.lstrip("#@")
                    for tg in t.tags
                )
                if not matched:
                    continue

            filtered.append(t)

        return [t.to_dict() for t in filtered]

    def add_task(
        self,
        file_path: Optional[str] = None,
        task_text: str = "",
        section: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not task_text.strip():
            raise ValueError("Task text cannot be empty.")

        resolved = self._resolve_file_path(file_path, create_if_missing=True)
        with open(resolved, "r", encoding="utf-8") as f:
            lines = f.readlines()

        task_line = f"- [ ] {task_text.strip()}\n"
        target_path = Path(resolved)
        date_m = re.match(r"^(\d{1,2}-[A-Za-z]{3})\.md$", target_path.name)

        effective_section = section
        if effective_section is None or effective_section.strip() in ("", "Inbox"):
            if date_m:
                effective_section = f"## {date_m.group(1)}"
            elif effective_section is None:
                effective_section = None
            else:
                effective_section = "## Inbox"

        if not effective_section:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(task_line)
        else:
            sec_clean = effective_section.strip()
            header_level = "##" if not sec_clean.startswith("#") else ""
            desired_header = f"{header_level} {sec_clean}".strip() if header_level else sec_clean

            header_idx: Optional[int] = None
            for idx, line in enumerate(lines):
                line_stripped = line.strip()
                match = self.HEADER_REGEX.match(line_stripped)
                if match:
                    header_title = match.group(2).strip().lower()
                    req_title = desired_header.lstrip("#").strip().lower()
                    if line_stripped.lower() == desired_header.lower() or header_title == req_title:
                        header_idx = idx
                        break

            if header_idx is not None:
                insert_idx = len(lines)
                for i in range(header_idx + 1, len(lines)):
                    if self.HEADER_REGEX.match(lines[i].strip()):
                        insert_idx = i
                        break

                while insert_idx > header_idx + 1 and lines[insert_idx - 1].strip() == "":
                    insert_idx -= 1

                if insert_idx > 0 and not lines[insert_idx - 1].endswith("\n"):
                    lines[insert_idx - 1] += "\n"

                lines.insert(insert_idx, task_line)
            else:
                if lines and not lines[-1].endswith("\n"):
                    lines[-1] += "\n"
                if lines and lines[-1].strip() != "":
                    lines.append("\n")

                lines.append(f"{desired_header}\n\n")
                lines.append(task_line)

        self._atomic_write(resolved, lines)
        _, tasks = self._parse_file(resolved)
        matches = [t for t in tasks if t.text == task_text.strip()]
        if matches:
            return matches[-1].to_dict()

        return {
            "text": task_text.strip(),
            "completed": False,
            "section": effective_section or "General",
            "tags": self._extract_tags(task_text.strip()),
            "raw_line": task_line.strip(),
        }

    def _find_task_index(self, lines: List[str], task_identifier: Any) -> int:
        if isinstance(task_identifier, int) or (isinstance(task_identifier, str) and task_identifier.strip().isdigit()):
            line_idx = int(task_identifier) - 1
            if 0 <= line_idx < len(lines):
                if self.TASK_REGEX.match(lines[line_idx]):
                    return line_idx
                raise ValueError(f"Line {task_identifier} is not a markdown task.")
            raise ValueError(f"Line number {task_identifier} is out of range.")

        query = str(task_identifier).strip().lower()
        if not query:
            raise ValueError("Task identifier cannot be empty.")

        for idx, line in enumerate(lines):
            match = self.TASK_REGEX.match(line)
            if match and query in match.group(4).strip().lower():
                return idx

        raise ValueError(f"No task matching '{task_identifier}' was found.")

    def update_task_status(
        self,
        file_path: Optional[str] = None,
        task_identifier: Any = "",
        completed: bool = True,
    ) -> Dict[str, Any]:
        resolved = self._resolve_file_path(file_path)
        with open(resolved, "r", encoding="utf-8") as f:
            lines = f.readlines()

        idx = self._find_task_index(lines, task_identifier)
        original_line = lines[idx]
        match = self.TASK_REGEX.match(original_line)
        if not match:
            raise ValueError(f"Matched line is not a valid task: {original_line}")

        prefix = match.group(1)
        suffix = match.group(3) + match.group(4)
        new_checkbox = "x" if completed else " "
        ending = "\n" if original_line.endswith("\n") else ""

        updated_line = f"{prefix}{new_checkbox}{suffix}{ending}"
        lines[idx] = updated_line
        self._atomic_write(resolved, lines)

        _, tasks = self._parse_file(resolved)
        for t in tasks:
            if t.line_number == idx + 1:
                return t.to_dict()

        return {"line_number": idx + 1, "completed": completed, "raw_line": updated_line.rstrip("\r\n")}

    def delete_task(self, file_path: Optional[str] = None, task_identifier: Any = "") -> Dict[str, Any]:
        resolved = self._resolve_file_path(file_path)
        _, tasks = self._parse_file(resolved)
        with open(resolved, "r", encoding="utf-8") as f:
            lines = f.readlines()

        idx = self._find_task_index(lines, task_identifier)
        deleted = next((t.to_dict() for t in tasks if t.line_number == idx + 1), {})
        del lines[idx]
        self._atomic_write(resolved, lines)
        return deleted

    def get_task_summary(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        resolved = self._resolve_file_path(file_path)
        _, tasks = self._parse_file(resolved)

        total = len(tasks)
        completed = sum(1 for t in tasks if t.completed)
        open_tasks = total - completed
        breakdown: Dict[str, Dict[str, int]] = {}
        top_open: List[Dict[str, Any]] = []

        for t in tasks:
            sec = t.section
            if sec not in breakdown:
                breakdown[sec] = {"total": 0, "open": 0, "completed": 0}
            breakdown[sec]["total"] += 1
            if t.completed:
                breakdown[sec]["completed"] += 1
            else:
                breakdown[sec]["open"] += 1
                if len(top_open) < 5:
                    top_open.append(t.to_dict())

        return {
            "file": os.path.basename(resolved),
            "total_tasks": total,
            "open_tasks": open_tasks,
            "completed_tasks": completed,
            "breakdown_by_section": breakdown,
            "top_open_tasks": top_open,
        }

    def list_task_files(self) -> List[str]:
        if not self.task_dir:
            return []
        dir_path = Path(self.task_dir)
        if not dir_path.is_dir():
            return []
        files = sorted(dir_path.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [f.name for f in files]
