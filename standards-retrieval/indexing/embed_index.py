import json
from pathlib import Path
from typing import List, Tuple, Optional
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from data.models import Standard

# Global model cache and index cache
_MODEL_NAME = "intfloat/e5-base-v2"
_MODEL_INSTANCE: Optional[SentenceTransformer] = None
_CACHED_FAISS_INDEX: Optional[faiss.Index] = None
_CACHED_FAISS_IDS: Optional[List[str]] = None

_BASE_DIR = Path(__file__).resolve().parent.parent


# Resolved per call rather than at import, so STANDARDS_CORPUS is honoured
# even when it is set after this module is first imported (as in tests).
def _default_index_path() -> Path:
    from data_loader import index_dir
    return index_dir() / "faiss.index"


def _default_ids_path() -> Path:
    from data_loader import index_dir
    return index_dir() / "faiss_ids.json"


def get_embedding_model() -> SentenceTransformer:
    """Loads and caches the sentence-transformers model instance.
    
    Uses 'intfloat/e5-base-v2' (CPU-runnable, open-source).
    Cached globally so load time is incurred only once per process.
    """
    global _MODEL_INSTANCE
    if _MODEL_INSTANCE is None:
        print(f"[DenseRetrieval] Loading embedding model '{_MODEL_NAME}'...")
        _MODEL_INSTANCE = SentenceTransformer(_MODEL_NAME)
    return _MODEL_INSTANCE


def get_standard_embedding_text(standard: Standard) -> str:
    """Canonical text representation of a standard for dense embedding.
    
    Concatenates title + '. ' + scope + ' ' + description.
    Keep this single source of truth to avoid index/query construction drift.
    """
    return f"{standard.title}. {standard.scope} {standard.description}".strip()


def build_index(
    corpus: List[Standard],
    index_path: Optional[Path | str] = None,
    ids_path: Optional[Path | str] = None
) -> None:
    """Builds a FAISS dense vector index over a corpus of Standard objects.
    
    1. Formats each standard with the 'passage: ' prefix required by E5.
    2. Embeds all documents in a single batch.
    3. L2-normalizes vectors for exact cosine similarity via inner product.
    4. Constructs a faiss.IndexFlatIP.
    5. Saves index and parallel ID mapping list to disk.
    
    Args:
        corpus: List of Standard Pydantic objects.
        index_path: Target path for the FAISS index binary.
        ids_path: Target path for the ID mapping JSON.
    """
    global _CACHED_FAISS_INDEX, _CACHED_FAISS_IDS

    if not corpus:
        raise ValueError("Cannot build FAISS index from an empty corpus.")

    target_index_path = Path(index_path) if index_path else _default_index_path()
    target_ids_path = Path(ids_path) if ids_path else _default_ids_path()

    target_index_path.parent.mkdir(parents=True, exist_ok=True)
    target_ids_path.parent.mkdir(parents=True, exist_ok=True)

    # e5 models require 'passage: ' prefix on corpus documents
    passage_texts = [f"passage: {get_standard_embedding_text(std)}" for std in corpus]
    doc_ids = [std.id for std in corpus]

    model = get_embedding_model()
    print(f"[DenseRetrieval] Encoding {len(passage_texts)} documents in batch...")
    embeddings = model.encode(
        passage_texts,
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True
    )

    embeddings_np = np.ascontiguousarray(embeddings, dtype=np.float32)
    dim = embeddings_np.shape[1]

    # IndexFlatIP calculates inner product, which equals cosine similarity for L2-normalized vectors
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings_np)

    # Save index and ID mapping to disk
    faiss.write_index(index, str(target_index_path))
    with open(target_ids_path, "w", encoding="utf-8") as f:
        json.dump(doc_ids, f, indent=2)

    # Update in-memory cache
    _CACHED_FAISS_INDEX = index
    _CACHED_FAISS_IDS = doc_ids

    print(f"[DenseRetrieval] Index built with {index.ntotal} vectors (dim={dim}).")
    print(f"[DenseRetrieval] Saved to '{target_index_path}' and '{target_ids_path}'.")


def load_index(
    index_path: Optional[Path | str] = None,
    ids_path: Optional[Path | str] = None,
    force_reload: bool = False
) -> Tuple[faiss.Index, List[str]]:
    """Loads the FAISS index and parallel ID mapping from disk into memory.
    
    Raises:
        FileNotFoundError: If the index file or ID mapping file is missing.
        ValueError: If index size and ID mapping length do not match.
        
    Returns:
        Tuple of (faiss.Index, list of standard IDs).
    """
    global _CACHED_FAISS_INDEX, _CACHED_FAISS_IDS

    if _CACHED_FAISS_INDEX is not None and _CACHED_FAISS_IDS is not None and not force_reload:
        return _CACHED_FAISS_INDEX, _CACHED_FAISS_IDS

    target_index_path = Path(index_path) if index_path else _default_index_path()
    target_ids_path = Path(ids_path) if ids_path else _default_ids_path()

    if not target_index_path.exists():
        raise FileNotFoundError(
            f"FAISS index file not found at '{target_index_path}'. "
            "Run 'python -m indexing.build' or call 'build_index(corpus)' first."
        )

    if not target_ids_path.exists():
        raise FileNotFoundError(
            f"FAISS ID mapping file not found at '{target_ids_path}'. "
            "Run 'python -m indexing.build' or call 'build_index(corpus)' first."
        )

    index = faiss.read_index(str(target_index_path))
    with open(target_ids_path, "r", encoding="utf-8") as f:
        ids = json.load(f)

    if index.ntotal != len(ids):
        raise ValueError(
            f"Index corruption / mismatch: FAISS index contains {index.ntotal} vectors, "
            f"but ID mapping has {len(ids)} items."
        )

    _CACHED_FAISS_INDEX = index
    _CACHED_FAISS_IDS = ids
    return index, ids


def dense_search(
    query: str,
    top_k: int = 20,
    index_path: Optional[Path | str] = None,
    ids_path: Optional[Path | str] = None
) -> List[Tuple[str, float]]:
    """Performs semantic dense search using FAISS.
    
    1. Prefixes query with 'query: ' (required for E5 embeddings).
    2. Encodes and L2-normalizes the query vector.
    3. Queries FAISS index for top_k cosine similarity nearest neighbors.
    4. Returns list of (standard_id, cosine_score) sorted descending.
    
    Raises:
        FileNotFoundError / ValueError: If the index has not been built or is invalid.
    """
    if not query or not query.strip():
        return []

    index, ids = load_index(index_path=index_path, ids_path=ids_path)

    model = get_embedding_model()
    # e5 models expect 'query: ' prefix on queries
    query_text = f"query: {query.strip()}"
    query_emb = model.encode(
        [query_text],
        normalize_embeddings=True,
        show_progress_bar=False
    )
    query_emb_np = np.ascontiguousarray(query_emb, dtype=np.float32)

    k = min(top_k, index.ntotal)
    scores, indices = index.search(query_emb_np, k)

    results: List[Tuple[str, float]] = []
    for idx, score in zip(indices[0], scores[0]):
        if idx >= 0 and idx < len(ids):
            results.append((ids[idx], float(score)))

    return results
