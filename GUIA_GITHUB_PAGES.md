# Guia Rápido: ArchIQ no GitHub Pages + Backend Externo

## Arquitetura

| Camada | Hospedagem | Tecnologia |
|--------|-----------|------------|
| Frontend | GitHub Pages (estático) | HTML + CSS + JS (`web/`) |
| Backend | Serviço externo (Render/Railway/etc.) | FastAPI + Python + AWS Bedrock |

---

## 1. Estrutura de arquivos para deploy automático

O GitHub Pages pega o conteúdo da pasta `web/` e publica como site estático. O fluxo é:

```
arch_iq/
├── web/
│   ├── index.html      <- página principal
│   ├── app.js          <- frontend (chama a API externa)
│   ├── style.css       <- estilos
│   └── config.js       <- URL do backend (você preenche)
├── .github/
│   └── workflows/
│       └── deploy.yml  <- CI/CD automático para GitHub Pages
├── src/api/app.py      <- backend FastAPI (roda fora do GitHub Pages)
└── Dockerfile          <- opcional, se for containerizar o backend
```

### Como o deploy funciona

O arquivo `.github/workflows/deploy.yml` dispara automaticamente a cada `push` na branch `main` (quando houver mudanças em `web/`). Ele:
1. Copia o conteúdo de `web/` para o site do GitHub Pages
2. Publica em `https://SEU_USUARIO.github.io/arch_iq/`

---

## 2. Configurar URL do backend no frontend

Edite o arquivo `web/config.js` **antes de fazer push**:

```javascript
window.API_CONFIG = {
  baseUrl: 'https://seu-backend.onrender.com',  // <-- URL do seu backend externo
  auditEndpoint: '/api/audit',
  healthEndpoint: '/health'
};
```

- Se deixar `baseUrl: ''`, o frontend tentará chamar a API no mesmo domínio (só funciona em localhost).
- Após preencher, faça commit e push. O GitHub Actions fará o deploy automaticamente.

---

## 3. Configurar CORS no backend (obrigatório)

O backend precisa aceitar requisições do domínio do GitHub Pages. No seu serviço de hospedagem (Render, Railway, etc.), defina a variável de ambiente:

```
CORS_ORIGINS=https://SEU_USUARIO.github.io/arch_iq
```

No `src/api/app.py` isso já está implementado:

```python
cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Se quiser permitir também localhost para testes locais:

```
CORS_ORIGINS=https://SEU_USUARIO.github.io/arch_iq,http://localhost:8000
```

---

## 4. Passo a passo para subir o frontend e ativar o GitHub Pages

### Passo A: Verifique se está na branch main

```powershell
git branch
git checkout main
```

### Passo B: Adicione e faça commit dos arquivos do frontend

```powershell
git add web/ .github/workflows/deploy.yml
git commit -m "feat: prepara frontend para GitHub Pages"
git push origin main
```

### Passo C: Ative o GitHub Pages no repositório

1. Acesse seu repositório no GitHub: `https://github.com/limajoaohs/arch_iq`
2. Vá em **Settings** > **Pages** (menu lateral esquerdo)
3. Em **Build and deployment** > **Source**, selecione **GitHub Actions**
4. Salve. O próximo push na branch `main` disparará o deploy automaticamente.

### Passo D: Acesse o site

Após o workflow rodar (check na aba Actions), o site ficará disponível em:

```
https://limajoaohs.github.io/arch_iq/
```

---

## 5. Melhores opções gratuitas para rodar o backend FastAPI

O backend precisa de:
- Python + FastAPI
- Acesso às credenciais AWS (chaves de acesso + Bedrock)
- Memória suficiente para rodar LangGraph + ChromaDB + Bedrock

### Opções recomendadas (Free Tier)

| Serviço | Free Tier | Limitações | Ideal para |
|---------|-----------|------------|------------|
| **Render** | ✅ Sim | Servidor "spina down" após inativação (cold start ~30s). 512 MB RAM. | Simplicidade, sobe direto do GitHub |
| **Railway** | ⚠️ Parcial | Trial de ~$5 em créditos, depois paga. Não é totalmente grátis a longo prazo. | Facilidade de deploy |
| **Fly.io** | ⚠️ Parcial | Pequeno crédito inicial, depois exige cartão. | Performance |
| **Koyeb** | ✅ Sim | Nível gratuito com limitações de CPU/RAM. | Alternativa ao Render |
| **AWS App Runner** | ❌ Não | Não tem free tier permanente (cobrado por uso). | Evite se quer grátis |

### 🏆 Recomendação: Render (mais simples e gratuito)

1. Crie conta em https://render.com
2. Conecte seu GitHub (`limajoaohs/arch_iq`)
3. Crie um **Web Service**:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements_minimal.txt`
   - **Start Command**: `python -m uvicorn src.api.app:app --host 0.0.0.0 --port $PORT`
   - **Port**: `10000` (Render usa essa porta automaticamente via `$PORT`)
4. Adicione as variáveis de ambiente:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION` = `us-east-1`
   - `BEDROCK_MODEL_ID` = `amazon.nova-lite-v1:0`
   - `CHROMA_PERSIST_DIR` = `/tmp/chroma_data`
   - `CORS_ORIGINS` = `https://limajoaohs.github.io/arch_iq`
   - `PYTHONUNBUFFERED` = `1`
5. Após o deploy, copie a URL gerada (ex: `https://archiq.onrender.com`) e cole no `web/config.js`.

### Ajuste no Dockerfile (se usar Render com Docker)

Se preferir subir via Docker no Render, o `Dockerfile` já existe na raiz. Apenas aponte para ele nas configurações do serviço.

---

## 6. Testar localmente antes do deploy

```powershell
# Terminal 1 - Backend
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000

# Terminal 2 - Frontend estático
python -m http.server 5500 --directory web
```

Acesse: `http://localhost:5500`  
(O `config.js` com `baseUrl: ''` chamará `http://localhost:8000/api/audit`)

---

## Resumo do que fazer agora

1. [ ] Hospede o backend no Render (ou similar)
2. [ ] Defina `CORS_ORIGINS` no backend com a URL do GitHub Pages
3. [ ] Preencha `baseUrl` em `web/config.js` com a URL do backend
4. [ ] `git add web/ .github/` → `git commit` → `git push origin main`
5. [ ] Ative GitHub Pages em Settings > Pages do repositório
6. [ ] Acesse `https://limajoaohs.github.io/arch_iq/` e teste o upload do `.tf`
