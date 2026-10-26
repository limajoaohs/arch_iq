# Deploy ArchIQ no GitHub Pages

## Arquitetura

| Camada | Onde roda | Tecnologia |
|--------|-----------|------------|
| Frontend | GitHub Pages (estático) | HTML + JS + CSS (`web/`) |
| Backend | Serviço separado (Render, Railway, Fly.io, AWS, etc.) | FastAPI + Python |

O GitHub Pages **não roda backend Python**. Você precisa hospedar a API FastAPI em outro lugar e apontar o frontend para ela.

---

## 1. Hospedar o Backend (FastAPI)

Escolha um serviço que suporte Python/Docker:

- **Render**: https://render.com (grátis tier disponível)
- **Railway**: https://railway.app
- **Fly.io**: https://fly.io
- **AWS**: Elastic Beanstalk, ECS, Lambda + API Gateway

### Exemplo no Render

1. Conecte seu repositório GitHub ao Render.
2. Crie um novo **Web Service**.
3. Build Command: `pip install -r requirements_minimal.txt`
4. Start Command: `python -m uvicorn src.api.app:app --host 0.0.0.0 --port $PORT`
5. Adicione as variáveis de ambiente do `.env` (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, BEDROCK_MODEL_ID, AWS_REGION, etc.)
6. Após o deploy, você terá uma URL tipo: `https://archiq-api.onrender.com`

---

## 2. Configurar a URL do Backend no Frontend

Edite o arquivo `web/config.js`:

```javascript
window.API_CONFIG = {
  baseUrl: 'https://seu-backend.onrender.com',  // <-- coloque a URL aqui
  auditEndpoint: '/api/audit',
  healthEndpoint: '/health'
};
```

Se deixar `baseUrl: ''`, o frontend tentará chamar a API no mesmo domínio (funciona apenas em localhost com o servidor rodando).

---

## 3. Habilitar CORS no Backend

O backend precisa aceitar requisições do domínio do GitHub Pages. No `src/api/app.py`, adicione o middleware CORS:

```python
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="ArchIQ API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://seu-usuario.github.io", "http://localhost:8000"],  # ajuste
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 4. Habilitar o GitHub Pages no Repositório

1. Vá em **Settings > Pages** do seu repositório no GitHub.
2. Em **Build and deployment > Source**, selecione **GitHub Actions**.
3. Faça um push na branch `main` para disparar o workflow `.github/workflows/deploy.yml`.
4. Após o deploy, o site estará disponível em:
   `https://SEU_USUARIO.github.io/arch_iq/`

---

## 5. Testar Localmente (antes do deploy)

```powershell
# Terminal 1 - Backend
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000

# Terminal 2 - Frontend (servidor estático simples)
python -m http.server 5500 --directory web
```

Acesse: `http://localhost:5500`

---

## Arquivos criados/modificados

- `web/config.js` — configuração da URL da API
- `web/index.html` — inclui `config.js` antes do `app.js`
- `web/app.js` — usa `window.API_CONFIG.baseUrl` para montar a URL do endpoint
- `.github/workflows/deploy.yml` — workflow de deploy automático no GitHub Pages
- `SETUP_GITHUB_PAGES.md` — este arquivo
