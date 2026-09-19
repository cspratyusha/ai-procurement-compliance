import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.models.postgres_models import Base

logger = logging.getLogger(__name__)

# Determine database engine (PostgreSQL or fallback to SQLite if Postgres unavailable)
DATABASE_URL = settings.DATABASE_URL
engine = None

try:
    if DATABASE_URL.startswith("postgresql"):
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        # Test connection
        with engine.connect() as conn:
            logger.info("Successfully connected to PostgreSQL database.")
    else:
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
except Exception as e:
    logger.warning(f"Failed to connect to primary database ({DATABASE_URL}): {e}. Falling back to local SQLite database.")
    sqlite_url = "sqlite:///./procurement_compliance.db"
    engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Create all PostgreSQL / relational database tables, handling legacy schema migration gracefully."""
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        if "standards" in tables:
            columns = [col["name"] for col in inspector.get_columns("standards")]
            if "standard_number" not in columns:
                logger.warning(
                    "Legacy 'standards' table without 'standard_number' column detected. "
                    "Purging incompatible legacy tables for clean initialization..."
                )
                with engine.begin() as conn:
                    conn.execute(
                        text("DROP TABLE IF EXISTS audit_findings, interaction_logs, cross_references, amendments, certification_rules, standards, product_categories CASCADE;")
                    )
    except Exception as e:
        logger.warning(f"Database schema inspection notice: {e}")

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified and initialized successfully.")

def get_db():
    """FastAPI dependency for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
