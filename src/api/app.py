import os
import uuid
import base64
from typing import Optional, Dict, Any, List
import jwt
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import settings
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.aws.sns import SnsService
from src.aws.cloudwatch import CloudWatchService
from src.aws.textract import TextractService
from src.rag.store import VectorStore
from src.agents.graph import create_arch_iq_graph


app = FastAPI(title="ArchIQ API", version="1.0.0")

# CORS - liberar frontend (ajuste via variavel de ambiente CORS_ORIGINS)
cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Autenticacao opcional com Amazon Cognito (se configurado via variaveis de ambiente)
_jwks_client: Optional[jwt.PyJWKClient] = None


def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """Valida o access token JWT do Cognito. Retorna None se nao houver Cognito configurado."""
    global _jwks_client
    if not settings.cognito_user_pool_id or not settings.cognito_client_id:
        return None  # Autenticacao desativada

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token de autenticacao necessario.")

    token = authorization.split(" ", 1)[1]
    issuer = f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.cognito_user_pool_id}"
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(f"{issuer}/.well-known/jwks.json")  # cacheia as chaves publicas

    try:
        key = _jwks_client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=issuer,
                            options={"require": ["exp", "iss", "sub", "token_use", "client_id"]})
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token invalido ou expirado.")

    # Access token do Cognito nao tem "aud": o app client vem em "client_id"
    if claims["token_use"] != "access" or claims["client_id"] != settings.cognito_client_id:
        raise HTTPException(status_code=401, detail="Token invalido ou expirado.")

    return claims


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
    technical_report: str
    layperson_explanation: str
    report_location: Optional[str] = None
    alert_sent: bool = False
    executive_summary: ExecutiveSummary


class TextractResponse(BaseModel):
    extracted_text: str


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "ArchIQ",
        "region": settings.aws_region,
        "model": settings.bedrock_model_id
    }


@app.post("/api/audit", response_model=AuditResponse)
def audit_architecture(request: AuditRequest, user: Optional[Dict[str, Any]] = Depends(get_current_user)):
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
            technical_report=final_state.get("technical_report", ""),
            layperson_explanation=final_state.get("layperson_explanation", ""),
            report_location=final_state.get("report_location"),
            alert_sent=final_state.get("alert_sent", False),
            executive_summary=executive_summary
        )
    except Exception as e:
        # Não expor stack traces nem detalhes internos ao cliente
        raise HTTPException(status_code=500, detail="Erro interno do servidor ao processar a solicitação.")


@app.post("/api/extract-text", response_model=TextractResponse)
async def extract_text(file: UploadFile = File(...), user: Optional[Dict[str, Any]] = Depends(get_current_user)):
    """Extrai texto de uma imagem ou PDF (diagrama de arquitetura) usando Amazon Textract."""
    if not textract_service or not textract_service.client:
        raise HTTPException(status_code=503, detail="Textract nao esta configurado nesta instancia.")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    extracted = textract_service.extract_text_from_bytes(contents)
    if not extracted:
        raise HTTPException(status_code=422, detail="Nao foi possivel extrair texto do arquivo enviado.")

    return TextractResponse(extracted_text=extracted)


# Inicializar serviços e graph (depois das rotas da API para evitar captura pelo StaticFiles)
vector_store = VectorStore()
bedrock_service = BedrockService()
storage_service = StorageService()
sns_service = SnsService()
cloudwatch_service = CloudWatchService()
textract_service = TextractService()

data_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "well_architected.json")
vector_store.seed_data(os.path.abspath(data_path))

graph = create_arch_iq_graph(
    vector_store=vector_store,
    bedrock_service=bedrock_service,
    storage_service=storage_service
)


# Rota raiz - servir o index.html da interface web
@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse("web/index.html")


# Servir arquivos estáticos da pasta web (na raiz) - montado DEPOIS das rotas da API
app.mount("/", StaticFiles(directory="web", html=True), name="web")

