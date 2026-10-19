import json
import os
from typing import List, Dict, Any, Optional
from src.config import settings


class VectorStore:
    def __init__(self, persist_directory: Optional[str] = None):
        self.persist_directory = persist_directory or settings.chroma_persist_dir
        self.collection_name = "aws_well_architected"
        self._client = None
        self._collection = None
        self._memory_backup: List[Dict[str, Any]] = []

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

    def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
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

