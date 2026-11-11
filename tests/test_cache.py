"""Cache de auditorias e limite de chamadas simultaneas ao Bedrock."""
import threading
import time

import pytest

from src.aws import bedrock as bedrock_module
from src.aws.cache import ResultCache, cache_key


def test_cache_key_ignores_surrounding_whitespace():
    assert cache_key("  a = 1\n") == cache_key("a = 1")


def test_memory_cache_round_trip_and_expiry():
    cache = ResultCache(table_name="", ttl_seconds=60)
    assert cache.get("x") is None
    cache.put("x", {"score": 80})
    assert cache.get("x") == {"score": 80}
    expired = ResultCache(table_name="", ttl_seconds=-1)
    expired.put("x", {"score": 80})
    assert expired.get("x") is None


def test_bedrock_waits_for_a_free_slot_then_gives_up(monkeypatch):
    monkeypatch.setattr(bedrock_module, "_slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(bedrock_module, "BEDROCK_QUEUE_TIMEOUT", 0.2)
    service = bedrock_module.BedrockService()

    class SlowClient:
        def converse(self, **kwargs):
            time.sleep(0.6)
            return {"output": {"message": {"content": [{"text": "ok"}]}}}
    service._client = SlowClient()

    first = threading.Thread(target=service.invoke, args=("p",))
    first.start()
    time.sleep(0.05)
    with pytest.raises(bedrock_module.BedrockBusy):
        service.invoke("p")
    first.join()
    assert service.invoke("p") == "ok"  # a vaga volta depois da chamada
