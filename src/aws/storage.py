import json
import uuid
from typing import Optional, Dict, Any
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from src.config import settings


class StorageService:
    def __init__(self, region_name: Optional[str] = None):
        self.region_name = region_name or settings.aws_region
        self.bucket_name = settings.s3_reports_bucket
        self.table_name = settings.dynamodb_table_name
        self._s3_client = None
        self._dynamo_client = None

    @property
    def s3(self):
        if self._s3_client is None:
            self._s3_client = boto3.client("s3", region_name=self.region_name)
        return self._s3_client

    @property
    def dynamo(self):
        if self._dynamo_client is None:
            self._dynamo_client = boto3.client("dynamodb", region_name=self.region_name)
        return self._dynamo_client

    def save_report(self, report_content: str, report_id: Optional[str] = None) -> str:
        report_key = report_id or f"reports/archi-iq-audit-{uuid.uuid4().hex[:8]}.md"
        if not self.bucket_name:
            return report_key

        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=report_key,
                Body=report_content.encode("utf-8"),
                ContentType="text/markdown"
            )
            return f"s3://{self.bucket_name}/{report_key}"
        except (BotoCoreError, ClientError):
            return report_key

    def record_checkpoint(self, session_id: str, state_payload: Dict[str, Any]) -> bool:
        if not self.table_name:
            return True

        try:
            self.dynamo.put_item(
                TableName=self.table_name,
                Item={
                    "SessionId": {"S": session_id},
                    "Timestamp": {"S": str(uuid.uuid1().time)},
                    "State": {"S": json.dumps(state_payload)}
                }
            )
            return True
        except (BotoCoreError, ClientError):
            return False

