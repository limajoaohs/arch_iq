from typing import Optional, List, Dict, Any
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from src.config import settings


class TextractService:
    """Extrai texto e estrutura de imagens/PDFs (diagramas de arquitetura) usando Amazon Textract."""

    def __init__(self, region_name: Optional[str] = None):
        self.region_name = region_name or settings.aws_region
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client("textract", region_name=self.region_name)
        return self._client

    def extract_text_from_bytes(self, document_bytes: bytes) -> str:
        """Extrai texto de uma imagem ou PDF em memoria."""
        try:
            response = self.client.detect_document_text(
                Document={"Bytes": document_bytes}
            )
            linhas: List[str] = []
            for bloco in response.get("Blocks", []):
                if bloco["BlockType"] == "LINE":
                    linhas.append(bloco.get("Text", ""))
            return "\n".join(linhas)
        except (BotoCoreError, ClientError):
            return ""

    def extract_text_from_s3(self, bucket: str, key: str) -> str:
        """Extrai texto de um documento armazenado no S3."""
        try:
            response = self.client.detect_document_text(
                Document={"S3Object": {"Bucket": bucket, "Name": key}}
            )
            linhas: List[str] = []
            for bloco in response.get("Blocks", []):
                if bloco["BlockType"] == "LINE":
                    linhas.append(bloco.get("Text", ""))
            return "\n".join(linhas)
        except (BotoCoreError, ClientError):
            return ""
