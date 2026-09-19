"""Reading a tool call: which lines changed, and what a shell command was for."""

from __future__ import annotations

from prudence.store import edits

PATCH = {
    "filePath": "/repo/src/parser.py",
    "structuredPatch": [
        {
            "oldStart": 1,
            "oldLines": 2,
            "newStart": 1,
            "newLines": 3,
            "lines": ["-    return None", "+    return value", "+    # explained"],
        }
    ],
}


def test_an_edit_with_a_structured_patch_is_read_from_the_patch() -> None:
    facts = edits.extract_edit("Edit", {"file_path": "/repo/src/parser.py"}, PATCH)
    assert facts is not None
    assert facts.added == ["    return value", "    # explained"]
    assert facts.removed == ["    return None"]
    assert facts.is_new_file is False
    assert facts.file_path == "/repo/src/parser.py"


def test_an_edit_without_a_result_is_diffed_from_its_own_input() -> None:
    payload = {
        "file_path": "/repo/src/parser.py",
        "old_string": "def parse():\n    return None\n",
        "new_string": "def parse():\n    return value\n",
    }
    facts = edits.extract_edit("Edit", payload, None)
    assert facts is not None
    assert facts.added == ["    return value"], "only the line that really changed"
    assert facts.removed == ["    return None"]


def test_a_write_of_a_new_file_counts_every_line_as_added() -> None:
    payload = {"file_path": "/repo/src/new.py", "content": "alpha = 1\nbeta = 2\n"}
    facts = edits.extract_edit("Write", payload, {"type": "create", "filePath": "/repo/src/new.py"})
    assert facts is not None
    assert facts.added == ["alpha = 1", "beta = 2"]
    assert facts.removed == []
    assert facts.is_new_file is True


def test_a_tool_that_does_not_edit_produces_nothing() -> None:
    assert edits.extract_edit("Read", {"file_path": "/repo/src/parser.py"}, None) is None
    assert edits.extract_edit("Edit", {}, None) is None


def test_commands_are_classified_by_what_they_do() -> None:
    assert edits.classify_command("git commit -m 'work'") == "git_commit"
    assert edits.classify_command("git -C /tmp/repo commit -m x") == "git_commit"
    assert edits.classify_command("git -c user.name=t commit --amend") == "git_commit"
    assert edits.classify_command("git log --oneline | grep commit") == "git_other"
    assert edits.classify_command("git status") == "git_other"
    assert edits.classify_command("uv run pytest -q") == "test"
    assert edits.classify_command("npm test") == "test"
    assert edits.classify_command("cargo test --all") == "test"
    assert edits.classify_command("uv run ruff format src/") == "formatter"
    assert edits.classify_command("npx prettier --write .") == "formatter"
    assert edits.classify_command("eslint src --fix") == "formatter"
    assert edits.classify_command("ls -la") == "other"
    assert edits.classify_command(None) == "other"


def test_a_commit_that_runs_after_the_tests_is_still_a_commit() -> None:
    assert edits.classify_command("pytest -q && git commit -m done") == "git_commit"


def test_the_commit_hash_is_read_from_the_bracket_git_prints() -> None:
    result = {"stdout": "[main abc1234] add the parser\n 2 files changed", "stderr": ""}
    assert edits.read_result(result) == (None, "abc1234")
    root = {"stdout": "[master (root-commit) 0f1e2d3] first", "stderr": ""}
    assert edits.read_result(root)[1] == "0f1e2d3"
    assert edits.read_result({"stdout": "nothing to commit"})[1] is None


def test_a_structured_commit_field_is_preferred_over_the_printed_one() -> None:
    result = {
        "stdout": "[main abc1234] add the parser",
        "gitOperation": {"commit": {"kind": "create", "sha": "abcdef1234567890"}},
    }
    assert edits.read_result(result)[1] == "abcdef1234567890"


def test_metadata_only_keeps_the_class_and_drops_the_text() -> None:
    payload = {"command": "git commit -m 'secret branch name'"}
    full = edits.extract_command("Bash", payload, full=True)
    metadata = edits.extract_command("Bash", payload, full=False)
    assert full is not None and metadata is not None
    assert full.command_text == payload["command"]
    assert metadata.command_text is None
    assert metadata.command_class == "git_commit"
