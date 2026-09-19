import logging
from typing import List
import numpy as np
from app.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
            logger.info(f"Loaded SentenceTransformer model '{settings.EMBEDDING_MODEL_NAME}'.")
        except Exception as e:
            logger.warning(f"Could not load SentenceTransformer model ({e}). Using hash vector fallback.")
            self.model = None

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate dense embeddings for a list of text strings."""
        if not texts:
            return []

        if self.model:
            embeddings = self.model.encode(texts, show_progress_bar=False)
            return embeddings.tolist()
        else:
            # Simple deterministic pseudo-vector fallback for testing environments without PyTorch/HuggingFace weights loaded
            logger.debug("Generating fallback pseudo-embeddings.")
            results = []
            for text in texts:
                np.random.seed(abs(hash(text)) % (2**32))
                vec = np.random.randn(384).astype(np.float32)
                vec /= np.linalg.norm(vec)
                results.append(vec.tolist())
            return results

    def embed_query(self, query: str) -> List[float]:
        """Generate vector embedding for a single search query string."""
        return self.embed_texts([query])[0]

embedding_service = EmbeddingService()
