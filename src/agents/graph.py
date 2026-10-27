from typing import Dict, Any
from .state import ArchIQState
from .nodes import AgentNodes
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.rag.retriever import KnowledgeRetriever
from src.rag.store import VectorStore


class FallbackWorkflow:
    def __init__(self, nodes: AgentNodes):
        self.nodes = nodes

    def invoke(self, initial_state: ArchIQState) -> ArchIQState:
        state = dict(initial_state)
        state.update(self.nodes.parse_input(state))
        state.update(self.nodes.retrieve_context(state))
        state.update(self.nodes.audit_security(state))
        state.update(self.nodes.optimize_finops(state))
        state.update(self.nodes.synthesize_report(state))
        state.update(self.nodes.explain_for_layperson(state))
        return state


def create_arch_iq_graph(vector_store: VectorStore, bedrock_service: BedrockService, storage_service: StorageService):
    retriever = KnowledgeRetriever(vector_store)
    nodes = AgentNodes(bedrock=bedrock_service, retriever=retriever, storage=storage_service)

    try:
        from langgraph.graph import StateGraph, START, END

        workflow = StateGraph(ArchIQState)

        workflow.add_node("parse_input", nodes.parse_input)
        workflow.add_node("retrieve_context", nodes.retrieve_context)
        workflow.add_node("audit_security", nodes.audit_security)
        workflow.add_node("optimize_finops", nodes.optimize_finops)
        workflow.add_node("synthesize_report", nodes.synthesize_report)
        workflow.add_node("explain_for_layperson", nodes.explain_for_layperson)

        workflow.add_edge(START, "parse_input")
        workflow.add_edge("parse_input", "retrieve_context")
        workflow.add_edge("retrieve_context", "audit_security")
        workflow.add_edge("audit_security", "optimize_finops")
        workflow.add_edge("optimize_finops", "synthesize_report")
        workflow.add_edge("synthesize_report", "explain_for_layperson")
        workflow.add_edge("explain_for_layperson", END)

        return workflow.compile()
    except Exception:
        return FallbackWorkflow(nodes)

