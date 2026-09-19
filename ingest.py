#!/usr/bin/env python3
import sys
import os
import json
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger(__name__)

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import init_db, SessionLocal
from app.schemas.ingestion import BatchIngestRequest
from app.services.ingestion_service import IngestionService

def main():
    parser = argparse.ArgumentParser(description="Ingest Indian Standards data into PostgreSQL, Neo4j, Vector DB, and BM25 index.")
    parser.add_argument("--file", "-f", default="data/seed_standards.json", help="Path to JSON seed file (default: data/seed_standards.json)")
    parser.add_argument("--rebuild", "-r", action="store_true", help="Rebuild derived stores directly from PostgreSQL")

    args = parser.parse_args()

    # Initialize DB schema
    init_db()

    db = SessionLocal()
    try:
        if args.rebuild:
            logger.info("Executing derived stores rebuild routine from PostgreSQL...")
            result = IngestionService.rebuild_derived_stores(db)
            logger.info(f"Rebuild completed: {json.dumps(result, indent=2)}")
        else:
            file_path = os.path.abspath(args.file)
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                sys.exit(1)

            logger.info(f"Reading standards batch from '{file_path}'...")
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            batch = BatchIngestRequest(**data)
            logger.info(f"Starting fan-out ingestion of {len(batch.standards)} standards...")
            res = IngestionService.ingest_batch(db, batch)
            logger.info("Ingestion completed successfully!")
            logger.info(f"Status: {res.status}")
            logger.info(f"PostgreSQL insertions: {json.dumps(res.postgres_inserted)}")
            logger.info(f"Vector DB count: {res.vector_db_indexed_count}")
            logger.info(f"BM25 Indexed count: {res.bm25_indexed_count}")

            # Print corpus stats
            stats = IngestionService.get_ingestion_stats(db)
            logger.info(f"Current Corpus Stats: {json.dumps(stats.model_dump(), indent=2)}")

    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
