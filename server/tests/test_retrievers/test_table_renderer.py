import json
import os
import sys

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from retrievers.implementations.intent.domain.response.table_renderer import TableRenderer
from retrievers.implementations.intent.domain.response import table_renderer as table_renderer_module


class FakeObjectId:
    def __init__(self, value: str):
        self.value = value

    def __str__(self) -> str:
        return self.value


def test_render_toon_handles_non_json_types_without_fallback(monkeypatch):
    monkeypatch.setattr(table_renderer_module, "toon_dumps", json.dumps)

    columns = ["_id", "payload", "tags"]
    rows = [[FakeObjectId("abc123"), {"nested_id": FakeObjectId("def456")}, {"a", "b"}]]

    rendered = TableRenderer.render(columns, rows, format="toon")
    parsed = json.loads(rendered)

    assert parsed[0]["_id"] == "abc123"
    assert parsed[0]["payload"]["nested_id"] == "def456"
    assert sorted(parsed[0]["tags"]) == ["a", "b"]


def test_render_toon_falls_back_when_encoder_still_fails(monkeypatch):
    def _fail(_data):
        raise TypeError("forced failure")

    monkeypatch.setattr(table_renderer_module, "toon_dumps", _fail)

    columns = ["name", "value"]
    rows = [["alpha", 1]]

    rendered = TableRenderer.render(columns, rows, format="toon")

    assert rendered == "name | value\n------------\nalpha | 1\n"
