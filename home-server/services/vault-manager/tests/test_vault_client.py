"""Tests for the Obsidian vault client."""

from __future__ import annotations

from pathlib import Path

import pytest

from vault_client import VaultClient


@pytest.fixture
def vault(tmp_path: Path) -> VaultClient:
    """Create a vault client with a temp directory."""
    client = VaultClient(tmp_path)
    client.initialize()
    return client


class TestInitialize:
    def test_creates_required_directories(self, vault: VaultClient) -> None:
        assert (vault.path / "daily").is_dir()
        assert (vault.path / "tasks").is_dir()
        assert (vault.path / "people").is_dir()
        assert (vault.path / "projects").is_dir()
        assert (vault.path / "health" / "sleep").is_dir()
        assert (vault.path / "health" / "nutrition").is_dir()
        assert (vault.path / "private" / "notes").is_dir()
        assert (vault.path / "private" / "suggestions").is_dir()
        assert (vault.path / "agent").is_dir()
        assert (vault.path / "templates").is_dir()


class TestDailyNotes:
    def test_create_daily_note(self, vault: VaultClient) -> None:
        path = vault.create_daily_note("2026-02-19")
        assert path.exists()
        content = path.read_text()
        assert "2026-02-19" in content
        assert "Daily Log" in content

    def test_create_daily_note_idempotent(self, vault: VaultClient) -> None:
        path1 = vault.create_daily_note("2026-02-19")
        path1.write_text("custom content")
        path2 = vault.create_daily_note("2026-02-19")
        assert path1 == path2
        assert path2.read_text() == "custom content"

    def test_get_daily_note_path(self, vault: VaultClient) -> None:
        path = vault.get_daily_note_path("2026-02-19")
        assert path.name == "2026-02-19.md"
        assert "daily" in str(path)

    def test_append_time_block(self, vault: VaultClient) -> None:
        vault.create_daily_note("2026-02-19")
        vault.append_time_block("2026-02-19", "07:00-07:30", "- Conversation with wife about plans")
        content = vault.get_daily_note_path("2026-02-19").read_text()
        assert "07:00-07:30" in content
        assert "Conversation with wife" in content

    def test_append_time_block_creates_note_if_missing(self, vault: VaultClient) -> None:
        vault.append_time_block("2026-03-01", "08:00-08:30", "- Meeting notes")
        assert vault.get_daily_note_path("2026-03-01").exists()

    def test_update_morning_briefing(self, vault: VaultClient) -> None:
        vault.create_daily_note("2026-02-19")
        vault.update_morning_briefing("2026-02-19", "Standup at 9, 1-on-1 at 2", "2 pending tasks")
        content = vault.get_daily_note_path("2026-02-19").read_text()
        assert "Standup at 9" in content
        assert "2 pending tasks" in content

    def test_update_daily_summary(self, vault: VaultClient) -> None:
        vault.create_daily_note("2026-02-19")
        vault.update_daily_summary("2026-02-19", "Productive day, 3 tasks completed")
        content = vault.get_daily_note_path("2026-02-19").read_text()
        assert "Productive day" in content


class TestTaskNotes:
    def test_create_task_note(self, vault: VaultClient) -> None:
        path = vault.create_task_note(
            task_id="abc12345",
            title="Schedule Daughter Haircut",
            context="Wife asked to schedule it this weekend",
            source="conversation",
            due_date="2026-02-22",
            people=["wife", "daughter"],
        )
        assert path.exists()
        content = path.read_text()
        assert "Schedule Daughter Haircut" in content
        assert "abc12345" in content
        assert "[[wife]]" in content
        assert "[[daughter]]" in content
        assert "2026-02-22" in content

    def test_create_private_task_note(self, vault: VaultClient) -> None:
        path = vault.create_task_note(
            task_id="prv12345",
            title="Private Task",
            context="Private context",
            is_private=True,
        )
        assert "private" in str(path)
        assert path.exists()

    def test_update_task_note_status(self, vault: VaultClient) -> None:
        path = vault.create_task_note("t1", "Test", "context")
        vault.update_task_note_status(path, "completed")
        content = path.read_text()
        assert "status: completed" in content


class TestPeopleNotes:
    def test_create_person_note(self, vault: VaultClient) -> None:
        path = vault.create_person_note("Jane Smith", relationship="coworker", context="QA team")
        assert path.exists()
        content = path.read_text()
        assert "Jane Smith" in content
        assert "coworker" in content

    def test_create_person_note_idempotent(self, vault: VaultClient) -> None:
        path1 = vault.create_person_note("Bob")
        path1.write_text("custom")
        path2 = vault.create_person_note("Bob")
        assert path1 == path2
        assert path2.read_text() == "custom"

    def test_update_person_conversation(self, vault: VaultClient) -> None:
        vault.create_person_note("Alice")
        vault.update_person_conversation("Alice", "2026-02-19", "Discussed weekend plans")
        path = vault.path / "people" / "alice.md"
        content = path.read_text()
        assert "[[2026-02-19]]" in content
        assert "Discussed weekend plans" in content


class TestPrivateNotes:
    def test_create_private_note(self, vault: VaultClient) -> None:
        path = vault.create_private_note("My Private Thought", "Some private content")
        assert path.exists()
        assert "private" in str(path)
        content = path.read_text()
        assert "private" in content.lower()
        assert "Some private content" in content


class TestSearch:
    def test_search_finds_matching_notes(self, vault: VaultClient) -> None:
        vault.create_daily_note("2026-02-19")
        vault.append_time_block("2026-02-19", "07:00-07:30", "- Discussion about vacation")
        results = vault.search_notes("vacation")
        assert len(results) >= 1
        assert any("vacation" in r["snippet"].lower() for r in results)

    def test_search_excludes_private_by_default(self, vault: VaultClient) -> None:
        vault.create_private_note("Secret", "hidden content 12345")
        results = vault.search_notes("hidden content 12345")
        assert len(results) == 0

    def test_search_in_specific_section(self, vault: VaultClient) -> None:
        vault.create_person_note("TestPerson", context="unique_keyword_xyz")
        results = vault.search_notes("unique_keyword_xyz", section="people")
        assert len(results) >= 1

    def test_search_no_results(self, vault: VaultClient) -> None:
        results = vault.search_notes("nonexistent_query_string")
        assert len(results) == 0


class TestAgentNotes:
    def test_update_self_assessment(self, vault: VaultClient) -> None:
        vault.update_agent_self_assessment("# Self Assessment\nDoing well today.")
        path = vault.path / "agent" / "self-assessment.md"
        assert path.exists()
        assert "Doing well" in path.read_text()

    def test_append_pattern(self, vault: VaultClient) -> None:
        vault.append_agent_pattern("User frequently asks about calendar in morning")
        vault.append_agent_pattern("User prefers concise responses")
        content = (vault.path / "agent" / "patterns.md").read_text()
        assert "calendar" in content
        assert "concise" in content
