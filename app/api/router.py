from fastapi import APIRouter
from app.api.endpoints import health, ingest, search, standards

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(ingest.router)
api_router.include_router(search.router)
api_router.include_router(standards.router)
