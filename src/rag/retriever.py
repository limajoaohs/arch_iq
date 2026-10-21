from typing import List, Dict, Any
from .store import VectorStore


class KnowledgeRetriever:
    def __init__(self, vector_store: VectorStore):
        self.store = vector_store

    def retrieve_guidance(self, declared_services: List[str]) -> str:
        all_guidelines = []
        has_security_group = "SECURITY_GROUP" in declared_services

        for service in declared_services:
            # Se for Security Group e o usuário NÃO declarou, pulamos (evitar findings falsos)
            if service == "SECURITY_GROUP" and not has_security_group:
                continue

            results = self.store.query(f"AWS {service} security cost best practice", top_k=2)
            for res in results:
                all_guidelines.append(res["text"])

        # Se ninguém declarou Security Group, também removemos guidelines gerais de risco alto
        # que mencionam SG ou portas SSH não declaradas
        if not has_security_group:
            filtered = []
            for g in all_guidelines:
                text_lower = g.lower()
                # Filtra regras que mencionam SSH 0.0.0.0/0 ou portas não declaradas
                if "unrestricted ingress" in text_lower or "0.0.0.0/0" in text_lower:
                    continue
                filtered.append(g)
            all_guidelines = filtered

        return "\n".join(all_guidelines) if all_guidelines else ""

