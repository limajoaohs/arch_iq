import json
import os
from typing import List, Dict, Any, Optional
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from src.config import settings


class VectorStore:
    def __init__(self, persist_directory: Optional[str] = None):
        self.persist_directory = persist_directory or settings.chroma_persist_dir
        self.collection_name = "aws_well_architected"
        self._client = None
        self._collection = None
        self._memory_backup: List[Dict[str, Any]] = []
        self._bedrock_agent_runtime = None
        self._kb_id = settings.bedrock_kb_id

    def _init_chroma(self):
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            self._client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            self._collection = self._client.get_or_create_collection(name=self.collection_name)
        except Exception:
            self._client = None
            self._collection = None

    def seed_data(self, json_file_path: str):
        if not os.path.exists(json_file_path):
            return

        with open(json_file_path, "r", encoding="utf-8") as f:
            items = json.load(f)

        self._memory_backup = items

        self._init_chroma()
        if self._collection is not None and len(items) > 0:
            documents = []
            metadatas = []
            ids = []
            for item in items:
                text = f"Pillar: {item['pillar']} | Service: {item['service']} | Rule: {item['rule']} | Recommendation: {item['recommendation']}"
                documents.append(text)
                metadatas.append({"pillar": item["pillar"], "service": item["service"]})
                ids.append(item["id"])

            self._collection.upsert(documents=documents, metadatas=metadatas, ids=ids)

    def _get_bedrock_agent_runtime(self):
        if self._bedrock_agent_runtime is None:
            self._bedrock_agent_runtime = boto3.client(
                "bedrock-agent-runtime", region_name=settings.aws_region
            )
        return self._bedrock_agent_runtime

    def query_knowledge_base(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Consulta uma Bedrock Knowledge Base, se configurada."""
        if not self._kb_id:
            return []
        try:
            client = self._get_bedrock_agent_runtime()
            response = client.retrieve(
                knowledgeBaseId=self._kb_id,
                retrievalQuery={"text": query_text},
                numberOfResults=top_k,
            )
            results = []
            for item in response.get("retrievalResults", []):
                content = item.get("content", {})
                results.append({
                    "id": item.get("location", {}).get("s3Location", {}).get("uri", ""),
                    "text": content.get("text", ""),
                    "metadata": {"score": item.get("score", 0)},
                })
            return results
        except (BotoCoreError, ClientError):
            return []

    def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        # Tenta primeiro a Bedrock Knowledge Base (RAG gerenciado pela AWS)
        kb_results = self.query_knowledge_base(query_text, top_k=top_k)
        if kb_results:
            return kb_results

        # Fallback: Chroma local
        self._init_chroma()
        if self._collection is not None:
            try:
                results = self._collection.query(query_texts=[query_text], n_results=top_k)
                matched = []
                for i, doc in enumerate(results["documents"][0]):
                    matched.append({
                        "id": results["ids"][0][i],
                        "text": doc,
                        "metadata": results["metadatas"][0][i] if "metadatas" in results else {}
                    })
                return matched
            except Exception:
                pass

        query_lower = query_text.lower()
        scored = []
        for item in self._memory_backup:
            content = f"{item['service']} {item['rule']} {item['recommendation']}".lower()
            score = sum(1 for word in query_lower.split() if word in content)
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "id": x[1]["id"],
                "text": f"Pillar: {x[1]['pillar']} | Service: {x[1]['service']} | Rule: {x[1]['rule']}",
                "metadata": {"pillar": x[1]["pillar"], "service": x[1]["service"]}
            }
            for x in scored[:top_k]
        ]

