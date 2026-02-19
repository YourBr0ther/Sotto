"""Obsidian vault file operations for Sotto."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VaultClient:
    """Manages the Obsidian vault filesystem for Sotto.

    Handles creating, reading, and updating markdown files in the vault structure.
    """

    def __init__(self, vault_path: str | Path) -> None:
        self._vault_path = Path(vault_path).resolve()

    def initialize(self) -> None:
        """Ensure all required vault directories exist."""
        directories = [
            "daily", "tasks", "people", "projects",
            "health/sleep", "health/nutrition",
            "private/notes", "private/suggestions",
            "agent", "templates",
        ]
        for d in directories:
            (self._vault_path / d).mkdir(parents=True, exist_ok=True)
        logger.info("Vault initialized at %s", self._vault_path)

    @property
    def path(self) -> Path:
        return self._vault_path

    # --- Daily Notes ---

    def get_daily_note_path(self, date: str | None = None) -> Path:
        """Get the path to a daily note."""
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._vault_path / "daily" / f"{date}.md"

    def create_daily_note(self, date: str | None = None) -> Path:
        """Create a daily note from template if it doesn't exist."""
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        path = self.get_daily_note_path(date)
        if path.exists():
            return path

        content = f"""---
date: {date}
summary: ""
mood: ""
---

# {date} -- Daily Log

## Morning Briefing
- Calendar: (pending)
- Pending tasks: (pending)

## Time Blocks

## Evening Summary
- Tasks completed: (pending)
- Tasks created: (pending)
- Notable moments: (pending)

## Links
"""
        path.write_text(content)
        logger.info("Created daily note: %s", path)
        return path

    def append_time_block(self, date: str, time_range: str, content: str) -> None:
        """Append a time block entry to the daily note."""
        path = self.get_daily_note_path(date)
        if not path.exists():
            self.create_daily_note(date)

        existing = path.read_text()

        # Insert before Evening Summary
        block = f"\n### {time_range}\n{content}\n"
        if "## Evening Summary" in existing:
            existing = existing.replace("## Evening Summary", f"{block}## Evening Summary")
        else:
            existing += block

        path.write_text(existing)
        logger.debug("Appended time block %s to %s", time_range, date)

    def update_daily_summary(self, date: str, summary: str) -> None:
        """Update the summary field in the daily note frontmatter."""
        path = self.get_daily_note_path(date)
        if not path.exists():
            return

        content = path.read_text()
        content = re.sub(r'summary: ".*?"', f'summary: "{summary}"', content)
        path.write_text(content)

    def update_morning_briefing(self, date: str, calendar: str, tasks: str) -> None:
        """Update the morning briefing section."""
        path = self.get_daily_note_path(date)
        if not path.exists():
            self.create_daily_note(date)

        content = path.read_text()
        content = content.replace("- Calendar: (pending)", f"- Calendar: {calendar}")
        content = content.replace("- Pending tasks: (pending)", f"- Pending tasks: {tasks}")
        path.write_text(content)

    # --- Task Notes ---

    def create_task_note(
        self,
        task_id: str,
        title: str,
        context: str,
        source: str = "conversation",
        due_date: str | None = None,
        people: list[str] | None = None,
        is_private: bool = False,
    ) -> Path:
        """Create a task note in the vault."""
        now = datetime.now(timezone.utc).isoformat()
        slug = re.sub(r'[^a-z0-9-]', '-', title.lower())[:50].strip('-')
        date_prefix = datetime.now(timezone.utc).strftime("%Y-%m")

        if is_private:
            path = self._vault_path / "private" / "notes" / f"{slug}-{date_prefix}.md"
        else:
            path = self._vault_path / "tasks" / f"{slug}-{date_prefix}.md"

        people_links = ""
        if people:
            people_links = ", ".join(f"[[{p}]]" for p in people)

        content = f"""---
status: pending
created: {now}
source: {source}
due: {due_date or ""}
remind_at: ""
remind_count: 0
context: "{context}"
task_id: {task_id}
---

# {title}

## Details
- Context: {context}
{f"- Due: {due_date}" if due_date else ""}
{f"- People: {people_links}" if people_links else ""}
- Source: {source}

## Agent Notes

## History
- {now[:10]} -- Task created from {source}
"""
        path.write_text(content)
        logger.info("Created task note: %s", path)
        return path

    def update_task_note_status(self, path: str | Path, status: str) -> None:
        """Update the status in a task note's frontmatter."""
        path = Path(path)
        if not path.exists():
            return

        content = path.read_text()
        content = re.sub(r'status: \w+', f'status: {status}', content)
        path.write_text(content)

    # --- People Notes ---

    def create_person_note(self, name: str, relationship: str = "", context: str = "") -> Path:
        """Create a person note in the vault."""
        slug = re.sub(r'[^a-z0-9-]', '-', name.lower())[:30].strip('-')
        path = self._vault_path / "people" / f"{slug}.md"

        if path.exists():
            return path

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        content = f"""---
name: "{name}"
relationship: "{relationship}"
last_seen: "{today}"
---

# {name}

## Key Information
- Relationship: {relationship}
{f"- Context: {context}" if context else ""}

## Conversation Log

## Things to Remember
"""
        path.write_text(content)
        logger.info("Created person note: %s", path)
        return path

    def update_person_conversation(self, name: str, date: str, summary: str) -> None:
        """Append a conversation entry to a person note."""
        slug = re.sub(r'[^a-z0-9-]', '-', name.lower())[:30].strip('-')
        path = self._vault_path / "people" / f"{slug}.md"

        if not path.exists():
            self.create_person_note(name)
            path = self._vault_path / "people" / f"{slug}.md"

        content = path.read_text()
        entry = f"- [[{date}]]: {summary}\n"

        if "## Conversation Log" in content:
            content = content.replace(
                "## Conversation Log\n",
                f"## Conversation Log\n{entry}",
            )
        else:
            content += f"\n## Conversation Log\n{entry}"

        # Update last_seen
        content = re.sub(r'last_seen: ".*?"', f'last_seen: "{date}"', content)
        path.write_text(content)

    # --- Private Notes ---

    def create_private_note(self, title: str, content: str) -> Path:
        """Create a note in the private section."""
        slug = re.sub(r'[^a-z0-9-]', '-', title.lower())[:50].strip('-')
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._vault_path / "private" / "notes" / f"{slug}-{date}.md"

        note_content = f"""---
created: {datetime.now(timezone.utc).isoformat()}
classification: private
---

# {title}

{content}
"""
        path.write_text(note_content)
        logger.info("Created private note: %s", path.name)
        return path

    # --- Search ---

    def search_notes(self, query: str, section: str | None = None) -> list[dict[str, Any]]:
        """Search notes by content.

        Args:
            query: Text to search for (case-insensitive).
            section: Optional section to limit search (daily, tasks, people, etc.)

        Returns:
            List of matching notes with path and snippet.
        """
        search_path = self._vault_path / section if section else self._vault_path
        search_path = search_path.resolve()
        results = []
        query_lower = query.lower()

        for md_file in search_path.rglob("*.md"):
            try:
                rel_path = str(md_file.relative_to(self._vault_path))
            except ValueError:
                rel_path = str(md_file)

            # Skip private section in general search (check relative path)
            if section is None and rel_path.startswith("private"):
                continue

            try:
                content = md_file.read_text()
                if query_lower in content.lower():
                    # Extract a snippet around the match
                    idx = content.lower().find(query_lower)
                    start = max(0, idx - 50)
                    end = min(len(content), idx + len(query) + 50)
                    snippet = content[start:end].replace("\n", " ")

                    results.append({
                        "path": rel_path,
                        "snippet": snippet,
                    })
            except Exception as e:
                logger.error("Error reading %s: %s", md_file, e)

        return results

    # --- Agent Notes ---

    def update_agent_self_assessment(self, content: str) -> None:
        """Update the agent's self-assessment note."""
        path = self._vault_path / "agent" / "self-assessment.md"
        path.write_text(content)

    def append_agent_pattern(self, pattern: str) -> None:
        """Append a behavioral pattern to the agent's patterns note."""
        path = self._vault_path / "agent" / "patterns.md"
        if not path.exists():
            path.write_text("# Behavioral Patterns\n\n")

        content = path.read_text()
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        content += f"- [{date}] {pattern}\n"
        path.write_text(content)
