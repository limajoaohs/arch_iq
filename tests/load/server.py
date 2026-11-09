"""API do ArchIQ para teste de carga, sem nenhum acesso real a AWS.

As variaveis abaixo precisam vir antes de importar `src`, porque sobrescrevem o .env.
Os servicos AWS viram simulacoes com latencia configuravel, e o endpoint aponta para
uma porta fechada: qualquer chamada que escape falha localmente, sem gastar cota nem
enviar alertas.

    python tests/load/server.py --port 8099 --bedrock-latency 2 --aws-latency 0.03
"""
import argparse
import os
import sys
import threading
import time

os.environ.update({
    "AWS_ACCESS_KEY_ID": "load-test",
    "AWS_SECRET_ACCESS_KEY": "load-test",
    "AWS_ENDPOINT_URL": "http://127.0.0.1:9",
    "AWS_MAX_ATTEMPTS": "1",
    "BEDROCK_KB_ID": "",
    "S3_REPORTS_BUCKET": "",
    "DYNAMODB_TABLE_NAME": "",
    "SNS_TOPIC_ARN": "",
    "COGNITO_USER_POOL_ID": "",
    "COGNITO_CLIENT_ID": "",
    "CHROMA_PERSIST_DIR": os.environ.get("CHROMA_PERSIST_DIR", "./chroma_data_load"),
})
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Producao (requirements_minimal.txt) nao tem LangGraph nem ChromaDB e roda o FallbackWorkflow.
# Esconde os dois mesmo que o venv local os tenha: com ChromaDB cada auditoria calcula
# embeddings na CPU e o teste mede uma arquitetura que nao e a de producao.
for _module in ("langgraph", "langgraph.graph", "chromadb", "chromadb.config"):
    sys.modules[_module] = None

import uvicorn  # noqa: E402

from src.api.app import app  # noqa: E402
from src.aws.bedrock import BedrockService  # noqa: E402
from src.aws.cloudwatch import CloudWatchService  # noqa: E402
from src.aws.storage import StorageService  # noqa: E402
from src.aws.history import HistoryService  # noqa: E402

counts = {"bedrock": 0, "s3": 0, "dynamodb": 0, "cloudwatch": 0, "in_flight_bedrock_peak": 0}
_lock = threading.Lock()
_in_flight = 0


def install_fakes(bedrock_latency: float, aws_latency: float) -> None:
    def fake_invoke(self, *args, **kwargs):
        global _in_flight
        with _lock:
            counts["bedrock"] += 1
            _in_flight += 1
            counts["in_flight_bedrock_peak"] = max(counts["in_flight_bedrock_peak"], _in_flight)
        time.sleep(bedrock_latency)
        with _lock:
            _in_flight -= 1
        return "Explicacao simulada para teste de carga."

    def fake_aws(name, result):
        def call(self, *args, **kwargs):
            with _lock:
                counts[name] += 1
            time.sleep(aws_latency)
            return result
        return call

    BedrockService.invoke = fake_invoke
    StorageService.save_report = fake_aws("s3", "reports/load-test.md")
    StorageService.record_checkpoint = fake_aws("dynamodb", True)
    HistoryService.save = fake_aws("dynamodb", "20260101T000000Z_000000000000")
    CloudWatchService.put_audit_metric = fake_aws("cloudwatch", True)


def load_counts():
    return counts


# Na frente da lista: o StaticFiles montado em "/" capturaria a rota se ela viesse depois
app.add_api_route("/__load/counts", load_counts, include_in_schema=False)
app.router.routes.insert(0, app.router.routes.pop())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--bedrock-latency", type=float, default=2.0)
    parser.add_argument("--aws-latency", type=float, default=0.03)
    options = parser.parse_args()

    install_fakes(options.bedrock_latency, options.aws_latency)
    # Mesmo modo do Dockerfile: um unico processo uvicorn
    uvicorn.run(app, host="127.0.0.1", port=options.port, log_level="warning")
