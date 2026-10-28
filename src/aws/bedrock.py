from typing import Optional, Dict, Any
import boto3
from src.config import settings


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
            self._client = boto3.client("bedrock-runtime", region_name=self.region_name)
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
        response = self.client.converse(**converse_kwargs)
        return response["output"]["message"]["content"][0]["text"]
