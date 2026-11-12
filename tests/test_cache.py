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


def test_bedrock_pauses_after_daily_quota_error(monkeypatch):
    from botocore.exceptions import ClientError
    monkeypatch.setattr(bedrock_module, "_paused_until", 0.0)
    service = bedrock_module.BedrockService()
    calls = []

    class QuotaClient:
        def converse(self, **kwargs):
            calls.append(1)
            raise ClientError({"Error": {"Code": "ThrottlingException",
                                         "Message": "Too many tokens per day"}}, "Converse")
    service._client = QuotaClient()

    with pytest.raises(ClientError):
        service.invoke("p")
    with pytest.raises(bedrock_module.BedrockBusy):  # nem chega na AWS durante a pausa
        service.invoke("p")
    assert len(calls) == 1


def test_question_answers_are_shared_through_the_result_cache():
    from src.agents.qa_agent import QuestionAgent

    class FakeBedrock:
        calls = 0
        def invoke(self, **kwargs):
            FakeBedrock.calls += 1
            return "resposta"
    cache = ResultCache(table_name="")
    code = 'resource "aws_s3_bucket" "b" {}'
    QuestionAgent(FakeBedrock(), cache).answer(code, "Esta seguro?")
    # outro processo (outra instancia) com o mesmo cache nao chama o Bedrock de novo
    assert QuestionAgent(FakeBedrock(), cache).answer(code, "esta seguro?")["answer"] == "resposta"
    assert FakeBedrock.calls == 1
