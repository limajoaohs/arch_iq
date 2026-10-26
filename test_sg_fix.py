import sys
sys.path.insert(0, '.')
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.rag.store import VectorStore
from src.agents.graph import create_arch_iq_graph

# Teste 1: Apenas EC2 (sem Security Group)
print('=== TESTE 1: Apenas EC2 (sem SG) ===')
vector_store = VectorStore(persist_directory='./chroma_data')
data_path = 'data/well_architected.json'
vector_store.seed_data(data_path)

bedrock = BedrockService()
storage = StorageService()
graph = create_arch_iq_graph(vector_store, bedrock, storage)

test_input = """resource "aws_instance" "app" {
  instance_type = "t3.medium"
}"""

state = {
    'session_id': 'test-sg-fix',
    'raw_input': test_input
}

final_state = graph.invoke(state)
print('Score:', final_state.get('score'))
print('Services:', final_state.get('parsed_services'))
audit = final_state.get('security_audit', {})
if audit:
    findings = audit.get('findings', [])
    print('Findings count:', len(findings))
    for f in findings[:3]:
        print(f"  - {f.get('severity')}: {f.get('service')}: {f.get('rule')[:60]}")
else:
    print('Nenhum security_audit')
print('Final report preview:', str(final_state.get('final_report', '')[:100]))
print()

# Teste 2: EC2 + Security Group (deve mostrar o finding de SG)
print('=== TESTE 2: EC2 + Security Group (com SG) ===')
test_input2 = """resource "aws_instance" "app" {
  instance_type = "t3.medium"
}
resource "aws_security_group" "web" {
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}"""

state2 = {
    'session_id': 'test-sg-fix-2',
    'raw_input': test_input2
}

final_state2 = graph.invoke(state2)
print('Score:', final_state2.get('score'))
print('Services:', final_state2.get('parsed_services'))
audit2 = final_state2.get('security_audit', {})
if audit2:
    findings2 = audit2.get('findings', [])
    print('Findings count:', len(findings2))
    for f in findings2[:3]:
        print(f"  - {f.get('severity')}: {f.get('service')}: {f.get('rule')[:60]}")
print('Final report preview:', str(final_state2.get('final_report', '')[:100]))