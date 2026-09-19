import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "AI-Procurement-Compliance-API"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000

    # PostgreSQL Database URL
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://postgres:postgres@localhost:5432/procurement_compliance"
    )

    # Neo4j Graph Database Settings
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "password123")

    # Vector DB (ChromaDB) Settings
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")
    CHROMA_COLLECTION_NAME: str = "indian_standards"

    # BM25 Keyword Index Settings
    BM25_INDEX_DIR: str = os.getenv("BM25_INDEX_DIR", "./data/bm25_index")

    # Embedding Model Settings
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
