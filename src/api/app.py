import os
import uuid
import base64
from typing import Optional, Dict, Any, List, Literal
import anyio
import jwt
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import settings
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.aws.sns import SnsService
from src.aws.cloudwatch import CloudWatchService
from src.aws.textract import TextractService
from src.aws.history import HistoryService, ANONYMOUS
from src.aws.cache import ResultCache
from src.rag.store import VectorStore
from src.agents.graph import create_arch_iq_graph
from src.agents.qa_agent import MAX_QUESTION_CHARS, QuestionAgent


app = FastAPI(title="ArchIQ API", version="1.0.0")

# Auditorias bloqueiam uma thread durante a chamada ao Bedrock. Elas usam um limitador
# proprio para nao ocupar o pool padrao do FastAPI e travar o resto da API sob carga.
AUDIT_MAX_THREADS = 40
_audit_limiter = anyio.CapacityLimiter(AUDIT_MAX_THREADS)
# Perguntas tem limitador separado e menor: uma rajada de chat nao pode atrasar as auditorias.
ASK_MAX_THREADS = 20
_ask_limiter = anyio.CapacityLimiter(ASK_MAX_THREADS)

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
    source_name: Optional[str] = Field(None, max_length=120)  # nome do arquivo, mostrado no historico


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


class ClientRisk(BaseModel):
    id: str
    priority: int
    priority_label: str
    occurrences: int
    title: str
    meaning: str
    impact: str
    action: str


class ClientSaving(BaseModel):
    title: str
    explanation: str


class ClientReport(BaseModel):
    """Relatorio para quem nao e da area, separado da explicacao simplificada."""
    headline: str
    tone: str
    summary: str
    risks: List[ClientRisk]
    savings: List[ClientSaving]
    strengths: List[ClientSaving]
    next_steps: List[str]
    disclaimer: str
    plain_text: str


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
    client_report: ClientReport
    report_location: Optional[str] = None
    alert_sent: bool = False
    executive_summary: ExecutiveSummary
    history_id: Optional[str] = None  # None quando a analise nao entrou no historico
    cached: bool = False  # True quando o mesmo Terraform ja foi analisado e o resultado veio do cache


class HistoryEntry(BaseModel):
    id: str
    created_at: str
    score: int
    score_status: str
    services: List[str]
    findings: int
    optimizations: int
    source_name: str
    headline: str


class HistoryList(BaseModel):
    items: List[HistoryEntry]


class HistoryDetail(BaseModel):
    summary: HistoryEntry
    code: str
    result: AuditResponse


class TextractResponse(BaseModel):
    extracted_text: str


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=4000)


class AskRequest(BaseModel):
    code_or_prompt: str = Field(..., max_length=200_000)
    question: str = Field(..., max_length=MAX_QUESTION_CHARS)
    history: List[ChatTurn] = Field(default_factory=list, max_length=20)


class AskResponse(BaseModel):
    answer: str
    source: str  # "bedrock" ou "catalog" (resposta de reserva sem o modelo)


# async de proposito: o /health nao pode esperar na fila de threads, ou a hospedagem
# considera o servico morto e o reinicia justamente durante um pico de uso.
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "ArchIQ",
        "region": settings.aws_region,
        "model": settings.bedrock_model_id
    }


# async de proposito: em uma rota sync o FastAPI serializa a resposta de volta no mesmo
# pool de threads, e uma rajada so devolve as respostas quando a fila inteira termina.
@app.post("/api/audit", response_model=AuditResponse)
async def audit_architecture(request: AuditRequest, user: Optional[Dict[str, Any]] = Depends(get_current_user)):
    if not request.code_or_prompt.strip():
        raise HTTPException(status_code=400, detail="code_or_prompt cannot be empty")

    session_id = request.session_id or str(uuid.uuid4())
    result = await anyio.to_thread.run_sync(
        _run_audit, request.code_or_prompt, session_id, limiter=_audit_limiter
    )
    # Historico e um extra: se a gravacao falhar, o usuario ainda recebe a analise
    try:
        result.history_id = await anyio.to_thread.run_sync(
            history_service.save, _user_id(user), result.model_dump(exclude={"history_id"}),
            request.code_or_prompt, (request.source_name or "").strip(), limiter=_audit_limiter,
        )
    except Exception:
        result.history_id = None
    return result


