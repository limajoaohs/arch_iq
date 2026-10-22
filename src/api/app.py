import os
import uuid
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import settings
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.rag.store import VectorStore
from src.agents.graph import create_arch_iq_graph


app = FastAPI(title="ArchIQ API", version="1.0.0")

# Rota raiz - servir o index.html da interface web
@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse("web/index.html")

# Servir arquivos estáticos da pasta web (na raiz)
app.mount("/", StaticFiles(directory="web", html=True), name="web")

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


class SecurityFinding(BaseModel):
    severity: str
    service: str
    rule: str
    remediation: str


class FinopsOptimization(BaseModel):
    service: str
    action: str
    impact: str


class ExecutiveSummary(BaseModel):
    score: int
    score_status: str
    monthly_savings_pct: int
    savings_level: str
    services_detected: List[str]
    top_findings: List[SecurityFinding]
    top_optimizations: List[FinopsOptimization]


class AuditResponse(BaseModel):
    session_id: str
    score: int
    parsed_services: List[str]
    security_audit: Dict[str, Any]
    finops_audit: Dict[str, Any]
    remediated_iac: str
    final_report: str
    report_location: Optional[str] = None
    executive_summary: ExecutiveSummary


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

        # Build executive summary for humanized response
        score = final_state.get("score", 0)
        fin_audit = final_state.get("finops_audit", {})
        sec_audit = final_state.get("security_audit", {})

        # Determine score status
        if score >= 90:
            score_status = "EXCELENTE"
        elif score >= 75:
            score_status = "BOA"
        elif score >= 50:
            score_status = "REGULAR"
        else:
            score_status = "ATENCAO"

        # Determine savings level
        savings = fin_audit.get("monthly_savings_pct", 0)
        if savings >= 30:
            savings_level = "OTIMO"
        elif savings >= 15:
            savings_level = "BOM"
        elif savings >= 5:
            savings_level = "MODERADO"
        else:
            savings_level = "BAIXO"

        # Top findings (first 3)
        top_findings = []
        for f in sec_audit.get("findings", [])[:3]:
            top_findings.append(SecurityFinding(
                severity=f.get("severity", "INFO"),
                service=f.get("service", ""),
                rule=f.get("rule", ""),
                remediation=f.get("remediation", "")
            ))

        # Top optimizations (first 3)
        top_optimizations = []
        for o in fin_audit.get("optimizations", [])[:3]:
            top_optimizations.append(FinopsOptimization(
                service=o.get("service", ""),
                action=o.get("action", ""),
                impact=o.get("impact", "")
            ))

        executive_summary = ExecutiveSummary(
            score=score,
            score_status=score_status,
            monthly_savings_pct=savings,
            savings_level=savings_level,
            services_detected=final_state.get("parsed_services", []),
            top_findings=top_findings,
            top_optimizations=top_optimizations
        )

        return AuditResponse(
            session_id=session_id,
            score=score,
            parsed_services=final_state.get("parsed_services", []),
            security_audit=sec_audit,
            finops_audit=fin_audit,
            remediated_iac=final_state.get("remediated_iac", ""),
            final_report=final_state.get("final_report", ""),
            report_location=final_state.get("report_location"),
            executive_summary=executive_summary
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

