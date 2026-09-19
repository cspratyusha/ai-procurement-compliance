import os
import logging
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from app.config import settings

logger = logging.getLogger(__name__)

class VectorStoreClient:
    def __init__(self):
        self.client = None
        self.collection = None
        self._init_chroma()

    def _init_chroma(self):
        try:
            os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
            self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
            self.collection = self.client.get_or_create_collection(
                name=settings.CHROMA_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Initialized ChromaDB vector store at '{settings.CHROMA_PERSIST_DIR}'.")
        except Exception as e:
            logger.warning(f"Failed to initialize persistent ChromaDB ({e}). Initializing in-memory ChromaDB.")
            self.client = chromadb.Client()
            self.collection = self.client.get_or_create_collection(
                name=settings.CHROMA_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )

    def upsert_embeddings(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]]
    ):
        """Upsert documents, vectors, and metadata into vector store."""
        if not ids:
            return
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 10,
        where_filter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Perform dense vector search with optional metadata filtering."""
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter
        )

    def count(self) -> int:
        """Return total number of vector records in collection."""
        return self.collection.count()

    def clear(self):
        """Purge vector collection."""
        try:
            self.client.delete_collection(name=settings.CHROMA_COLLECTION_NAME)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )

vector_store_client = VectorStoreClient()
