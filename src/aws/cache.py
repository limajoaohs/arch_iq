"""Cache das auditorias: o mesmo Terraform devolve o mesmo resultado sem chamar o Bedrock.

A nota e os riscos vem de regras deterministicas, entao repetir a analise de um codigo
identico so gasta cota. Dois niveis, sem recurso novo na AWS:
  1. memoria do processo (LRU), para repeticoes seguidas;
  2. a tabela DynamoDB dos checkpoints e do historico (chave SessionId + Timestamp):
     SessionId = "CACHE#<sha256 do codigo>", Timestamp = RULES_VERSION,
     resultado comprimido em "Result" e validade em "ExpiresAt" (epoch, para o TTL).
Erros do cache nunca derrubam a auditoria: no pior caso ela roda normalmente.
"""

import gzip
import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.config import settings

# Mude quando as regras do analisador ou os textos mudarem: invalida o cache inteiro.
RULES_VERSION = "2026-11-11"
TTL_SECONDS = 7 * 24 * 3600
MEMORY_ITEMS = 256
MAX_BLOB_BYTES = 350 * 1024  # folga abaixo do limite de 400 KB por item do DynamoDB


def cache_key(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


class ResultCache:
    def __init__(self, table_name: Optional[str] = None, region_name: Optional[str] = None,
                 ttl_seconds: int = TTL_SECONDS):
        self.table_name = table_name if table_name is not None else settings.dynamodb_table_name
        self.region_name = region_name or settings.aws_region
        self.ttl_seconds = ttl_seconds
        self._client = None
        self._memory: "OrderedDict[str, tuple]" = OrderedDict()
        self._lock = threading.Lock()

    @property
    def dynamo(self):
        if self._client is None:
            self._client = boto3.client("dynamodb", region_name=self.region_name)
        return self._client

    def get(self, code: str) -> Optional[Dict[str, Any]]:
        key = cache_key(code)
        now = time.time()
        with self._lock:
            hit = self._memory.get(key)
            if hit and hit[0] > now:
                self._memory.move_to_end(key)
                return json.loads(hit[1])
        if not self.table_name:
            return None
        try:
            item = self.dynamo.get_item(TableName=self.table_name, Key={
                "SessionId": {"S": f"CACHE#{key}"}, "Timestamp": {"S": RULES_VERSION}}).get("Item")
        except (BotoCoreError, ClientError):
            return None
        # o TTL do DynamoDB apaga com atraso: a validade e conferida aqui tambem
        if not item or "Result" not in item or float(item.get("ExpiresAt", {}).get("N", 0)) <= now:
            return None
        raw = gzip.decompress(item["Result"]["B"]).decode("utf-8")
        self._remember(key, raw, float(item["ExpiresAt"]["N"]))
        return json.loads(raw)

    def put(self, code: str, result: Dict[str, Any]) -> None:
        key = cache_key(code)
        raw = json.dumps(result)
        expires = time.time() + self.ttl_seconds
        self._remember(key, raw, expires)
        if not self.table_name:
            return
        blob = gzip.compress(raw.encode("utf-8"))
        if len(blob) > MAX_BLOB_BYTES:
            return
        try:
            self.dynamo.put_item(TableName=self.table_name, Item={
                "SessionId": {"S": f"CACHE#{key}"},
                "Timestamp": {"S": RULES_VERSION},
                "Result": {"B": blob},
                "ExpiresAt": {"N": str(int(expires))},
            })
        except (BotoCoreError, ClientError):
            pass

    def _remember(self, key: str, raw: str, expires: float) -> None:
        with self._lock:
            self._memory[key] = (expires, raw)
            self._memory.move_to_end(key)
            while len(self._memory) > MEMORY_ITEMS:
                self._memory.popitem(last=False)
