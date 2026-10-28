import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.rag.store import VectorStore
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.agents.graph import create_arch_iq_graph
from src.agents.nodes import AgentNodes
from src.rag.retriever import KnowledgeRetriever


@pytest.fixture
def test_vector_store(tmp_path):
    store = VectorStore(persist_directory=str(tmp_path / "chroma"))
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "well_architected.json")
    store.seed_data(os.path.abspath(data_path))
    return store


def test_vector_store_query(test_vector_store):
    results = test_vector_store.query("S3 bucket public", top_k=2)
    assert len(results) > 0
    assert any("S3" in r["text"] for r in results)


def test_agent_nodes_parse_input():
    nodes = AgentNodes(
        bedrock=BedrockService(),
        retriever=KnowledgeRetriever(VectorStore()),
        storage=StorageService()
    )
    state = {"raw_input": "resource \"aws_s3_bucket\" \"logs\" {}\nresource \"aws_instance\" \"web\" {}"}
    result = nodes.parse_input(state)
    assert "S3" in result["parsed_services"]
    assert "EC2" in result["parsed_services"]


def test_graph_end_to_end_flow(test_vector_store):
    bedrock = BedrockService()
    storage = StorageService()
    graph = create_arch_iq_graph(test_vector_store, bedrock, storage)

    test_input = """
    resource "aws_security_group" "allow_all" {
      ingress {
        from_port   = 22
        to_port     = 22
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
      }
    }
    resource "aws_instance" "app" {
      instance_type = "t3.medium"
    }
    """

    state = {
        "session_id": "test-session-123",
        "raw_input": test_input
    }

    final_state = graph.invoke(state)
    assert "score" in final_state
    assert "final_report" in final_state
    assert "remediated_iac" in final_state
    assert "SECURITY_GROUP" in final_state.get("parsed_services", [])



class ThrottledBedrock(BedrockService):
    def invoke(self, *args, **kwargs):
        from botocore.exceptions import ClientError
        raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "Too many tokens per day"}}, "Converse")


def test_graph_uses_deterministic_fallback_when_bedrock_fails(test_vector_store):
    graph = create_arch_iq_graph(test_vector_store, ThrottledBedrock(), StorageService())
    final_state = graph.invoke({
        "session_id": "test-throttled",
        "raw_input": 'resource "aws_s3_bucket" "logs" { acl = "public-read" }',
    })
    explanation = final_state["layperson_explanation"]
    assert not explanation.lstrip().startswith("{")
    assert f"{final_state['score']} de 100" in explanation
    assert final_state["remediated_iac"] == ""
