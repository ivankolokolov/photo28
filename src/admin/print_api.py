"""HTTP Print API для локального агента печати (аутентификация по Bearer-токену)."""
from fastapi import APIRouter, Request, HTTPException, Body

from src.database import async_session
from src.models.print_agent import PrintAgent
from src.models.order import OrderStatus
from src.services.print_agent_service import PrintAgentService
from src.services.order_service import OrderService
from src.services.product_service import ProductService

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


@print_router.get("/jobs")
async def jobs(request: Request):
    async with async_session() as session:
        agent = await resolve_agent(request, session)
        sid = agent.studio_id
        await ProductService(session).load_cache(sid)
        orders = await OrderService(session, sid).get_orders_by_status(OrderStatus.CONFIRMED)
        result = []
        for order in orders:
            photos = []
            for p in sorted(order.photos, key=lambda x: x.position):
                prod = ProductService.get_product(sid, p.product_id)
                photos.append({
                    "photo_id": p.id,
                    "product_slug": prod.slug if prod else None,
                    "aspect_ratio": prod.aspect_ratio if prod else None,
                    "crop_data": p.crop_data,
                    "position": p.position,
                })
            result.append({"order_id": order.id, "order_number": order.order_number, "photos": photos})
    return {"jobs": result}
