import sys
sys.path.insert(0, '.')
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.rag.store import VectorStore
from src.agents.graph import create_arch_iq_graph
from src.agents.nodes import AgentNodes

# Teste direto com Bedrock
print('=== TESTE DIRETO COM BEDROCK ===')
bedrock = BedrockService()

test_input = """resource "aws_instance" "app" {
  instance_type = "t3.medium"
}"""

parsed_services = ['EC2']
has_sg = 'SECURITY_GROUP' in parsed_services

# Try different prompt approaches
prompt1 = f"""**INSTRUCTION: This architecture has NO Security Group resources. Do NOT generate any findings about SSH ingress, port 22, or Security Group misconfigurations. If you were about to mention them, skip them entirely.**

Evaluate this architecture for security risks:
{test_input}

Based on the above, return JSON with "score" (0-100) and "findings" array. Each finding needs: "severity", "service", "rule", "remediation".

Return ONLY the JSON, no text before or after."""

print('Prompt 1 (instruction at start):')
raw = bedrock.invoke(prompt=prompt1, system_prompt="You are a Principal Cloud Security Architect. Output only valid JSON.")
print('Raw response:', raw[:200])
print()

# Try without the architecture context at all, just the instruction
prompt2 = """**INSTRUCTION: Do NOT generate findings about Security Groups, SSH port 22, or 0.0.0.0/0 access. Focus on other security aspects.**

Return JSON: "score" and "findings" array. Each finding: "severity", "service", "rule", "remediation".

Return ONLY the JSON."""

print('Prompt 2 (instruction only, no architecture):')
raw2 = bedrock.invoke(prompt=prompt2, system_prompt="You are a Principal Cloud Security Architect. Output only valid JSON.")
print('Raw response:', raw2[:200])