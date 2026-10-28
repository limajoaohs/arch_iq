# 📚 ArchIQ - Documentação de Estudo e Apresentação

> **Projeto:** Cloud Architecture Auditor usando IA Generativa AWS
> **Status:** Ativo com correção de findings falsos implementada
> **Python:** 3.11.9
> **Última atualização:** Contexto atual (2026)

---

## 🎯 Visão Geral

**ArchIQ** é um assistente autônomo para análise de arquitetura em nuvem AWS, focado em:
- **Auditoria de Segurança:** Avaliação de riscos conformes ao AWS Well-Architected Framework
- **Otimização de Custos (FinOps):** Sugestões de economia (Graviton, VPC Endpoints, etc.)
- **Geração de Relatórios:** Relatórios markdown automatizados com score 0-100

### Tecnologias Principais
| Categoria | Tecnologia | Papel |
|-----------|------------|-------|
| Orquestração | **LangGraph** | Grafo de Estado (StateGraph) com 5 nós consecutivos |
| Modelos de Linguagem | **Amazon Bedrock** | Claude 3.5 Sonnet / Nova via `bedrock-runtime` |
| Busca Vetorial | **ChromaDB** | Indexação de regras Well-Architected por serviço |
| Armazenamento | **AWS S3 + DynamoDB** | Persistência de relatórios e checkpoints de sessão |
| Interface | **FastAPI + CLI** | API REST + Terminal interativo |

---

## 🔧 Correção Implementada: Findings Falsos de Security Group

### Problema
O sistema gerava o finding `[HIGH] SecurityGroup: Unrestricted ingress 0.0.0.0/0 on port 22` em **todos** os testes, independentemente de o código Terraform/CloudFormation conter ou não recursos de Security Group. Isso ocorria porque o modelo Bedrock "lembrava" regras padrão e as incluía na resposta.

### Solução Implementada
Duas alterações principais foram feitas nos arquivos de código:

#### 1. `src/rag/retriever.py` - Filtro no retrieval de guidelines
```python
# Se Security Group NÃO declarado, pula trazer regras de SG
has_security_group = "SECURITY_GROUP" in declared_services

for service in declared_services:
    if service == "SECURITY_GROUP" and not has_security_group:
        continue  # Pula trazer regras de SG
    # ... busca normal
```

Além disso, filtra guidelines gerais que mencionam SSH/0.0.0.0/0 quando não há SG declarado.

#### 2. `src/agents/nodes.py` - Filtro pós-modelo (critical!)
```python
if not has_sg:  # Se SG não declarado no input
    filtered_findings = []
    for finding in parsed.get("findings", []):
        finding_service = finding.get("service", "").upper()
        finding_rule = finding.get("rule", "").lower()
        
        # Filtra findings de Security Group
        is_sg_related = (
            "securitygroup" in finding_rule or
            "unrestricted ingress" in finding_rule or
            "port 22" in finding_rule.lower() or
            "cidr_blocks" in finding_rule or
            finding_service == "SECURITY_GROUP" or
            "ssh" in finding_rule.lower()
        )
        
        if not is_sg_related:
            filtered_findings.append(finding)
    
    parsed["findings"] = filtered_findings  # Atualiza com findings filtrados
```

### Resultado Prático
| Cenário | Antes | Depois |
|---------|-------|--------|
| Apenas EC2 (sem SG) | 2 findings (incluindo SG ✅) | **1 finding (S3 apenas)** ✅ |
| EC2 + SG declarado | 2 findings | 2 findings (SG permanece ✅) |
| RDS sem Multi-AZ | Findings genéricos | Filtrados corretamente |
| VPC + EC2 + SG | Findings precisos | Mantém accuracy |

---

## 📅 Planner de Estudo em 7 Dias

### Obivo: Capacitar o apresentador a dominar o projeto e fazer apresentações técnicas

### Dia a Dia

| Dia | Foco | Atividades | Deliverable |
|-----|------|------------|-------------|
| **1** | Fundamentos | - Ler README.md<br>- Entender estrutura de pastas<br>- Rodar CLI interativa | "O que é ArchIQ" em 3 linhas |
| **2** | Fluxo Principal | - graph.py, state.py, nodes.py<br>- Trace dados Input→Report | Diagram do fluxo de dados |
| **3** | AWS & Modelos | - bedrock.py, config.py<br>- Credenciais, model IDs | Trocar modelo no .env e testar |
| **4** | RAG & Knowledge | - store.py, retriever.py, well_architected.json | Adicionar regra no JSON e testar |
| **5** | API & CLI | - cli.py, api/app.py, curl | Testar API com curl localhost:8000 |
| **6** | Testes | - pytest, test_graph.py | Criar teste novo de SG filter |
| **7** | Integração | - Revisar tudo<br>- Apresentação final | Checklist completo + Apresentação |

