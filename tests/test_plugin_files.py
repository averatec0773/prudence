"""`plugin/`: the Claude Code plugin's own files, checked the way a plugin loader would.

Not a pytest.testing of Claude Code itself (there is none to drive here); this file
checks the static shape: the manifest parses, the hook set matches `hooks/__init__.py`,
the shipped hook script is the one Prudence actually runs, and the skills have the
frontmatter a plugin loader requires.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from prudence import hooks as hooks_module

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugin"


def test_plugin_manifest_parses_and_has_the_required_keys() -> None:
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "prudence"
    assert manifest["version"] == "0.0.1"
    assert manifest["description"]
    assert manifest["author"]["name"]


def test_mcp_json_wires_the_prudence_server_by_command() -> None:
    manifest = json.loads((PLUGIN / ".mcp.json").read_text())
    server = manifest["mcpServers"]["prudence"]
    assert server["command"] == "prudence"
    assert server["args"] == ["mcp"]


def test_hooks_json_lists_the_six_events_hooks_install_writes() -> None:
    manifest = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    events = manifest["hooks"]
    expected = {event for event, _matcher in hooks_module.EVENTS}
    assert set(events) == expected

    for event, matcher in hooks_module.EVENTS:
        groups = events[event]
        assert len(groups) == 1
        group = groups[0]
        assert group.get("matcher") == matcher or (matcher is None and "matcher" not in group)
        entries = group["hooks"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["type"] == "command"
        assert "${CLAUDE_PLUGIN_ROOT}" in entry["command"]
        assert entry["command"].endswith(f'prudence-hook.sh" {event}')
        assert entry["timeout"] == hooks_module.TIMEOUT_SECONDS


def test_the_two_hook_scripts_are_byte_identical() -> None:
    packaged = (ROOT / "src" / "prudence" / "hooks" / hooks_module.SCRIPT_NAME).read_bytes()
    shipped = (PLUGIN / "hooks" / hooks_module.SCRIPT_NAME).read_bytes()
    assert packaged == shipped, (
        "plugin/hooks/prudence-hook.sh has drifted from src/prudence/hooks/prudence-hook.sh; "
        "the two must stay identical (see plugin/README.md)"
    )


def test_skills_have_frontmatter_with_a_description() -> None:
    for name in ("sessions", "recall"):
        text = (PLUGIN / "skills" / name / "SKILL.md").read_text()
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        assert match, f"{name}/SKILL.md has no --- frontmatter block"
        frontmatter = match.group(1)
        assert re.search(r"^description:\s*\S", frontmatter, re.MULTILINE), (
            f"{name}/SKILL.md frontmatter has no description"
        )
        assert re.search(rf"^name:\s*{name}\s*$", frontmatter, re.MULTILINE)


def test_plugin_readme_names_the_local_install_command_and_the_privacy_statement() -> None:
    text = (PLUGIN / "README.md").read_text()
    assert "claude --plugin-dir ./plugin" in text
    assert "No message text" in text
    assert "prudence-coach" in text, "the CLI install instruction"
