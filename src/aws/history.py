"""Historico de auditorias por usuario.

Usa a mesma tabela DynamoDB dos checkpoints (chave SessionId + Timestamp):
  SessionId = "HISTORY#<sub do Cognito>"   (todas as analises de um usuario)
  Timestamp = "<AAAAMMDDTHHMMSSZ>_<id>"   (ordena da mais nova para a mais antiga)
O resultado completo vai comprimido (gzip) no atributo binario "Result" para caber
no limite de 400 KB por item. Sem tabela configurada, guarda em memoria (dev e testes).
"""

import gzip
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.config import settings

MAX_ITEMS = 50
MAX_BLOB_BYTES = 350 * 1024  # folga abaixo do limite de 400 KB do DynamoDB
ANONYMOUS = "local"  # usuario quando o login (Cognito) esta desativado
_ID_RE = re.compile(r"^\d{8}T\d{6}Z_[0-9a-f]{12}$")

SUMMARY_FIELDS = ("id", "created_at", "score", "score_status", "services",
                  "findings", "optimizations", "source_name", "headline")


def valid_id(entry_id: str) -> bool:
    return bool(_ID_RE.match(entry_id or ""))


def build_summary(entry_id: str, created_at: str, result: Dict[str, Any], source_name: str) -> Dict[str, Any]:
    summary = result.get("executive_summary") or {}
    return {
        "id": entry_id,
        "created_at": created_at,
        "score": int(result.get("score", 0)),
        "score_status": summary.get("score_status", ""),
        "services": [s for s in result.get("parsed_services", []) if s != "GENERAL_AWS"],
        "findings": len((result.get("security_audit") or {}).get("findings", [])),
        "optimizations": sum(1 for o in (result.get("finops_audit") or {}).get("optimizations", [])
                             if o.get("status") != "in_use"),
        "source_name": source_name or "main.tf",
        "headline": (result.get("client_report") or {}).get("headline", ""),
    }


def _pack(result: Dict[str, Any], code: str) -> Optional[bytes]:
    blob = gzip.compress(json.dumps({"result": result, "code": code}).encode("utf-8"))
    if len(blob) > MAX_BLOB_BYTES:
        # Terraform enorme: guarda so o resultado (o agente de perguntas fica sem o codigo)
        blob = gzip.compress(json.dumps({"result": result, "code": ""}).encode("utf-8"))
    return blob if len(blob) <= MAX_BLOB_BYTES else None


def _unpack(blob: bytes) -> Dict[str, Any]:
    return json.loads(gzip.decompress(blob).decode("utf-8"))


class HistoryService:
    def __init__(self, table_name: Optional[str] = None, region_name: Optional[str] = None):
        self.table_name = table_name if table_name is not None else settings.dynamodb_table_name
        self.region_name = region_name or settings.aws_region
        self._client = None
        self._memory: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()

    @property
    def dynamo(self):
        if self._client is None:
            self._client = boto3.client("dynamodb", region_name=self.region_name)
        return self._client

    @staticmethod
    def _pk(user_id: str) -> str:
        return f"HISTORY#{user_id or ANONYMOUS}"

    def save(self, user_id: str, result: Dict[str, Any], code: str, source_name: str = "") -> Optional[str]:
        """Guarda a analise e devolve o id, ou None se nao foi possivel guardar."""
        now = datetime.now(timezone.utc)
        entry_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:12]}"
        summary = build_summary(entry_id, now.isoformat(timespec="seconds"), result, source_name)
        blob = _pack(result, code)
        if blob is None:
            return None

        if not self.table_name:
            with self._lock:
                items = self._memory.setdefault(self._pk(user_id), [])
                items.insert(0, {"summary": summary, "blob": blob})
                del items[MAX_ITEMS:]
            return entry_id

        try:
            self.dynamo.put_item(TableName=self.table_name, Item={
                "SessionId": {"S": self._pk(user_id)},
                "Timestamp": {"S": entry_id},
                "Summary": {"S": json.dumps(summary)},
                "Result": {"B": blob},
            })
            return entry_id
        except (BotoCoreError, ClientError):
            return None

    def list(self, user_id: str, limit: int = MAX_ITEMS) -> List[Dict[str, Any]]:
        if not self.table_name:
            with self._lock:
                return [dict(i["summary"]) for i in self._memory.get(self._pk(user_id), [])[:limit]]

        # Le so o resumo: o resultado completo vem sob demanda em get()
        response = self.dynamo.query(
            TableName=self.table_name,
            KeyConditionExpression="SessionId = :pk",
            ExpressionAttributeValues={":pk": {"S": self._pk(user_id)}},
            ProjectionExpression="Summary",
            ScanIndexForward=False,
            Limit=limit,
        )
        return [json.loads(item["Summary"]["S"]) for item in response.get("Items", []) if "Summary" in item]

    def get(self, user_id: str, entry_id: str) -> Optional[Dict[str, Any]]:
        if not valid_id(entry_id):
            return None
        if not self.table_name:
            with self._lock:
                for item in self._memory.get(self._pk(user_id), []):
                    if item["summary"]["id"] == entry_id:
                        return {"summary": dict(item["summary"]), **_unpack(item["blob"])}
            return None

        response = self.dynamo.get_item(TableName=self.table_name, Key={
            "SessionId": {"S": self._pk(user_id)}, "Timestamp": {"S": entry_id}})
        item = response.get("Item")
        if not item or "Result" not in item:
            return None
        return {"summary": json.loads(item["Summary"]["S"]), **_unpack(item["Result"]["B"])}

    def delete(self, user_id: str, entry_id: str) -> bool:
        if not valid_id(entry_id):
            return False
        if not self.table_name:
            with self._lock:
                items = self._memory.get(self._pk(user_id), [])
                kept = [i for i in items if i["summary"]["id"] != entry_id]
                self._memory[self._pk(user_id)] = kept
                return len(kept) != len(items)

        response = self.dynamo.delete_item(
            TableName=self.table_name,
            Key={"SessionId": {"S": self._pk(user_id)}, "Timestamp": {"S": entry_id}},
            ReturnValues="ALL_OLD",
        )
        return "Attributes" in response
