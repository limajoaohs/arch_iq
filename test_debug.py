import sys
sys.path.insert(0, '.')
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.rag.store import VectorStore
from src.rag.retriever import KnowledgeRetriever
from src.agents.graph import create_arch_iq_graph
from src.agents.nodes import AgentNodes
from src.agents.state import ArchIQState

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
    'session_id': 'test-debug',
    'raw_input': test_input
}

# Let's manually trace through the graph
from src.agents.nodes import AgentNodes
from src.agents.state import ArchIQState

nodes = AgentNodes(
    bedrock=bedrock,
    retriever=KnowledgeRetriever(VectorStore(persist_directory='./chroma_data')),
    storage=StorageService()
)

# Test parse_input
parsed = nodes.parse_input(state)
print('parsed_services:', parsed['parsed_services'])

# Test retrieve_context
ctx = nodes.retrieve_context(state)
print('retrieved_knowledge length:', len(ctx['retrieved_knowledge']))
print('retrieved_knowledge first 200 chars:', str(ctx['retrieved_knowledge'])[:200])

# Now test the full graph
final_state = graph.invoke(state)
print('Score:', final_state.get('score'))
audit = final_state.get('security_audit', {})
if audit:
    findings = audit.get('findings', [])
    print('Findings:', findings)
else:
    print('No security_audit')