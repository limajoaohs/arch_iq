# ArchIQ

ArchIQ e um assistente para analise de arquitetura em nuvem e otimizacao de custos (FinOps) focado em AWS. O projeto analisa arquivos de infraestrutura como codigo (Terraform) ou descricoes textuais de arquitetura, cruza os componentes com as diretrizes do AWS Well-Architected Framework e gera apontamentos de seguranca, recomendacoes de economia e sugestoes de correcao no codigo.

A proposta e demonstrar na pratica a integracao entre modelos de linguagem (Amazon Bedrock), orquestracao com grafos de estado (LangGraph), busca vetorial com RAG (ChromaDB) e recursos do ecossistema AWS.

**Demo:** https://limajoaohs.github.io/arch_iq/ (login com cadastro aberto) · **API:** https://arch-iq.onrender.com/docs

![Arquitetura do ArchIQ](docs/architecture.svg)

---

## Arquitetura e Componentes

O fluxo de execucao e organizado em modulos independentes:

1. **Camada de Entrada (Web, CLI e API)**: Recebe o codigo Terraform ou descricao da arquitetura. Ha uma interface web (HTML/JS puro, publicada no GitHub Pages), uma CLI interativa e endpoints REST via FastAPI. Imagens/PDFs de diagramas podem ser convertidos em texto com Amazon Textract (`/api/extract-text`).
2. **Orquestrador de Agentes (LangGraph)**: Em vez de uma chamada direta e linear para a LLM, o fluxo e executado por uma maquina de estados:
   - Parser e Triagem: Identifica servicos AWS declarados (S3, EC2, RDS, VPC, Security Groups, IAM).
   - Recuperacao de Contexto (RAG): Busca regras e recomendacoes especificas para os servicos detectados.
   - Auditoria de Seguranca: Avalia riscos como portas abertas para a internet, falta de criptografia e pontos unicos de falha.
   - Otimizador FinOps: Avalia oportunidades de reducao de custos, como migracao para processadores Graviton e uso de VPC Endpoints para evitar custos de NAT Gateway.
   - Sintese e Remediacao: Gera o relatorio consolidado com nota de aderencia, diagrama Mermaid e o codigo Terraform com as correcoes aplicadas.
   - Alertas e Metricas: Publica alerta no Amazon SNS quando o score fica abaixo de 75 e grava metricas no CloudWatch.
   - Explicacao para leigos: Traduz o resultado tecnico em linguagem simples.
3. **Amazon Bedrock**: Executa o modelo de linguagem (Amazon Nova Lite por padrao) para a explicacao em linguagem simples e a remediacao de IaC, com suporte a Bedrock Guardrails. O score e os findings vem de uma analise estatica deterministica; se o Bedrock estiver indisponivel, a explicacao usa um texto de fallback e a analise continua.
4. **RAG**: Amazon Bedrock Knowledge Base (se configurada) com fallback para ChromaDB local, indexando boas praticas do AWS Well-Architected Framework.
5. **Amazon Q**: Utilizado no processo de desenvolvimento como assistente de codificacao, geracao de testes unitarios e revisao de seguranca, alem de suportar prompts de remediacao no agente.
6. **Armazenamento AWS (S3 e DynamoDB)**:
   - S3: Armazenamento persistente de relatorios e auditorias exportadas.
   - DynamoDB: Armazenamento de checkpoints de estado das sessoes para permitir continuidade em conversas longas.
7. **Amazon Cognito**: Autenticacao opcional. Quando `COGNITO_USER_POOL_ID` e `COGNITO_CLIENT_ID` estao definidos, a API exige um access token JWT (assinatura validada via JWKS) e a interface web faz login pelo Hosted UI com Authorization Code + PKCE.

---

## Estrutura do Projeto

