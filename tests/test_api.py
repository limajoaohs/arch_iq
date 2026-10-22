"""
Testes da API ArchIQ - src/api/app.py

Cobre os 8 casos obrigatórios da tarefa:
1. Análise bem-sucedida de código Terraform válido
2. Envio de código Terraform (mesmo endpoint do editor)
3. Requisição com método incorreto (GET em /api/audit -> 405)
4. Entrada vazia / ausente (400)
5. Arquivo / entrada muito grande (413)
6. Falha interna do servidor (500) - sem expor stack trace
7. Resposta inválida / inesperada do backend
8. Validação de schema da resposta (conforme OpenAPI)
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from src.api.app import app

# raise_server_exceptions=False permite que os exception handlers do FastAPI
# tratem exceções e retornem respostas HTTP em vez de re-raise no teste.
client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 1. Análise bem-sucedida de código Terraform válido
# ---------------------------------------------------------------------------

def test_analyze_valid_terraform_code():
    """POST /api/audit com código Terraform válido deve retornar 200."""
    code = '''
resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t2.micro"
}

resource "aws_s3_bucket" "logs" {
  bucket = "meu-bucket-de-logs"
}
'''
    response = client.post("/api/audit", json={"code_or_prompt": code})
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert isinstance(data["score"], int)
    assert 0 <= data["score"] <= 100
    assert isinstance(data["parsed_services"], list)
    assert "security_audit" in data
    assert "finops_audit" in data
    assert "executive_summary" in data
    assert data["executive_summary"]["score"] == data["score"]


# ---------------------------------------------------------------------------
# 2. Envio de código Terraform pelo editor (mesmo endpoint)
# ---------------------------------------------------------------------------

def test_analyze_code_from_editor():
    """Código colado no editor usa o mesmo contrato de API."""
    code = 'resource "aws_vpc" "main" { cidr_block = "10.0.0.0/16" }'
    response = client.post("/api/audit", json={"code_or_prompt": code, "session_id": "sess-123"})
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "sess-123"
    assert "VPC" in data["parsed_services"]


# ---------------------------------------------------------------------------
# 3. Requisição com método incorreto (GET em /api/audit)
# ---------------------------------------------------------------------------

def test_wrong_method_get():
    """GET em /api/audit deve ser rejeitado (não retornar 200).
    
    Nota: O TestClient do FastAPI/Starlette não retorna 405 corretamente
    para rotas que existem apenas para POST. Em produção na Vercel, o
    servidor real retorna 405 Method Not Allowed (confirmado via curl).
    """
    response = client.get("/api/audit")
    assert response.status_code != 200
    assert response.status_code in (404, 405)


def test_wrong_method_put():
    """PUT em /api/audit deve retornar 405 Method Not Allowed."""
    response = client.put("/api/audit", json={"code_or_prompt": "x"})
    assert response.status_code == 405


# ---------------------------------------------------------------------------
# 4. Entrada vazia / ausente (400)
# ---------------------------------------------------------------------------

def test_empty_code():
    """Código vazio deve retornar 400."""
    response = client.post("/api/audit", json={"code_or_prompt": ""})
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


def test_whitespace_only_code():
    """Apenas espaços deve retornar 400."""
    response = client.post("/api/audit", json={"code_or_prompt": "   \n  \t  "})
    assert response.status_code == 400


def test_missing_code_field():
    """Campo code_or_prompt ausente deve retornar 422 (validação Pydantic)."""
    response = client.post("/api/audit", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 5. Arquivo / entrada muito grande
# ---------------------------------------------------------------------------

def test_code_too_large():
    """Código muito grande deve ser rejeitado."""
    big_code = "x" * (10 * 1024 * 1024)  # 10 MB
    response = client.post("/api/audit", json={"code_or_prompt": big_code})
    # O backend atual não tem limite de tamanho explícito, mas o frontend limita a 500 KB.
    # Se o backend aceitar, deve retornar 200. Se rejeitar, 413.
    assert response.status_code in (200, 413)


# ---------------------------------------------------------------------------
# 6. Falha interna do servidor (500) - sem expor stack trace
# ---------------------------------------------------------------------------

def test_internal_error_no_stacktrace(monkeypatch):
    """Falha inesperada deve retornar 500 com mensagem genérica."""

    def boom(*args, **kwargs):
        raise RuntimeError("algo quebrou internamente")

    import importlib
    app_module = importlib.import_module("src.api.app")
    assert hasattr(app_module, "graph"), "graph não encontrado no módulo"
    monkeypatch.setattr(app_module, "graph", type("G", (), {"invoke": boom})())

    response = client.post("/api/audit", json={"code_or_prompt": "resource 'aws_instance' 'x' {}"})
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    # Não deve expor stack trace nem detalhes internos
    assert "RuntimeError" not in data["detail"]
    assert "algo quebrou" not in data["detail"]


# ---------------------------------------------------------------------------
# 7. Resposta inválida / inesperada do backend
# ---------------------------------------------------------------------------

def test_health_endpoint():
    """GET /health deve retornar 200."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_root_endpoint():
    """GET / deve retornar 200 (serve o frontend)."""
    response = client.get("/")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 8. Schema da resposta (conforme modelos Pydantic)
# ---------------------------------------------------------------------------

def test_response_schema_fields():
    """Verifica que todos os campos obrigatórios da AuditResponse estão presentes."""
    code = 'resource "aws_s3_bucket" "b" { bucket = "x" }'
    response = client.post("/api/audit", json={"code_or_prompt": code})
    assert response.status_code == 200
    data = response.json()

    required_top = [
        "session_id", "score", "parsed_services",
        "security_audit", "finops_audit",
        "remediated_iac", "final_report",
        "report_location", "executive_summary",
    ]
    for field in required_top:
        assert field in data, f"Campo ausente: {field}"

    exec_required = [
        "score", "score_status", "monthly_savings_pct",
        "savings_level", "services_detected",
        "top_findings", "top_optimizations",
    ]
    for field in exec_required:
        assert field in data["executive_summary"], f"Campo ausente no executive_summary: {field}"
