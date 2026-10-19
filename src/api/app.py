import os
import uuid
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.config import settings
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.rag.store import VectorStore
from src.agents.graph import create_arch_iq_graph

app = FastAPI(title="ArchIQ API", version="1.0.0")

vector_store = VectorStore()
bedrock_service = BedrockService()
storage_service = StorageService()

data_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "well_architected.json")
vector_store.seed_data(os.path.abspath(data_path))

graph = create_arch_iq_graph(
    vector_store=vector_store,
    bedrock_service=bedrock_service,
    storage_service=storage_service
)


class AuditRequest(BaseModel):
    code_or_prompt: str
    session_id: Optional[str] = None


class AuditResponse(BaseModel):
    session_id: str
    score: int
    parsed_services: list
    security_audit: Dict[str, Any]
    finops_audit: Dict[str, Any]
    remediated_iac: str
    final_report: str
    report_location: Optional[str] = None


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "ArchIQ",
        "region": settings.aws_region,
        "model": settings.bedrock_model_id
    }


@app.post("/api/audit", response_model=AuditResponse)
def audit_architecture(request: AuditRequest):
    if not request.code_or_prompt.strip():
        raise HTTPException(status_code=400, detail="code_or_prompt cannot be empty")

    session_id = request.session_id or str(uuid.uuid4())

    initial_state = {
        "session_id": session_id,
        "raw_input": request.code_or_prompt
    }

    try:
        final_state = graph.invoke(initial_state)
        storage_service.record_checkpoint(session_id, final_state)
        return AuditResponse(
            session_id=session_id,
            score=final_state.get("score", 0),
            parsed_services=final_state.get("parsed_services", []),
            security_audit=final_state.get("security_audit", {}),
            finops_audit=final_state.get("finops_audit", {}),
            remediated_iac=final_state.get("remediated_iac", ""),
            final_report=final_state.get("final_report", ""),
            report_location=final_state.get("report_location")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