def _user_id(user: Optional[Dict[str, Any]]) -> str:
    """Dono do historico: o sub do Cognito, ou um usuario local quando o login esta desativado."""
    return str(user["sub"]) if user and user.get("sub") else ANONYMOUS


@app.get("/api/history", response_model=HistoryList)
async def list_history(user: Optional[Dict[str, Any]] = Depends(get_current_user)):
    """Ultimas analises do usuario logado, da mais nova para a mais antiga."""
    try:
        items = await anyio.to_thread.run_sync(history_service.list, _user_id(user), limiter=_ask_limiter)
    except Exception:
        raise HTTPException(status_code=503, detail="Historico indisponivel no momento.")
    return HistoryList(items=items)


@app.get("/api/history/{entry_id}", response_model=HistoryDetail)
async def get_history(entry_id: str, user: Optional[Dict[str, Any]] = Depends(get_current_user)):
    try:
        entry = await anyio.to_thread.run_sync(history_service.get, _user_id(user), entry_id, limiter=_ask_limiter)
    except Exception:
        raise HTTPException(status_code=503, detail="Historico indisponivel no momento.")
    if not entry:
        raise HTTPException(status_code=404, detail="Analise nao encontrada.")
    entry["result"]["history_id"] = entry_id
    return HistoryDetail(**entry)


@app.delete("/api/history/{entry_id}", status_code=204)
async def delete_history(entry_id: str, user: Optional[Dict[str, Any]] = Depends(get_current_user)):
    try:
        deleted = await anyio.to_thread.run_sync(history_service.delete, _user_id(user), entry_id, limiter=_ask_limiter)
    except Exception:
        raise HTTPException(status_code=503, detail="Historico indisponivel no momento.")
    if not deleted:
        raise HTTPException(status_code=404, detail="Analise nao encontrada.")


def _run_audit(code_or_prompt: str, session_id: str) -> AuditResponse:
    initial_state = {
        "session_id": session_id,
        "raw_input": code_or_prompt
    }

    # Mesmo Terraform, mesmo resultado: o cache poupa o Bedrock, o S3, o SNS e as metricas
    cached = result_cache.get(code_or_prompt)
    if cached:
        return AuditResponse(**{**cached, "session_id": session_id, "report_location": None,
                                "alert_sent": False, "cached": True})

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

        response = AuditResponse(
            session_id=session_id,
            score=score,
            parsed_services=final_state.get("parsed_services", []),
            security_audit=sec_audit,
            finops_audit=fin_audit,
            remediated_iac=final_state.get("remediated_iac", ""),
            final_report=final_state.get("final_report", ""),
            technical_report=final_state.get("technical_report", ""),
            layperson_explanation=final_state.get("layperson_explanation", ""),
            client_report=ClientReport(**final_state["client_report"]),
            report_location=final_state.get("report_location"),
            alert_sent=final_state.get("alert_sent", False),
            executive_summary=executive_summary
        )
        # Texto de reserva (Bedrock fora do ar ou sem cota) nao entra no cache: a proxima analise tenta de novo
        if final_state.get("layperson_source") == "bedrock":
            result_cache.put(code_or_prompt, response.model_dump(
                exclude={"session_id", "report_location", "alert_sent", "history_id", "cached"}))
        return response
    except Exception as e:
        # Não expor stack traces nem detalhes internos ao cliente
        raise HTTPException(status_code=500, detail="Erro interno do servidor ao processar a solicitação.")


@app.post("/api/ask", response_model=AskResponse)
async def ask_question(request: AskRequest, user: Optional[Dict[str, Any]] = Depends(get_current_user)):
    """Responde uma pergunta do usuario sobre a analise do Terraform enviado."""
    if not request.code_or_prompt.strip() or not request.question.strip():
        raise HTTPException(status_code=400, detail="code_or_prompt e question sao obrigatorios")

    history = [turn.model_dump() for turn in request.history]
    try:
        result = await anyio.to_thread.run_sync(
            question_agent.answer, request.code_or_prompt, request.question, history,
            limiter=_ask_limiter,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Erro interno ao responder a pergunta.")
    return AskResponse(**result)


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
history_service = HistoryService()
result_cache = ResultCache()
question_agent = QuestionAgent(bedrock_service, result_cache)

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

