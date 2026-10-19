from typing import List, Dict, Any
from .store import VectorStore


class KnowledgeRetriever:
    def __init__(self, vector_store: VectorStore):
        self.store = vector_store

    def retrieve_guidance(self, declared_services: List[str]) -> str:
        all_guidelines = []
        for service in declared_services:
            results = self.store.query(f"AWS {service} security cost best practice", top_k=2)
            for res in results:
                all_guidelines.append(res["text"])

        if not all_guidelines:
            general = self.store.query("AWS Well-Architected Framework high risk", top_k=3)
            all_guidelines = [g["text"] for g in general]

        return "\n".join(all_guidelines)