```text
arch_iq/
├── data/
│   └── well_architected.json    # Base de conhecimento de regras AWS para o RAG
├── docs/
│   └── architecture.svg         # Diagrama visual da arquitetura
├── src/
│   ├── config.py                # Configuracoes de ambiente e servicos AWS
│   ├── aws/
│   │   ├── bedrock.py           # Cliente Bedrock (Converse API) com guardrails
│   │   ├── storage.py           # Integracoes com S3 e DynamoDB
│   │   ├── sns.py               # Alerta de score baixo
│   │   ├── cloudwatch.py        # Metricas de auditoria
│   │   ├── textract.py          # Extracao de texto de imagens/PDFs
│   │   └── amazon_q.py          # Wrapper de geracao de remediacao com Amazon Q
│   ├── rag/
│   │   ├── store.py             # Gerenciamento do ChromaDB e busca vetorial
│   │   └── retriever.py         # Recuperador de diretrizes por servico
│   ├── agents/
│   │   ├── state.py             # Definicao do estado compartilhado (TypedDict)
│   │   ├── nodes.py             # Implementacao de cada no do grafo
│   │   └── graph.py             # Montagem e compilacao do StateGraph
│   ├── terraform/
│   │   └── static_analyzer.py   # Regras de seguranca/custo e score por categoria
│   ├── api/
│   │   └── app.py               # Endpoints REST (FastAPI) e validacao do token Cognito
│   └── cli.py                   # Interface de linha de comando
├── web/                         # Interface web (GitHub Pages)
│   ├── index.html, style.css, app.js
│   ├── auth.js                  # Login Cognito (Hosted UI + PKCE)
│   └── config.js                # URL do backend e dados publicos do Cognito
├── tests/                       # Testes da API, autenticacao e grafo
├── Dockerfile                   # Imagem usada no deploy (Render)
├── requirements.txt             # Dependencias completas (desenvolvimento)
├── requirements_minimal.txt     # Dependencias de producao (Docker)
└── README.md
```

---

## Pre-requisitos

- Python 3.10 ou superior
- Credenciais da AWS configuradas localmente (`~/.aws/credentials` ou variaveis de ambiente `AWS_ACCESS_KEY_ID` e `AWS_SECRET_ACCESS_KEY`) com permissao de acesso ao Amazon Bedrock.

---

## Instalacao

1. Clone o repositorio e acesse a pasta:

```bash
git clone https://github.com/limajoaohs/arch_iq.git
cd arch_iq
```

2. Crie e ative um ambiente virtual:

```bash
python -m venv venv

# Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Linux / macOS:
source venv/bin/activate
```

3. Instale as dependencias:

```bash
pip install -r requirements.txt
```

---

## Como Usar

### 1. Interface de Linha de Comando (CLI)

Para auditar um arquivo Terraform diretamente:

```bash
python src/cli.py --file caminho/para/infra.tf
```

Para abrir o modo interativo no terminal:

```bash
python src/cli.py --interactive
```

### 2. Servidor de API (FastAPI)

Inicie o servidor de desenvolvimento:

```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

A documentacao interativa do Swagger ficara disponivel em `http://localhost:8000/docs`, e a interface web em `http://localhost:8000/`.

Copie `.env.example` para `.env` e preencha os servicos que quiser usar; todos sao opcionais. Com o Cognito configurado, envie o access token no header `Authorization: Bearer <token>`.

Exemplo de chamada via cURL (sem Cognito configurado):

```bash
curl -X POST http://localhost:8000/api/audit \
  -H "Content-Type: application/json" \
  -d '{
    "code_or_prompt": "resource \"aws_security_group\" \"web\" { ingress { from_port = 22 to_port = 22 protocol = \"tcp\" cidr_blocks = [\"0.0.0.0/0\"] } }"
  }'
```

---

## Execucao dos Testes

Para rodar os testes:

```bash
pytest tests
```

Observacao: `test_graph_end_to_end_flow` chama o Bedrock de verdade quando ha credenciais AWS no ambiente.

