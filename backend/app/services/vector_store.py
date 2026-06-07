import time
from collections.abc import Sequence
from typing import Any

import chromadb

from app.core.config import settings


class VectorStoreError(RuntimeError):
    pass


class VectorStoreService:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection_name: str | None = None,
    ) -> None:
        if settings.vector_store_provider != "chroma":
            raise VectorStoreError(f"Unsupported vector store provider: {settings.vector_store_provider}")

        self.collection_name = collection_name or settings.chroma_collection_name
        self.client = chromadb.HttpClient(
            host=host or settings.chroma_host,
            port=port or settings.chroma_port,
        )

    def get_or_create_collection(self):
        return self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={
                "description": "NLP2SQL schema retrieval documents",
                "document_type": "schema_table",
            },
        )

    def upsert_documents(
        self,
        documents: Sequence[dict[str, Any]],
        embeddings: Sequence[Sequence[float]],
    ) -> int:
        document_list = list(documents)
        embedding_list = [list(embedding) for embedding in embeddings]

        if len(document_list) != len(embedding_list):
            raise ValueError("documents and embeddings must have the same length")

        if not document_list:
            return 0

        collection = self.get_or_create_collection()
        collection.upsert(
            ids=[document["id"] for document in document_list],
            documents=[document["content"] for document in document_list],
            embeddings=embedding_list,
            metadatas=[self._normalize_metadata(document.get("metadata", {})) for document in document_list],
        )
        return len(document_list)

    def similarity_search(
        self,
        query_embedding: Sequence[float],
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        collection = self.get_or_create_collection()
        results = collection.query(
            query_embeddings=[list(query_embedding)],
            n_results=top_k,
            where=where,
        )
        return self._format_query_results(results)

    def delete_collection(self) -> None:
        if not self._collection_exists():
            return
        self.client.delete_collection(name=self.collection_name)

    def reset_collection(self) -> None:
        self.delete_collection()
        self.get_or_create_collection()

    def count_documents(self) -> int:
        collection = self.get_or_create_collection()
        return int(collection.count())

    def _collection_exists(self) -> bool:
        collections = self.client.list_collections()
        return any((getattr(collection, "name", collection) == self.collection_name) for collection in collections)

    def _normalize_metadata(self, metadata: dict[str, Any] | None) -> dict[str, str | int | float | bool]:
        normalized: dict[str, str | int | float | bool] = {}
        for key, value in (metadata or {}).items():
            if value is None:
                normalized[key] = ""
            elif isinstance(value, (str, int, float, bool)):
                normalized[key] = value
            elif isinstance(value, list):
                normalized[key] = ", ".join(str(item) for item in value)
            else:
                normalized[key] = str(value)
        return normalized

    def _format_query_results(self, results: dict[str, Any]) -> list[dict[str, Any]]:
        formatted = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for index, document_id in enumerate(ids):
            formatted.append(
                {
                    "id": document_id,
                    "content": documents[index] if index < len(documents) else "",
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                    "distance": distances[index] if index < len(distances) else None,
                }
            )
        return formatted


def initialize_vector_store() -> None:
    last_error: Exception | None = None
    for _ in range(settings.vector_store_startup_retries):
        try:
            VectorStoreService().get_or_create_collection()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(settings.vector_store_startup_retry_delay_seconds)

    raise VectorStoreError("Vector store initialization failed") from last_error
