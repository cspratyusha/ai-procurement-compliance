import os
import json
import logging
import re
from typing import List, Dict, Any, Tuple
from rank_bm25 import BM25Okapi
from app.config import settings

logger = logging.getLogger(__name__)

class BM25IndexClient:
    def __init__(self):
        self.bm25: BM25Okapi = None
        self.doc_ids: List[str] = []
        self.documents: List[Dict[str, Any]] = []
        self.corpus_tokens: List[List[str]] = []
        self._load_from_disk()

    def _tokenize(self, text: str) -> List[str]:
        """Simple, effective technical term & IS-number tokenizer."""
        clean_text = text.lower()
        # Keep alphanumeric, hyphenated words, and standard numbers
        tokens = re.findall(r'\b[a-z0-9\-]+\b', clean_text)
        return tokens

    def build_index(self, doc_records: List[Dict[str, Any]]):
        """
        doc_records: List of dicts with:
        {"standard_number": str, "title": str, "scope_text": str, "abstract": str}
        """
        self.doc_ids = []
        self.documents = []
        self.corpus_tokens = []

        for doc in doc_records:
            full_text = f"{doc.get('standard_number', '')} {doc.get('title', '')} {doc.get('scope_text', '')} {doc.get('abstract', '')}"
            tokens = self._tokenize(full_text)
            self.doc_ids.append(doc["standard_number"])
            self.documents.append(doc)
            self.corpus_tokens.append(tokens)

        if self.corpus_tokens:
            self.bm25 = BM25Okapi(self.corpus_tokens)
            self._save_to_disk()
            logger.info(f"Built BM25 keyword index over {len(self.doc_ids)} standards.")

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Return list of (standard_number, bm25_score, document_metadata)."""
        if not self.bm25 or not self.doc_ids:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores = self.bm25.get_scores(query_tokens)
        scored_docs = list(zip(self.doc_ids, scores, self.documents))
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        return [(doc_id, score, doc) for doc_id, score, doc in scored_docs[:top_k] if score > 0]

    def _save_to_disk(self):
        try:
            os.makedirs(settings.BM25_INDEX_DIR, exist_ok=True)
            path = os.path.join(settings.BM25_INDEX_DIR, "bm25_data.json")
            data = {
                "doc_ids": self.doc_ids,
                "documents": self.documents,
                "corpus_tokens": self.corpus_tokens
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist BM25 index to disk: {e}")

    def _load_from_disk(self):
        path = os.path.join(settings.BM25_INDEX_DIR, "bm25_data.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.doc_ids = data.get("doc_ids", [])
                    self.documents = data.get("documents", [])
                    self.corpus_tokens = data.get("corpus_tokens", [])
                    if self.corpus_tokens:
                        self.bm25 = BM25Okapi(self.corpus_tokens)
                        logger.info(f"Loaded existing BM25 index with {len(self.doc_ids)} documents.")
            except Exception as e:
                logger.warning(f"Could not load saved BM25 index: {e}")

    def count(self) -> int:
        return len(self.doc_ids)

    def clear(self):
        self.bm25 = None
        self.doc_ids = []
        self.documents = []
        self.corpus_tokens = []
        path = os.path.join(settings.BM25_INDEX_DIR, "bm25_data.json")
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

bm25_index_client = BM25IndexClient()
