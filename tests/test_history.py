"""Historico de analises por usuario (GET/DELETE /api/history)."""

import importlib
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient

from src.aws import history as history_module
from src.aws.history import HistoryService

app_module = importlib.import_module("src.api.app")
client = TestClient(app_module.app, raise_server_exceptions=False)

CODE = '''
resource "aws_s3_bucket" "uploads" {
  bucket = "app-uploads"
  acl    = "public-read"
}
'''

current_user = {"sub": "alice"}


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(app_module.bedrock_service, "invoke", lambda *a, **k: "Explicacao simulada.")
    monkeypatch.setattr(app_module, "history_service", HistoryService(table_name=""))
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: current_user
    current_user["sub"] = "alice"
    yield
    app_module.app.dependency_overrides.clear()


def run_audit(name="infra.tf"):
    response = client.post("/api/audit", json={"code_or_prompt": CODE, "source_name": name})
    assert response.status_code == 200
    return response.json()


def test_audit_is_saved_and_listed_newest_first():
    first = run_audit("a.tf")
    second = run_audit("b.tf")
    assert first["history_id"] and second["history_id"]

    items = client.get("/api/history").json()["items"]
    assert [i["source_name"] for i in items] == ["b.tf", "a.tf"]
    assert items[0]["score"] == second["score"]
    assert "S3" in items[0]["services"]
    assert items[0]["findings"] == len(second["security_audit"]["findings"])


def test_detail_returns_full_result_and_code():
    audit = run_audit()
    detail = client.get(f"/api/history/{audit['history_id']}").json()
    assert detail["code"] == CODE
    assert detail["result"]["score"] == audit["score"]
    assert detail["result"]["client_report"]["headline"] == audit["client_report"]["headline"]
    assert detail["result"]["history_id"] == audit["history_id"]


def test_users_do_not_see_each_other():
    audit = run_audit()
    current_user["sub"] = "bob"
    assert client.get("/api/history").json()["items"] == []
    assert client.get(f"/api/history/{audit['history_id']}").status_code == 404
    assert client.delete(f"/api/history/{audit['history_id']}").status_code == 404


def test_delete_removes_entry():
    audit = run_audit()
    assert client.delete(f"/api/history/{audit['history_id']}").status_code == 204
    assert client.get("/api/history").json()["items"] == []
    assert client.get(f"/api/history/{audit['history_id']}").status_code == 404


def test_invalid_id_is_404():
    assert client.get("/api/history/..%2F..%2Fetc").status_code == 404
    assert client.get("/api/history/nao-existe").status_code == 404


def test_audit_still_works_when_history_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("dynamo fora")
    monkeypatch.setattr(app_module.history_service, "save", boom)
    audit = run_audit()
    assert audit["history_id"] is None
    assert "score" in audit


def test_history_keeps_last_entries_only(monkeypatch):
    monkeypatch.setattr(history_module, "MAX_ITEMS", 3)
    service = HistoryService(table_name="")
    for n in range(5):
        service.save("u", {"score": n}, "x", f"{n}.tf")
    assert [i["source_name"] for i in service.list("u")] == ["4.tf", "3.tf", "2.tf"]


def test_huge_code_is_dropped_but_result_kept(monkeypatch):
    monkeypatch.setattr(history_module, "MAX_BLOB_BYTES", 2000)
    service = HistoryService(table_name="")
    noise = os.urandom(4000).hex()  # nao comprime
    entry_id = service.save("u", {"score": 42}, noise)
    entry = service.get("u", entry_id)
    assert entry["code"] == ""
    assert entry["result"]["score"] == 42
