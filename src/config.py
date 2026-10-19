from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    bedrock_guardrail_id: Optional[str] = None
    bedrock_guardrail_version: str = "DRAFT"
    chroma_persist_dir: str = "./chroma_data"
    s3_reports_bucket: Optional[str] = None
    dynamodb_table_name: Optional[str] = None
    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()

