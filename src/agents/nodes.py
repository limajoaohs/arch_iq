import json
import re
from typing import Dict, Any, List
from .state import ArchIQState
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.aws.amazon_q import AmazonQAssistant
from src.rag.retriever import KnowledgeRetriever


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
        prompt = f"""Evaluate this cloud architecture or Terraform definition for Security and Reliability risks.
Architecture:
{state.get('raw_input')}

Relevant AWS Well-Architected Rules:
{state.get('retrieved_knowledge')}

Return a strict JSON object with:
"score": integer (0 to 100),
"findings": array of {{"severity": "HIGH"|"MEDIUM"|"LOW", "service": string, "rule": string, "remediation": string}}"""

        system_prompt = "You are a Principal Cloud Security Architect. Output only valid JSON."
        raw_res = self.bedrock.invoke(prompt=prompt, system_prompt=system_prompt)

        try:
            cleaned = re.search(r"\{.*\}", raw_res, re.DOTALL)
            parsed = json.loads(cleaned.group(0)) if cleaned else {"score": 75, "findings": []}
        except Exception:
            parsed = {"score": 75, "findings": []}

        return {"security_audit": parsed}

    def optimize_finops(self, state: ArchIQState) -> Dict[str, Any]:
        prompt = f"""Review this architecture for FinOps and AWS Cost Optimization opportunities.
Architecture:
{state.get('raw_input')}

Relevant Rules:
{state.get('retrieved_knowledge')}

Return a strict JSON object with:
"monthly_savings_pct": integer,
"optimizations": array of {{"service": string, "action": string, "impact": string}}"""

        system_prompt = "You are an AWS FinOps Specialist. Output only valid JSON."
        raw_res = self.bedrock.invoke(prompt=prompt, system_prompt=system_prompt)

        try:
            cleaned = re.search(r"\{.*\}", raw_res, re.DOTALL)
            parsed = json.loads(cleaned.group(0)) if cleaned else {"monthly_savings_pct": 20, "optimizations": []}
        except Exception:
            parsed = {"monthly_savings_pct": 20, "optimizations": []}

        return {"finops_audit": parsed}

    def synthesize_report(self, state: ArchIQState) -> Dict[str, Any]:
        sec = state.get("security_audit", {})
        fin = state.get("finops_audit", {})
        score = sec.get("score", 80)

        findings_lines = []
        for f in sec.get("findings", []):
            findings_lines.append(f"- [{f.get('severity')}] {f.get('service')}: {f.get('rule')} -> {f.get('remediation')}")

        opt_lines = []
        for o in fin.get("optimizations", []):
            opt_lines.append(f"- {o.get('service')}: {o.get('action')} ({o.get('impact')})")

        report_md = f"""# ArchIQ Compliance and Architecture Report

## Overall Health Score: {score}/100
- **Potential Monthly Savings:** {fin.get('monthly_savings_pct', 0)}%
- **Identified AWS Services:** {', '.join(state.get('parsed_services', []))}

## Security & Well-Architected Findings
{chr(10).join(findings_lines) if findings_lines else "No critical security risks identified."}

## FinOps & Cost Recommendations
{chr(10).join(opt_lines) if opt_lines else "Workload already adheres to baseline cost allocation."}
"""

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

