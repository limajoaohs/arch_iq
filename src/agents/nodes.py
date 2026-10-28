import json
import re
import time
from typing import Dict, Any, List, Optional
from .state import ArchIQState
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.aws.amazon_q import AmazonQAssistant
from src.aws.sns import SnsService
from src.aws.cloudwatch import CloudWatchService
from src.aws.textract import TextractService
from src.rag.retriever import KnowledgeRetriever
from src.terraform.static_analyzer import analyze_terraform


class AgentNodes:
    def __init__(
        self,
        bedrock: BedrockService,
        retriever: KnowledgeRetriever,
        storage: StorageService,
        sns: Optional[SnsService] = None,
        cloudwatch: Optional[CloudWatchService] = None,
        textract: Optional[TextractService] = None,
    ):
        self.bedrock = bedrock
        self.retriever = retriever
        self.storage = storage
        self.sns = sns
        self.cloudwatch = cloudwatch
        self.textract = textract
        self.amazon_q = AmazonQAssistant(bedrock)

    def parse_input(self, state: ArchIQState) -> Dict[str, Any]:
        raw_text = state.get("raw_input", "")
        service_patterns = {
            "S3": ["s3", "aws_s3"],
            "EC2": ["ec2", "aws_ec2", "aws_instance"],
            "RDS": ["rds", "aws_rds", "aws_db_instance"],
            "DYNAMODB": ["dynamodb", "aws_dynamodb"],
            "LAMBDA": ["lambda", "aws_lambda"],
            "VPC": ["vpc", "aws_vpc"],
            "SECURITY_GROUP": ["security_group", "aws_security_group"],
            "IAM": ["iam", "aws_iam"],
            "ALB": ["alb", "aws_alb", "aws_lb"],
            "ASG": ["asg", "aws_asg", "aws_autoscaling_group"],
            "ECS": ["ecs", "aws_ecs"],
            "EKS": ["eks", "aws_eks"],
            "CLOUDFRONT": ["cloudfront", "aws_cloudfront"],
            "SQS": ["sqs", "aws_sqs"],
            "SNS": ["sns", "aws_sns"],
            "KMS": ["kms", "aws_kms"],
        }

        found = []
        lower = raw_text.lower()
        for svc_name, patterns in service_patterns.items():
            if any(pattern in lower for pattern in patterns):
                found.append(svc_name)

        if not found:
            found = ["GENERAL_AWS"]

        return {"parsed_services": found}

    def retrieve_context(self, state: ArchIQState) -> Dict[str, Any]:
        services = state.get("parsed_services", [])
        guidelines = self.retriever.retrieve_guidance(services)
        return {"retrieved_knowledge": guidelines}

    def audit_security(self, state: ArchIQState) -> Dict[str, Any]:
        raw_input = state.get("raw_input", "")

        # Se o input vier como bytes/base64 de imagem ou PDF, extrai texto com Textract
        image_text = self._extract_text_if_image(raw_input)
        if image_text:
            raw_input = image_text

        start = time.time()

        # Analise estatica primaria (nao depende de LLM / credenciais AWS)
        static_result = analyze_terraform(raw_input)

        duration = time.time() - start

        score = static_result["score"]
        findings = static_result["findings"]
        services = static_result["services"]

        # Manter somente a analise estatica (ja suficiente e deterministica)
        return {
            "security_audit": {
                "score": score,
                "findings": findings,
            },
            "parsed_services": services,
            "duration_seconds": duration,
            "image_extracted_text": image_text,
        }

    def _extract_text_if_image(self, raw_input: str) -> str:
        """Tenta extrair texto de imagem/PDF via Textract se o input parecer um documento binario."""
        if not self.textract:
            return ""

        # Assinaturas magicas comuns (base64 decodificado nao e possivel aqui sem lib,
        # entao verificamos se o texto comeca com cabecalho de PDF ou e longo o suficiente
        # para ser base64 de imagem).
        lower = raw_input.strip().lower()
        if lower.startswith("%pdf") or len(raw_input) > 1000 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in raw_input.strip()):
            try:
                import base64
                document_bytes = base64.b64decode(raw_input.strip())
                return self.textract.extract_text_from_bytes(document_bytes)
            except Exception:
                return ""
        return ""

    def optimize_finops(self, state: ArchIQState) -> Dict[str, Any]:
        raw_input = state.get("raw_input", "")

        # Analise estatica de FinOps (nao depende de LLM)
        static_result = analyze_terraform(raw_input)
        optimizations = static_result["optimizations"]

        # Calcular percentual de economia baseado nas otimizacoes encontradas
        savings_pct = min(60, len(optimizations) * 12)

        return {"finops_audit": {"monthly_savings_pct": savings_pct, "optimizations": optimizations}}

    def synthesize_report(self, state: ArchIQState) -> Dict[str, Any]:
        sec = state.get("security_audit", {})
        fin = state.get("finops_audit", {})
        score = sec.get("score", 80)

        findings_lines = []
        for f in sec.get("findings", []):
            findings_lines.append(
                "- [" + str(f.get("severity") or "INFO") + "] " + str(f.get("service") or "N/A") + ": " + str(f.get("rule") or "N/A") + " -> " + str(f.get("remediation") or "N/A")
            )

        opt_lines = []
        for o in fin.get("optimizations", []):
            opt_lines.append(
                "- " + str(o.get("service") or "N/A") + ": " + str(o.get("action") or "N/A") + " (" + str(o.get("impact") or "N/A") + ")"
            )

        findings_str = "\n".join(findings_lines) if findings_lines else "Nenhum risco critical de segurança identificado."
        opt_str = "\n".join(opt_lines) if opt_lines else "A carga de trabalho já atende aos criticos de alocacao de custos basais."

        # Generate mermaid diagram for architecture visualization
        services = state.get("parsed_services", [])
        mermaid_diagram = self._generate_mermaid_diagram(services)

        report_md = (
            "# ArchIQ Relatorio de Conformidade e Arquitetura\n\n"
            "### Score de Saude Geral\n"
            f"> **{score} / 100**\n\n"
            f"{mermaid_diagram}\n\n"
            "---\n\n"
            "## Poupança Mensal Potencial\n"
            f"> {fin.get('monthly_savings_pct', 0)}%\n\n"
            "---\n\n"
            "## Servicos Identificados\n"
            f"> {', '.join(services) if services else 'Nenhum'}\n\n"
            "---\n\n"
            "## Findings de Seguranca e Bem-Architected\n\n"
            f"{findings_str}\n\n"
            "---\n\n"
            "## Recomendacoes de FinOps e Custos\n\n"
            f"{opt_str}\n\n"
            "---"
        )

        try:
            remediated = self.amazon_q.generate_iac_remediation(
                original_iac=state.get("raw_input", ""),
                findings=sec.get("findings", [])
            )
        except Exception:
            remediated = ""  # Bedrock indisponivel: o relatorio segue sem IaC remediado

        s3_uri = self.storage.save_report(report_md)

        return {
            "score": score,
            "final_report": report_md,
            "technical_report": report_md,
            "remediated_iac": remediated,
            "report_location": s3_uri
        }

    def send_alerts_and_metrics(self, state: ArchIQState) -> Dict[str, Any]:
        """Envia alerta SNS se o score estiver baixo e grava metricas no CloudWatch."""
        score = state.get("score", state.get("security_audit", {}).get("score", 80))
        services = state.get("parsed_services", [])
        duration = state.get("duration_seconds", 0.0)
        findings = state.get("security_audit", {}).get("findings", [])
        session_id = state.get("session_id", "")

        # Alerta SNS quando score abaixo de 75
        alert_sent = False
        if score < 75 and self.sns and self.sns.is_enabled():
            alert_sent = self.sns.publish_low_score_alert(
                session_id=session_id,
                score=score,
                services=services,
                top_findings=findings[:3],
            )

        # Metricas CloudWatch
        if self.cloudwatch:
            self.cloudwatch.put_audit_metric(
                score=score,
                services_count=len(services),
                duration_seconds=duration,
                success=True,
            )

        return {"alert_sent": alert_sent}

    def explain_for_layperson(self, state: ArchIQState) -> Dict[str, Any]:
        """Gera uma explicacao didatica da arquitetura para leigos usando o Bedrock.

        Traduz os resultados tecnicos (score, findings, optimizacoes, servicos)
        em linguagem simples, explicando cada ponto especifico sem jargon desnecessario.
        """
        sec = state.get("security_audit", {})
        fin = state.get("finops_audit", {})
        score = sec.get("score", state.get("score", 80))
        services = state.get("parsed_services", [])
        knowledge = state.get("retrieved_knowledge", "")

        # Monta resumo dos findings tecnicos para o LLM traduzir
        findings_lines = []
        for f in sec.get("findings", []):
            findings_lines.append(
                f"- Servico: {f.get('service', 'N/A')} | Severidade: {f.get('severity', 'INFO')} | "
                f"Problema: {f.get('rule', 'N/A')} | Solucao sugerida: {f.get('remediation', 'N/A')}"
            )
        findings_str = "\n".join(findings_lines) if findings_lines else "Nenhum problema de seguranca identificado."

        opt_lines = []
        for o in fin.get("optimizations", []):
            opt_lines.append(
                f"- Servico: {o.get('service', 'N/A')} | Acao: {o.get('action', 'N/A')} | "
                f"Impacto: {o.get('impact', 'N/A')}"
            )
        opt_str = "\n".join(opt_lines) if opt_lines else "Nenhuma otimizacao de custo identificada."

        services_str = ", ".join(services) if services else "Nenhum servico especifico identificado"
        savings_pct = fin.get("monthly_savings_pct", 0)

        prompt = f"""Voce recebeu o resultado tecnico de uma auditoria de arquitetura na nuvem AWS.
Sua tarefa e escrever, como se fosse uma pessoa conversando com outra pessoa, uma explicacao simples e acolhedora para alguem que NAO entende nada de tecnologia da nuvem.

Dados tecnicos da auditoria (use apenas como base, nao repita termos brutos):
- Servicos identificados: {services_str}
- Nota geral de saude da arquitetura: {score} / 100
- Economia potencial mensal estimada: {savings_pct}%
- Diretrizes do AWS Well-Architected encontradas: {knowledge}

Problemas de seguranca encontrados (traduzir cada um em palavras simples):
{findings_str}

Oportunidades de economia de custo (traduzir cada uma em palavras simples):
{opt_str}

Escreva em portugues do Brasil, seguindo estas regras:
- Escreva como quem explica para um amigo ou familiar que nao sabe nada de nuvem. Paragrafos curtos, tom conversacional e acolhedor.
- Nao use listas numeradas, nao use marcadores com traços (-), nao use secoes rotuladas tipo "a)", "b)", "c)". Escreva fluido, como um texto normal.
- Nunca jogue uma sigla ou termo tecnico sozinho (EC2, S3, VPC, Security Group, IaC). Sempre que mencionar, explique brevemente o que significa na mesma frase ou na seguinte, de forma natural.
- Explique cada problema individualmente: o que significa, por que e um risco, o que pode acontecer se nao consertar e como consertar de forma simples.
- Explique cada chance de economizar dinheiro individualmente.
- Seja encorajador e nao alarmista. Evite palavras como "critico", "perigo", "alerta" ou "urgente".
- Voce pode usar analogias simples do dia a dia quando ajudar a entender (por exemplo: comparar um Security Group a um porteiro de predio).
- Nao invente informacoes que nao estejam nos dados acima.
- Nao assine o texto, nao diga "sou uma IA", nao use frases como "Aqui esta a explicacao" ou "Como modelo de linguagem". Comece direto com a explicacao."""

        system_prompt = (
            "Voce escreve como um amigo experiente em tecnologia explicando para um familiar leigo. "
            "Tom conversacional, paragrafos curtos, sem listas, sem jargon tecnico desnecessario, "
            "sempre em portugues do Brasil. Nao soe como uma inteligencia artificial."
        )

        try:
            explanation = self.bedrock.invoke(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=3000,
                temperature=0.3,
            )
        except Exception:
            explanation = self._fallback_layperson_explanation(
                score, services, findings_str, opt_str, savings_pct
            )

        return {"layperson_explanation": explanation}

    def _fallback_layperson_explanation(self, score, services, findings_str, opt_str, savings_pct) -> str:
        """Explicacao didatica deterministica usada quando o Bedrock nao esta disponivel."""
        if score >= 90:
            status = "otima"
        elif score >= 75:
            status = "boa"
        elif score >= 50:
            status = "regular"
        else:
            status = "precisa de atencao"

        services_lista = ", ".join(services) if services else "varios servicos da nuvem AWS"

        lines = [
            "Analisamos os servicos da nuvem AWS que voce usou: " + services_lista + ".",
            f"A nota geral da sua arquitetura e {score} de 100, o que esta considerado {status}.",
            f"Voce pode economizar cerca de {savings_pct}% por mes nos custos da nuvem.",
            "",
        ]

        if findings_str.strip() and "Nenhum problema" not in findings_str:
            lines.append("Precisamos olhar com calma alguns pontos:")
            lines.append(findings_str.replace("- ", ""))
            lines.append("")
        else:
            lines.append("Boa notica: nao encontramos problemas graves de seguranca nos servicos analisados.")
            lines.append("")

        if opt_str.strip() and "Nenhuma otimizacao" not in opt_str:
            lines.append("Tambem ha chances de economizar dinheiro todo mes:")
            lines.append(opt_str.replace("- ", ""))
            lines.append("")

        lines.append("Nosso conselho e levar as coisas com calma. Converse com quem cuida da tecnologia de voce e aplique as melhorias aos poucos, sem pressa.")
        return "\n".join(lines)

    def _generate_mermaid_diagram(self, services: List[str]) -> str:
        """Generate a simple mermaid diagram visualizing the detected services."""
        if not services or services == ["GENERAL_AWS"]:
            return "*Nenhum serviço específico identificado - diagrama simplificado*"

        compute_services = {"EC2", "LAMBDA", "ECS", "EKS", "ASG"}
        present = set(services)

        lines = ["graph TD"] + [f"    {svc}[{svc}]" for svc in services]

        # Conexoes comuns, somente entre servicos que existem no diagrama
        if "VPC" in present:
            lines += [f"    VPC -->|hosts| {svc}" for svc in services if svc in compute_services]
        if {"S3", "CLOUDFRONT"} <= present:
            lines.append("    CLOUDFRONT -->|distributes| S3")
        if "IAM" in present:
            lines += [f"    IAM -.->|manages| {svc}" for svc in services if svc != "IAM"]

        return "```mermaid\n" + "\n".join(lines) + "\n```"