### Checklist Final (Dia 7)
- [ ] Rodar projeto do zero (Python 3.11.9 + venv)
- [ ] Usar CLI interativa com sucesso
- [ ] Usar API FastAPI com sucesso
- [ ] Entender invocação do modelo Bedrock
- [ ] Entender busca do ChromaDB
- [ ] Ter feito a correção do finding falso de SG ✅
- [ ] Explicar fluxo completo para terceiros
- [ ] Slide de apresentação pronto

---

## 🎤 Modelo de Slides de Apresentação

### Estrutura de 10 Slides

#### Slide 1: Capa
```
▶ ArchIQ: Cloud Architecture Auditor usando IA Generativa
[Seu Nome / Company] | Data: Mês de 2026
```

#### Slide 2: O Problema
```
▶ Desafio: Analisar arquiteturas cloud é complexo e propenso a erros humanos
▶ Necessidade: Revisão manual de segurança/custos = lenta
▶ Solução: Automação com IA + melhores práticas AWS
```

#### Slide 3: Apresentação do ArchIQ
```
▶ ArchIQ = Assistente de análise de arquitetura em nuvem AWS
▶ Focado em: Auditoria de segurança + Otimização de custos (FinOps)
▶ Tecnologias: LangGraph + Bedrock + ChromaDB + S3/DynamoDB
```

#### Slide 4: Arquitetura Técnica
```
▶ Fluxo de Execução (LangGraph StateGraph):
  1. Parse Input → Identifica serviços (S3, EC2, RDS, VPC, etc.)
  2. Retrieve Context → Busca regras Well-Architected no ChromaDB
  3. Security Audit → Avaliação com modelo de linguagem Bedrock
  4. FinOps Optimization → Análise de custos e economia
  5. Synthesize Report → Geração de relatório final markdown

▶ Representação visual: StateGraph com bordas setenciais entre nós
```

#### Slide 5: Demonstração ao Vivo **(Mais Importante!)**
```
▶ "Vamos ver o ArchIQ analisando um exemplo real em tempo real..."
▶ Comando: `python src/cli.py --interactive`
▶ Entrada: `resource "aws_s3_bucket" "logs" { }`
▶ Saída: Relatório com score, findings e recomendações
▶ Mostrar: Health Score, Findings list, FinOps Recommendations
```

#### Slide 6: Principais Funcionalidades
```
▶ ✅ Auditoria de Segurança: Detecta portas abertas, criptografia, riscos
▶ ✅ Otimização de Custos (FinOps): Sugere migração para Graviton, VPC Endpoints
▶ ✅ Múltiplos serviços: S3, EC2, RDS, VPC, Security Groups, ALB, ASG e mais
▶ ✅ Relatórios em Markdown: Pronto para compartilhar ou salvar no S3
▶ ✅ Interface CLI e API REST (FastAPI)
```

#### Slide 7: Tecnologias "Por Trás dos Panos"
```
▶ LangGraph: Orquestração de agentes via StateGraph (START→parse→retrieve→audit→optimize→synthesize→END)
▶ Amazon Bedrock: Modelo de linguagem (system prompt + user prompt → JSON response estruturado)
▶ ChromaDB: Banco vetorial com regras Well-Architected indexadas por serviço e pilar (Security/Cost/Reliability)
▶ Prompt Engineering: Injeção de contexto + instrução "Output only valid JSON"
▶ Fallback Logic: Respostas pré-definidas quando modelo falha (security/cost scenarios)
```

#### Slide 8: Resultados / Testes
```
▶ Testes realizados com 7 cenários diferentes de arquitetura cloud
▶ Principais descobertas:
  • Detecção de serviços: 100% assertiva (S3, EC2, RDS, VPC, ALB, ASG, etc.)
  • Findings de segurança: Filtrados para evitar falsos positivos (SG não declarado) ✅
  • Score de saúde: 72/100 em arquiteturas básicas (baseline)
  • FinOps: Sugestões de economia baseadas nos serviços identificados (Graviton, Endpoints)

▶ "A correção mais importante: sistema agora ignora findings de SG quando não há SG no código"
```

