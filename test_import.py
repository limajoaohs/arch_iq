import sys
sys.path.insert(0, '.')
from src.agents.nodes import AgentNodes
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.rag.store import VectorStore
from src.rag.retriever import KnowledgeRetriever

nodes = AgentNodes(
    bedrock=BedrockService(),
    retriever=KnowledgeRetriever(VectorStore(persist_directory='./chroma_data')),
    storage=StorageService()
)

# Teste parse
result = nodes.parse_input({'raw_input': 'resource "aws_instance" "app" { instance_type = "t3.medium" }'})
print('parse_input OK:', result)

# Teste retrieve
ctx = nodes.retrieve_context({'raw_input': 'resource "aws_instance" "app" { instance_type = "t3.medium" }', 'parsed_services': ['EC2']})
print('retrieve_context OK, knowledge length:', len(ctx['retrieved_knowledge']))