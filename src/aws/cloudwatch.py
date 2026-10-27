import time
from typing import Optional
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from src.config import settings


class CloudWatchService:
    """Registra metricas da API ArchIQ no Amazon CloudWatch."""

    def __init__(self, region_name: Optional[str] = None, namespace: str = "ArchIQ"):
        self.region_name = region_name or settings.aws_region
        self.namespace = namespace
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client("cloudwatch", region_name=self.region_name)
        return self._client

    def put_audit_metric(
        self,
        score: int,
        services_count: int,
        duration_seconds: float,
        success: bool = True,
    ) -> bool:
        try:
            metric_data = [
                {
                    "MetricName": "ArchitectureScore",
                    "Value": float(score),
                    "Unit": "Count",
                },
                {
                    "MetricName": "ServicesDetected",
                    "Value": float(services_count),
                    "Unit": "Count",
                },
                {
                    "MetricName": "AuditDuration",
                    "Value": duration_seconds,
                    "Unit": "Seconds",
                },
                {
                    "MetricName": "AuditSuccess",
                    "Value": 1.0 if success else 0.0,
                    "Unit": "Count",
                },
            ]
            self.client.put_metric_data(Namespace=self.namespace, MetricData=metric_data)
            return True
        except (BotoCoreError, ClientError):
            return False
