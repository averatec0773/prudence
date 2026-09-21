"""The model layer: which backend is chosen, what it sends, and what it refuses.

No test in this file touches a network. `AnthropicModel` is exercised with a fake client
that records the payload, which is the only way to assert the two things that matter
about the request (the system prompt is marked cacheable, thinking is off) without
paying for a call to find out.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prudence import config as config_module
from prudence.model import NoModel, Request, Sent, select_model
from prudence.model import language as language_module
from prudence.model.anthropic_backend import AnthropicModel
from prudence.model.base import Completion, ModelFailed, ModelUnavailable
from prudence.model.guard import complete_checked, correction, judge
from prudence.model.numbers import check_numbers
from prudence.model.prices import cost, estimate
from prudence.model.recorded import RecordedModel, input_hash
from prudence.model.tone import check_tone


def _request(user: str = "the numbers") -> Request:
    return Request(system="a system prompt", user=user, max_tokens=64, sent=Sent(numbers=3))


# --- choosing a backend -------------------------------------------------------------------


def test_select_model_honours_the_environment_over_the_config(tmp_path, monkeypatch) -> None:
    config = config_module.Config(path=tmp_path / "config.toml")
    config.model = config_module.ModelSettings(backend="anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")

    monkeypatch.setenv("PRUDENCE_MODEL", "none")
    assert isinstance(select_model(config), NoModel)

    monkeypatch.setenv("PRUDENCE_MODEL", "recorded")
    monkeypatch.setenv("PRUDENCE_MODEL_FIXTURES", str(tmp_path))
    assert isinstance(select_model(config), RecordedModel)


def test_select_model_reads_the_config_backend(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("PRUDENCE_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    config = config_module.Config(path=tmp_path / "config.toml")

    config.model = config_module.ModelSettings(backend="none")
    assert isinstance(select_model(config), NoModel)

    config.model = config_module.ModelSettings(backend="anthropic", model_id="claude-haiku-4-5")
    chosen = select_model(config)
    assert isinstance(chosen, AnthropicModel)
    assert chosen.id == "claude-haiku-4-5"
    assert select_model(config, model_id="claude-sonnet-5").id == "claude-sonnet-5"


def test_no_key_is_a_no_model_that_says_what_to_do(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("PRUDENCE_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config = config_module.Config(path=tmp_path / "config.toml")
    chosen = select_model(config)
    assert isinstance(chosen, NoModel)
    assert "ANTHROPIC_API_KEY" in chosen.reason
    with pytest.raises(ModelUnavailable):
        chosen.complete(_request())


def test_the_config_file_round_trips_the_model_block(tmp_path) -> None:
    path = tmp_path / "config.toml"
    config = config_module.Config(path=path)
    config.model = config_module.ModelSettings(
        backend="none", model_id="claude-haiku-4-5", max_tokens=512
    )
    config.review = config_module.ReviewSettings(explain=True)
    config_module.save(config)

    back = config_module.load(path)
    assert back.model.backend == "none"
    assert back.model.model_id == "claude-haiku-4-5"
    assert back.model.max_tokens == 512
    assert back.review.explain is True
    assert back.model.language == config_module.DEFAULT_LANGUAGE


def test_the_config_file_round_trips_the_language(tmp_path) -> None:
    path = tmp_path / "config.toml"
    config = config_module.Config(path=path)
    config.model = config_module.ModelSettings(language="zh-Hans")
    config_module.save(config)
    assert config_module.load(path).model.language == "zh-Hans"

    # A code nobody knows is kept as written and falls back at the call, so an unreadable
    # setting cannot stop a review being written (architecture rule 3).
    path.write_text('version = 1\n\n[model]\nlanguage = "kl"\n')
    assert config_module.load(path).model.language == "kl"
    assert language_module.resolve("kl") == "en"


# --- the language -------------------------------------------------------------------------


def test_system_reads_the_locale_at_the_moment_of_the_call() -> None:
    assert language_module.resolve("system", {"LANG": "zh_CN.UTF-8"}) == "zh-Hans"
    assert language_module.resolve("system", {"LANG": "en_GB.UTF-8"}) == "en"
    # LC_ALL wins, as POSIX says, and a `C` locale is no answer at all.
    assert language_module.resolve("system", {"LC_ALL": "zh_CN", "LANG": "en_US"}) == "zh-Hans"
    assert language_module.resolve("system", {"LC_ALL": "C", "LANG": "zh_SG"}) == "zh-Hans"
    # Nothing set, and a language no row matches, are both the engine's own language.
    assert language_module.resolve("system", {}) == "en"
    assert language_module.resolve("system", {"LANG": "fr_FR.UTF-8"}) == "en"
    # `zh_TW` is traditional Chinese: it must not fall into the simplified row.
    assert language_module.resolve("system", {"LANG": "zh_TW.UTF-8"}) == "en"


def test_a_chosen_language_beats_the_locale_and_names_itself_in_itself() -> None:
    assert language_module.resolve("en", {"LANG": "zh_CN.UTF-8"}) == "en"
    assert language_module.instruction("en") == "Write in English."
    assert language_module.instruction("zh-Hans") == "用简体中文写。"
    assert language_module.name_of("zh-Hans") == "Simplified Chinese"


def test_the_sending_line_says_which_language_the_answer_is_asked_for() -> None:
    line = Sent(numbers=3, bytes=100, language="zh-Hans").line("recorded", max_tokens=64)
    assert "answer in zh-Hans;" in line
    # A receipt for a call that named no language says nothing about one.
    assert "answer in" not in Sent(numbers=3, bytes=100).line("recorded", max_tokens=64)


# --- the Anthropic request --------------------------------------------------------------


class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Usage:
    input_tokens = 1000
    output_tokens = 200
    cache_read_input_tokens = 800
    cache_creation_input_tokens = 0


class _Response:
    model = "claude-haiku-4-5"
    stop_reason = "end_turn"
    usage = _Usage()

    def __init__(self, text: str) -> None:
        self.content = [_Block(text), type("Other", (), {"type": "thinking"})()]


class _Messages:
    def __init__(self, text: str) -> None:
        self.text = text
        self.payloads: list[dict] = []

    def create(self, **payload):
        self.payloads.append(payload)
        return _Response(self.text)


class _Client:
    def __init__(self, text: str = "twenty six numbers") -> None:
        self.messages = _Messages(text)


def test_anthropic_model_builds_the_request_the_design_asks_for() -> None:
    client = _Client()
    model = AnthropicModel(model_id="claude-haiku-4-5", client=client)
    completion = model.complete(_request())

    payload = client.messages.payloads[0]
    assert payload["model"] == "claude-haiku-4-5"
    assert payload["max_tokens"] == 64
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert payload["system"][0]["text"] == "a system prompt"
    assert payload["messages"] == [{"role": "user", "content": "the numbers"}]

    # Only the text block is the answer, and the cache read is priced separately.
    assert completion.text == "twenty six numbers"
    assert completion.cached_tokens == 800
    assert completion.cost == pytest.approx(cost("claude-haiku-4-5", 1000, 200, 800))


def test_anthropic_model_refuses_an_answer_with_no_text() -> None:
    client = _Client(text="")
    with pytest.raises(ModelFailed):
        AnthropicModel(model_id="claude-haiku-4-5", client=client).complete(_request())


def test_estimate_is_none_for_an_unpriced_model() -> None:
    assert estimate("claude-haiku-4-5", 4000, 600) is not None
    assert estimate("some-other-model", 4000, 600) is None
    assert cost("some-other-model", 10, 10) is None


# --- replaying ----------------------------------------------------------------------------


def test_recorded_model_replays_by_input_hash(tmp_path: Path) -> None:
    request = _request()
    directory = tmp_path / "fixtures"
    directory.mkdir()
    (directory / f"{input_hash(request)}.json").write_text(
        json.dumps({"text": "replayed", "model": "recorded-haiku", "output_tokens": 7})
    )
    model = RecordedModel(directory)
    completion = model.complete(request)
    assert completion.text == "replayed"
    assert completion.model == "recorded-haiku"
    assert completion.output_tokens == 7

    # A prompt that changed no longer finds its fixture, and says so.
    with pytest.raises(ModelFailed) as error:
        model.complete(_request(user="different numbers"))
    assert "re-recorded" in str(error.value)


# --- the number guard ---------------------------------------------------------------------


def test_check_numbers_accepts_what_it_was_given_in_any_presentation() -> None:
    given = ["713938k", "26", "92%", "1,204", "0.9166666"]
    assert check_numbers("713938k tokens over 26.0 sessions, 92 % alive", given) == []
    assert check_numbers("1204 lines followed", given) == []
    assert check_numbers("about 0.92 of them", given) == []


def test_check_numbers_reports_an_invented_figure() -> None:
    given = [{"key": "became.reworked", "text": "26%", "value": 0.26}]
    assert check_numbers("you rework about 40% of your lines", given) == ["40%"]
    # A unit dropped is a claim changed, so a bare 26 is not the stored 26%.
    assert check_numbers("26 of them", given) == ["26"]
    assert check_numbers("26% of them", given) == []


def test_check_numbers_ignores_dates_and_session_ids() -> None:
    given = ["3"]
    text = (
        "Between 2026-09-06 and 2026-09-20, session "
        "a1b2c3d4-e5f6-7890-abcd-ef1234567890 and commit deadbeef1234 show 3 things."
    )
    assert check_numbers(text, given) == []


def test_check_numbers_ignores_a_date_a_person_wrote() -> None:
    """A written-out date is a name for a range, not a statistic the model invented."""
    given = ["4"]
    assert check_numbers("Between September 7 and 21, 2026 you had 4 sessions.", given) == []
    assert check_numbers("From 7 Sep 2026 to 21 September 2026: 4 sessions.", given) == []
    # A year on its own is allowed; a share that was not given is still caught.
    assert check_numbers("In 2026 you reworked 91.1% of them", given) == ["91.1%"]


def test_check_numbers_reads_a_chinese_answer_in_its_own_characters() -> None:
    """A segment written in Chinese prints the same figures in different characters."""
    given = ["92%", "5000", "2"]
    # Full-width percent sign and full-width digits are presentation, not arithmetic.
    assert check_numbers("覆盖率 92％，共 2 个会话。", given) == []
    assert check_numbers("覆盖率 ９２％。", given) == []
    # A magnitude word is a multiplier: 0.5万 is the 5000 it was given.
    assert check_numbers("总共 0.5万 行。", given) == []
    assert check_numbers("总共 5千 行。", given) == []
    # And a figure the magnitude changed is still an invention.
    assert check_numbers("总共 5万 行。", given) == ["5万"]
    # Without the reading, 5万 would tokenise as a bare 5 and be missed entirely.
    assert check_numbers("总共 5万 行。", ["5"]) == ["5万"]


def test_a_magnitude_does_not_launder_a_dropped_unit() -> None:
    """`5k` and `5000` are different claims, and 0.5万 is the second one."""
    assert check_numbers("总共 0.5万 tokens", ["5k"]) == ["0.5万"]
    assert check_numbers("总共 5k tokens", ["5k"]) == []


# --- the tone guard -------------------------------------------------------------------


def test_check_tone_flags_praise_blame_and_drama() -> None:
    assert check_tone("92% coverage, which is solid") == ["solid"]
    assert check_tone("a substantial shift and clear movement") == [
        "substantial",
        "clear movement",
    ]
    assert check_tone("your rework share is concerning and your coverage is poor") == [
        "concerning",
        "poor",
    ]
    # Collapsed, and reported as written so the retry can name them back.
    assert check_tone("Solid work. Really solid.") == ["Solid"]


def test_check_tone_leaves_description_alone() -> None:
    """It is a guard, not a censor: a sentence of facts passes untouched."""
    described = (
        "You ran 4 sessions over 26.0 active hours. 18 commits are credited to them at "
        "92% mean coverage. The record does not yet show what became of those lines."
    )
    assert check_tone(described) == []
    assert check_tone("goods were committed to the badge directory") == []


def test_check_tone_grades_chinese_with_the_chinese_list() -> None:
    """A Chinese segment breaks principle 3 with Chinese words, and with English ones."""
    assert check_tone("覆盖率 92%，表现优秀。", "zh-Hans") == ["优秀"]
    assert check_tone("这一周很棒，返工率大幅下降。", "zh-Hans") == ["很棒", "大幅"]
    # The English list runs too: a Chinese paragraph still quotes the page's labels.
    assert check_tone("覆盖率 92%，which is solid。", "zh-Hans") == ["solid"]
    # And a Chinese sentence that only describes passes, as the English one does.
    assert check_tone("本周有 4 个会话，18 次提交，平均覆盖率 92%。", "zh-Hans") == []
    # Asked in English, the Chinese words are not looked for at all.
    assert check_tone("表现优秀") == []


def test_a_verdict_names_both_kinds_of_violation() -> None:
    verdict = judge("you rework 40% of your lines, which is poor", ["26%"])
    assert not verdict.ok
    assert verdict.invented == ["40%"]
    assert verdict.graded == ["poor"]
    assert "40%" in verdict.as_note()
    assert "poor" in verdict.as_note()
    instruction = correction(verdict)
    assert "Do not use 40%" in instruction
    assert "poor" in instruction


def test_the_guard_retries_once_and_then_gives_up() -> None:
    """Two calls at most, and the caller is handed the verdict rather than the text."""
    calls: list[Request] = []

    class _Stubborn:
        id = "stubborn"
        caches_system_prompt = False

        def complete(self, request: Request) -> Completion:
            calls.append(request)
            return Completion(text="you rework 40% of your lines", model=self.id)

    completion, verdict = complete_checked(_Stubborn(), _request(), ["26%"])
    assert len(calls) == 2, "one attempt, then one correction"
    assert "Do not use 40%" in calls[1].user
    assert calls[1].system == calls[0].system, "the cached half is not disturbed"
    assert not verdict.ok
    assert verdict.invented == ["40%"]
    assert completion.text  # the caller holds it and prints none of it


def test_a_corrected_draft_stops_the_loop() -> None:
    answers = iter(["you rework 40% of your lines", "you rework 26% of your lines"])

    class _Corrigible:
        id = "corrigible"
        caches_system_prompt = False

        def complete(self, request: Request) -> Completion:
            return Completion(text=next(answers), model=self.id)

    completion, verdict = complete_checked(_Corrigible(), _request(), ["26%"])
    assert verdict.ok
    assert completion.text == "you rework 26% of your lines"
