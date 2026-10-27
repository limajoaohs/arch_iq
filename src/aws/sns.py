import json
from typing import Optional, Dict, Any
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from src.config import settings


class SnsService:
    """Envia alertas por SNS (e-mail, SMS, etc.) quando a arquitetura precisa de atencao."""

    def __init__(self, region_name: Optional[str] = None, topic_arn: Optional[str] = None):
        self.region_name = region_name or settings.aws_region
        self.topic_arn = topic_arn or settings.sns_topic_arn
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client("sns", region_name=self.region_name)
        return self._client

    def is_enabled(self) -> bool:
        return bool(self.topic_arn)

    def publish_low_score_alert(
        self,
        session_id: str,
        score: int,
        services: list[str],
        top_findings: list[Dict[str, Any]],
    ) -> bool:
        if not self.is_enabled():
            return False

        findings_resumo = "; ".join(
            f"{f.get('service', 'N/A')}: {f.get('rule', 'N/A')}" for f in top_findings[:3]
        ) or "nenhum detalhe"

        mensagem = (
            f"ArchIQ - Atencao: arquitetura com score baixo\n\n"
            f"Sessao: {session_id}\n"
            f"Score: {score} / 100\n"
            f"Servicos: {', '.join(services) if services else 'Nenhum'}\n"
            f"Principais problemas: {findings_resumo}\n\n"
            "Revise o relatorio completo no ArchIQ e aplique as melhorias sugeridas."
        )

        try:
            self.client.publish(
                TopicArn=self.topic_arn,
                Subject=f"[ArchIQ] Score baixo detectado: {score}/100",
                Message=mensagem,
            )
            return True
        except (BotoCoreError, ClientError):
            return False
