"""HTTP Print API для локального агента печати (аутентификация по Bearer-токену)."""
from fastapi import APIRouter, Request, HTTPException, Body

from src.database import async_session
from src.models.print_agent import PrintAgent
from src.services.print_agent_service import PrintAgentService

print_router = APIRouter(prefix="/api/print")


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "") or request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


async def resolve_agent(request: Request, session) -> PrintAgent:
    token = _bearer(request)
    agent = await PrintAgentService(session).authenticate(token)
    if agent is None:
        raise HTTPException(status_code=401, detail="Неверный токен агента")
    return agent


@print_router.post("/pair")
async def pair(request: Request, payload: dict = Body(...)):
    code = (payload or {}).get("code", "")
    async with async_session() as session:
        result = await PrintAgentService(session).pair(code)
    if result is None:
        raise HTTPException(status_code=404, detail="Код не найден")
    _agent, raw = result
    return {"token": raw}
