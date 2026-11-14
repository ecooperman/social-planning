"""Caption reading with Claude (app/ai_extraction.py) - the client is faked."""
from types import SimpleNamespace

import pytest

from app import ai_extraction
from app.ai_extraction import CaptionExtraction, ExtractedPlace


class _Client:
    def __init__(self, response):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))
        self._response = response

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def _reply(places=None, stop_reason="end_turn", parsed=True):
    output = CaptionExtraction(activities=places or []) if parsed else None
    return SimpleNamespace(stop_reason=stop_reason, parsed_output=output)


def test_blank_captions_never_reach_claude():
    # no_network replaces the client with something that fails if it is built.
    assert ai_extraction.extract_places("") == []
    assert ai_extraction.extract_places("   \n ") == []


def test_the_places_claude_found_are_returned(monkeypatch):
    found = [ExtractedPlace(name="Cafe", notes="n", city="Boston")]
    client = _Client(_reply(found))
    monkeypatch.setattr(ai_extraction, "_client", lambda: client)
    assert ai_extraction.extract_places("a caption") == found
    call = client.calls[0]
    assert call["messages"] == [{"role": "user", "content": "a caption"}]
    assert call["system"] == ai_extraction.SYSTEM_PROMPT


def test_a_refusal_or_empty_parse_counts_as_no_places(monkeypatch):
    monkeypatch.setattr(ai_extraction, "_client", lambda: _Client(_reply(stop_reason="refusal")))
    assert ai_extraction.extract_places("x") == []
    monkeypatch.setattr(ai_extraction, "_client", lambda: _Client(_reply(parsed=False)))
    assert ai_extraction.extract_places("x") == []


def test_where_the_post_was_filed_goes_in_the_user_message(monkeypatch):
    client = _Client(_reply())
    monkeypatch.setattr(ai_extraction, "_client", lambda: client)
    ai_extraction.extract_places("a caption", "Salem, MA (Salem, Massachusetts, United States)")
    content = client.calls[0]["messages"][0]["content"]
    assert content == "Filed under: Salem, MA (Salem, Massachusetts, United States)\n\nCaption:\na caption"


def test_no_api_key_is_a_clear_error(monkeypatch):
    monkeypatch.undo()  # drop the autouse fakes so the real _client runs
    monkeypatch.setattr(ai_extraction, "ANTHROPIC_API_KEY", None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        ai_extraction._client()
