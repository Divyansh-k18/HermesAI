"""Tells the interface whether AI steps can run. Never returns the key."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app import ai
from app.deps import CurrentAuth, get_current_auth

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


class AIStatus(BaseModel):
    configured: bool
    model: str | None
    provider: str | None


@router.get("/status", response_model=AIStatus)
def ai_status(request: Request, _auth: CurrentAuth = Depends(get_current_auth)) -> AIStatus:
    settings = request.app.state.settings
    configured = ai.is_configured(settings)
    return AIStatus(
        configured=configured,
        model=settings.ai_model if configured else None,
        provider=ai.provider_host(settings) if configured else None,
    )
