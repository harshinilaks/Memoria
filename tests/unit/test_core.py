import json
import logging

from memoria.api.dependencies import get_namespace
from memoria.core.config import settings
from memoria.core.logging import JsonFormatter


def test_namespace_comes_from_configured_identity(monkeypatch) -> None:
    monkeypatch.setattr(settings, "dev_namespace", "configured-ns")
    assert get_namespace() == "configured-ns"


def test_json_formatter_includes_extra_fields() -> None:
    record = logging.makeLogRecord(
        {"name": "memoria.test", "levelname": "INFO", "msg": "memory created", "memory_id": "abc"}
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "memory created"
    assert payload["level"] == "INFO"
    assert payload["memory_id"] == "abc"
    assert "timestamp" in payload
