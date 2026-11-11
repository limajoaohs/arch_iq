import os
import threading
from typing import Optional, Dict, Any
import boto3
from botocore.config import Config
from src.config import settings

# Fila de graca, dentro do processo: no maximo N chamadas ao Bedrock ao mesmo tempo. Num pico,
# as demais esperam a vez em vez de estourar a cota; quem espera demais recebe o texto de reserva.
BEDROCK_MAX_CONCURRENT = int(os.environ.get("BEDROCK_MAX_CONCURRENT", "4"))
BEDROCK_QUEUE_TIMEOUT = float(os.environ.get("BEDROCK_QUEUE_TIMEOUT", "25"))
_slots = threading.BoundedSemaphore(BEDROCK_MAX_CONCURRENT)


class BedrockBusy(RuntimeError):
    """Todas as vagas de chamada ao Bedrock ocupadas alem do tempo de espera."""


class BedrockService:
    def __init__(self, region_name: Optional[str] = None, model_id: Optional[str] = None):
        self.region_name = region_name or settings.aws_region
        self.model_id = model_id or settings.bedrock_model_id
        self.guardrail_id = settings.bedrock_guardrail_id
        self.guardrail_version = settings.bedrock_guardrail_version
        self._client = None

    @property
    def client(self):
        if self._client is None:
            # "adaptive": em throttling, o boto3 espera e tenta de novo no ritmo que a AWS aceita
            self._client = boto3.client("bedrock-runtime", region_name=self.region_name,
                                        config=Config(retries={"mode": "adaptive", "max_attempts": 4}))
        return self._client

    def invoke(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2048, temperature: float = 0.2) -> str:
        converse_kwargs: Dict[str, Any] = {
            "modelId": self.model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature
            }
        }

        if system_prompt:
            converse_kwargs["system"] = [{"text": system_prompt}]

        if self.guardrail_id:
            converse_kwargs["guardrailConfig"] = {
                "guardrailIdentifier": self.guardrail_id,
                "guardrailVersion": self.guardrail_version
            }

        # Erros da AWS (throttling, credenciais, modelo) sobem para o chamador decidir o fallback
        if not _slots.acquire(timeout=BEDROCK_QUEUE_TIMEOUT):
            raise BedrockBusy("Bedrock ocupado: fila cheia")
        try:
            response = self.client.converse(**converse_kwargs)
        finally:
            _slots.release()
        return response["output"]["message"]["content"][0]["text"]
