from fastapi import APIRouter

from app.api.v1.endpoints import auth
from app.api.v1.endpoints import query
from app.api.v1.endpoints import audit

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(query.router)
api_router.include_router(audit.router)