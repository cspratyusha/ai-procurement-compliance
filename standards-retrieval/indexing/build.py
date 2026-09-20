import argparse
import sys
import time
from pathlib import Path

# Ensure root directory is on Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_loader import load_corpus
from indexing.embed_index import build_index as build_dense_index
from indexing.bm25_index import build_index as build_bm25_index


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild the dense FAISS and sparse BM25 indices."
    )
    parser.add_argument(
        "--corpus",
        default=None,
        help=(
            "Path to the corpus JSON to index. Defaults to this package's "
            "data/mock_corpus.json. Use ../data/standards_corpus.json for the "
            "consolidated 45-standard corpus."
        ),
    )
    args = parser.parse_args()

    print("=" * 65)
    print("Building Dual Retrieval Indices (Dense FAISS + Sparse BM25)")
    print("=" * 65)

    corpus = load_corpus(args.corpus, force_reload=True)
    source = args.corpus or "data/mock_corpus.json (default)"
    print(f"Loaded {len(corpus)} standards from {source}.\n")

    # 1. Build Dense FAISS Vector Index
    print("--- [1/2] Building Dense FAISS Index ---")
    start_dense = time.time()
    build_dense_index(corpus)
    dense_elapsed = time.time() - start_dense
    print(f"Dense index complete in {dense_elapsed:.2f}s.\n")

    # 2. Build Sparse BM25 Lexical Index
    print("--- [2/2] Building Sparse BM25 Index ---")
    start_bm25 = time.time()
    build_bm25_index(corpus)
    bm25_elapsed = time.time() - start_bm25
    print(f"BM25 index complete in {bm25_elapsed:.2f}s.\n")

    total_elapsed = dense_elapsed + bm25_elapsed
    print("=" * 65)
    print(f"All indices built successfully for {len(corpus)} standards.")
    print(f"Total time elapsed: {total_elapsed:.2f}s")
    print("Artifacts generated in data/:")
    print("  - data/faiss.index")
    print("  - data/faiss_ids.json")
    print("  - data/bm25.pkl")
    print("  - data/bm25_ids.json")
    print("  - data/bm25_tokens.json")
    print("=" * 65)


if __name__ == "__main__":
    main()
