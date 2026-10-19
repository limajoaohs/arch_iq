from typing import Dict, Any, List
from .bedrock import BedrockService


class AmazonQAssistant:
    def __init__(self, bedrock_service: BedrockService):
        self.bedrock = bedrock_service

    def generate_iac_remediation(self, original_iac: str, findings: List[Dict[str, Any]]) -> str:
        prompt = f"""Given this IaC template:
{original_iac}

Apply security and FinOps fixes for the following findings:
{findings}

Generate the updated, production-ready Terraform configuration:"""

        system_prompt = "You are Amazon Q Developer assistant specializing in AWS Infrastructure as Code and DevSecOps."
        return self.bedrock.invoke(prompt=prompt, system_prompt=system_prompt)

    def explain_finding(self, finding: Dict[str, Any]) -> str:
        prompt = f"Explain why this AWS architecture issue is critical and how to resolve it according to AWS best practices: {finding}"
        return self.bedrock.invoke(prompt=prompt)