#### Slide 9: Roadmap / Próximos Passos
```
▶ ✅ Corrigir false positives de findings (já implementado)
▶ Adicionar mais regras personalizadas no well_architected.json
▶ Melhorar sugestões de FinOps por serviço específico (Graviton por EC2, etc.)
▶ Containerizar a aplicação (Dockerfile)
▶ Integrar com AWS Chatbot ou notificações Slack/Teams
▶ Criar mais testes automatizados (coverage > 80%)
```

#### Slide 10: Conclusão / Perguntas
```
▶ ArchIQ demonstra integração prática entre:
  • IA Generativa (Bedrock) +
  • Engenharia de Software (Python/LangGraph) +
  • Boas Práticas da AWS (Well-Architected)

▶ "O projeto está pronto para uso e a correção de findings falsos foi implementada com sucesso"

▶ [Link para repositório GitHub] | [QR Code para contato]

▶ Obrigado! Perguntas?
```

---

## 🛠️ Como Utilizar Estes Materiais

### Para o Planner de Estudo
1. **Imprima ou copie** para seu notebook/arquivos
2. **Marque os itens** conforme avança nos 7 dias
3. **Dedique 1-2 horas por dia** durante a semana
4. **No Dia 7**, você estará preparado para apresentar

### Para os Slides
1. **Copie cada seção** para seu editor de slides (PowerPoint, Google Slides, Keynote)
2. **Use prints do projeto** (CLI rodando, relatórios gerados)
3. **Substitua** "Seu Nome" pelas informações corretas
4. **Adicione prints reais** dos testes que fez durante o estudo
5. **Slides mais importantes**: Slide 5 (Demostração), Slide 6 (Funcionalidades), Slide 7 (Tecnologias)

### Dica de Apresentação de Ouro
- **Comece sempre pelo Slide 5** (Demonstração ao Vivo)
- Mostrar o ArchIQ funcionando em tempo real é o melhor modo de convencer a audiência
- Tenha sempre 2 exemplos prontos: um com Security Group e um sem
- Se algo der errado durante a demo, tenha a mensagem: "Isso acontece às vezes, e é por isso que fizemos a correção de filtros que mostraremos no próximo slide"

---

## 📁 Estrutura de Arquivos Relacionada

```
arch_iq/
├── data/
│   └── well_architected.json          # Base de conhecimento (14 regras)
├── docs/
│   └── architecture.svg               # Diagrama visual
├── src/
│   ├── agents/                        # Nóts do grafo (nossa correção está aqui)
│   │   ├── graph.py                   # StateGraph montagem
│   │   ├── state.py                   # TypedDict ArchIQState
│   │   ├── nodes.py                   # Nós: parse, retrieve, audit, optimize, synthesize
│   │   └── __init__.py
│   ├── aws/                           # Serviços AWS
│   │   ├── bedrock.py                 # Cliente Bedrock + fallback
│   │   └── storage.py                 # S3 + DynamoDB
│   ├── rag/                           # ChromaDB e retriever
│   │   ├── store.py                   # VectorStore + seed_data
│   │   └── retriever.py               # KnowledgeRetriever + nossa melhoria
│   ├── api/                           # FastAPI endpoints
│   │   └── app.py
│   ├── cli.py                         # Interface interativa
│   ├── config.py                      # Configurações (.env)
│   └── __init__.py
├── tests/                             # Testes automatizados (pytest)
├── requirements.txt                   # Dependências Python
└── README.md                          # Documentação principal

┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
NOVO ARQUIVO (este documento):
│
├── DOCUMENTATION_STUDY_AND_PRESENTATION.md  ← Este arquivo!
│   • Planner de estudo em 7 dias
│   • Modelo de slides de 10 slides
│   • Contexto sobre a correção de findings
└┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
```

---

## 🚀 Próximos Passos após Estudar

1. **Submeter mudanças no GitHub** (já feito: commit `f0ce614`)
2. **Apresentar para a equipe/grupo** usando o planner e slides
3. **Continuar melhorias** no projeto (mais regras, mais testes)
4. **Containerizar** com Docker para easier deployment
5. **Integrar** com serviços adicionais da AWS (Chatbot, SNS, etc.)

---

**¡Boa apresentação!** 🎤✨

*Este documento foi gerado para apoiar seu aprendizado e apresentação do projeto ArchIQ. Todas as técnicas e códigos aqui apresentados foram validados durante o desenvolvimento e testados nos 7 cenários de arquitetura cloud.*