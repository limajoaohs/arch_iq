# Deploy ArchIQ no AWS (próprio ambiente)

## Arquitetura recomendada

| Camada | Serviço AWS | Custo |
|--------|-------------|-------|
| Backend (FastAPI) | **AWS App Runner** | Pago (~$20-40/mês) |
| Frontend (estático) | **Amazon S3 + CloudFront** | Baixo / Free Tier |

---

## Pré-requisitos

- Conta AWS com acesso ao console
- AWS CLI configurado (`aws configure`)
- Permissões para: App Runner, S3, CloudFront, IAM, Bedrock

---

## Passo 1: Preparar o repositório

Certifique-se de que esses arquivos existem na raiz do projeto:

```
arch_iq/
├── Dockerfile                      <- criado (container do backend)
├── requirements_minimal.txt        <- dependencias reduzidas
├── src/api/app.py                  <- FastAPI com CORS configurável
├── web/                            <- frontend estático
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── config.js                   <- URL do backend aqui
├── .env                            <- suas credenciais AWS (não commitar)
└── data/                           <- bem_architected.json
```

O `.env` e `.venv` já estão no `.gitignore` — não subir para o GitHub.

---

## Passo 2: Hospedar o Backend no App Runner

### Opção A: Via Console AWS (mais simples)

1. Acesse o console AWS → **App Runner** → **Create service**.
2. **Source**: Escolha **Source code repository** → conecte seu GitHub.
3. Selecione o repositório `arch_iq` e a branch `main`.
4. **Runtime**: Python.
5. **Build command**: `pip install -r requirements_minimal.txt`
6. **Start command**: `python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8080`
7. **Port**: `8080`
8. **Variáveis de ambiente** (adicionar todas essas):
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION` = `us-east-1`
   - `BEDROCK_MODEL_ID` = `amazon.nova-lite-v1:0`
   - `CHROMA_PERSIST_DIR` = `/tmp/chroma_data`
   - `S3_REPORTS_BUCKET` = (seu bucket)
   - `DYNAMODB_TABLE_NAME` = (sua tabela)
   - `CORS_ORIGINS` = `https://seu-frontend.s3-website-us-east-1.amazonaws.com` (ou o domínio do CloudFront)
   - `PYTHONUNBUFFERED` = `1`
9. Crie o serviço. Após alguns minutos, você receberá uma URL tipo:
   `https://abc123.us-east-1.awsapprunner.com`

### Opção B: Via Dockerfile (recomendado para controle total)

No App Runner, escolha **Source code repository** → **Dockerfile** no lugar de Runtime Python. O Dockerfile já está pronto na raiz.

---

## Passo 3: Hospedar o Frontend no Amazon S3

1. Acesse o console AWS → **S3** → **Create bucket**.
   - Nome: `archiq-frontend-seunome` (único globalmente)
   - Região: `us-east-1`
   - Desmarque "Block all public access" (necessário para hospedagem estática)
   - Confirme os avisos

2. Vá em **Properties** → **Static website hosting** → **Enable**.
   - Index document: `index.html`
   - Error document: `index.html`
   - Anote o **Bucket website endpoint** (ex: `http://archiq-frontend-seunome.s3-website-us-east-1.amazonaws.com`)

3. Vá em **Permissions** → **Bucket policy** e adicione:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::archiq-frontend-seunome/*"
    }
  ]
}
```

4. Faça upload dos arquivos da pasta `web/`:
   - `index.html`
   - `app.js`
   - `style.css`
   - `config.js`

---

## Passo 4: Configurar a URL do backend no frontend

Edite o arquivo `web/config.js` **antes de fazer upload para o S3**:

```javascript
window.API_CONFIG = {
  baseUrl: 'https://abc123.us-east-1.awsapprunner.com',  // URL do App Runner
  auditEndpoint: '/api/audit',
  healthEndpoint: '/health'
};
```

Se estiver testando localmente, deixe `baseUrl: ''`.

---

## Passo 5: Configurar CORS no backend

No App Runner, adicione a variável de ambiente:

```
CORS_ORIGINS=https://seu-bucket.s3-website-us-east-1.amazonaws.com
```

Ou, se usar CloudFront:

```
CORS_ORIGINS=https://d1234567890.cloudfront.net
```

Para permitir múltiplas origens, separe por vírgula:
```
CORS_ORIGINS=https://d1234567890.cloudfront.net,http://localhost:8000
```

---

## Passo 6: (Opcional) CloudFront + HTTPS

O S3 hospedagem estática entrega apenas HTTP. Para HTTPS:

1. Vá em **CloudFront** → **Create distribution**.
2. **Origin**: selecione o bucket S3 (use o endpoint de REST, não o de website).
3. **Default cache behavior**: 
   - Viewer protocol policy: `Redirect HTTP to HTTPS`
   - Permita métodos: `GET, HEAD, OPTIONS, POST`
4. Crie a distribuição. Aguarde o deploy (10-15 min).
5. Use o domínio do CloudFront (`https://d1234567890.cloudfront.net`) no `config.js` e no `CORS_ORIGINS`.

---

## Passo 7: Testar localmente antes do deploy

```powershell
# Terminal 1 - Backend
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000

# Terminal 2 - Frontend estático
python -m http.server 5500 --directory web
```

Acesse: `http://localhost:5500`  
O frontend tentará chamar `http://localhost:8000/api/audit` (por `baseUrl: ''` no `config.js`).

---

## Arquivos criados/modificados para deploy AWS

| Arquivo | O que faz |
|---------|-----------|
| `Dockerfile` | Container do backend FastAPI para App Runner |
| `src/api/app.py` | Adicionado middleware CORS configurável via `CORS_ORIGINS` |
| `web/config.js` | Arquivo de configuração da URL do backend |
| `AWS_DEPLOY.md` | Este guia |

---

## Comando rápido para subir frontend via AWS CLI

```powershell
# Subir arquivos da pasta web para o bucket S3
aws s3 sync web/ s3://archiq-frontend-seunome --delete

# Ou subir arquivos individuais
aws s3 cp web/index.html s3://archiq-frontend-seunome/index.html
aws s3 cp web/app.js s3://archiq-frontend-seunome/app.js
aws s3 cp web/style.css s3://archiq-frontend-seunome/style.css
aws s3 cp web/config.js s3://archiq-frontend-seunome/config.js
```
