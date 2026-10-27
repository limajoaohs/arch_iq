from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- AWS região e Bedrock ---
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "amazon.nova-lite-v1:0"
    bedrock_guardrail_id: Optional[str] = None
    bedrock_guardrail_version: str = "DRAFT"

    # --- Bedrock Knowledge Bases (RAG gerenciado pela AWS) ---
    bedrock_kb_id: Optional[str] = None

    # --- Armazenamento ---
    chroma_persist_dir: str = "./chroma_data"
    s3_reports_bucket: Optional[str] = None
    dynamodb_table_name: Optional[str] = None

    # --- SNS (alertas de score baixo) ---
    sns_topic_arn: Optional[str] = None

    # --- Cognito (autenticação opcional) ---
    cognito_user_pool_id: Optional[str] = None
    cognito_client_id: Optional[str] = None

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()

