import json
import re
from typing import Dict, Any, List
from .state import ArchIQState
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.aws.amazon_q import AmazonQAssistant
from src.rag.retriever import KnowledgeRetriever
from src.terraform.static_analyzer import analyze_terraform


class AgentNodes:
    def __init__(self, bedrock: BedrockService, retriever: KnowledgeRetriever, storage: StorageService):
        self.bedrock = bedrock
        self.retriever = retriever
        self.storage = storage
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

        # Analise estatica primaria (nao depende de LLM / credenciais AWS)
        static_result = analyze_terraform(raw_input)

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
        }

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

        remediated = self.amazon_q.generate_iac_remediation(
            original_iac=state.get("raw_input", ""),
            findings=sec.get("findings", [])
        )

        s3_uri = self.storage.save_report(report_md)

        return {
            "score": score,
            "final_report": report_md,
            "remediated_iac": remediated,
            "report_location": s3_uri
        }

    def _generate_mermaid_diagram(self, services: List[str]) -> str:
        """Generate a simple mermaid diagram visualizing the detected services."""
        if not services or services == ["GENERAL_AWS"]:
            return "*Nenhum serviço específico identificado - diagrama simplificado*"

        # Define service group categories
        compute_services = {"EC2", "LAMBDA", "ECS", "EKS", "ASG"}
        storage_services = {"S3", "DYNAMODB"}
        database_services = {"RDS"}
        networking_services = {"VPC", "ALB", "CLOUDFRONT"}
        messaging_services = {"SQS", "SNS"}
        identity_services = {"IAM", "KMS"}

        # Build diagram nodes
        nodes = []
        edges = []

        for svc in services:
            if svc in compute_services:
                nodes.append(f"    {svc}[{svc}]")
            elif svc in storage_services:
                nodes.append(f"    {svc}[{svc}]")
            elif svc in database_services:
                nodes.append(f"    {svc}[{svc}]")
            elif svc in networking_services:
                nodes.append(f"    {svc}[{svc}]")
            elif svc in messaging_services:
                nodes.append(f"    {svc}[{svc}]")
            elif svc in identity_services:
                nodes.append(f"    {svc}[{svc}]")
            else:
                nodes.append(f"    {svc}[{svc}]")

        # Add general connections based on common patterns
        # Compute services often sit behind VPC
        if any(s in compute_services for s in services) and "VPC" in services:
            edges.append("    VPC -->|hosts| EC2")
            edges.append("    VPC -->|hosts| ECS")
            edges.append("    VPC -->|hosts| Lambda")

        # S3 often used with CloudFront for delivery
        if "S3" in services and "CLOUDFRONT" in services:
            edges.append("    CLOUDFRONT -->|distributes| S3")

        # IAM and KMS are foundational
        if "IAM" in services:
            edges.append("    IAM -->|manages| all other services")

        # Build mermaid source
        lines = ["graph TD"]
        for node in nodes:
            lines.append(node)
        for edge in edges:
            lines.append(edge)

        return "\n".join(lines)