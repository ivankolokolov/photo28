"""HTTP Print API для локального агента печати (аутентификация по Bearer-токену)."""
import io
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from aiogram import Bot

from src.database import async_session
from src.models.billing_event import BillingEvent
from src.models.print_agent import PrintAgent
from src.models.order import Order, OrderStatus
from src.models.photo import Photo
from src.models.studio import Studio
from src.services.print_agent_service import PrintAgentService
from src.services.order_service import OrderService
from src.services.product_service import ProductService
from src.services.crypto import decrypt_secret

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


@print_router.get("/photo/{photo_id}")
async def photo(request: Request, photo_id: int):
    async with async_session() as session:
        agent = await resolve_agent(request, session)
        row = (await session.execute(
            select(Photo, Studio)
            .join(Order, Photo.order_id == Order.id)
            .join(Studio, Order.studio_id == Studio.id)
            .where(Photo.id == photo_id, Order.studio_id == agent.studio_id)
        )).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Фото не найдено")
        photo_obj, studio = row
        if not studio.bot_token:
            raise HTTPException(status_code=409, detail="У студии нет токена бота")
        bot = Bot(token=decrypt_secret(studio.bot_token))
        try:
            f = await bot.get_file(photo_obj.telegram_file_id)
            data = await bot.download_file(f.file_path)
        finally:
            await bot.session.close()
    return StreamingResponse(io.BytesIO(data.read()), media_type="image/jpeg")


@print_router.post("/health")
async def health(request: Request, payload: dict = Body(...)):
    async with async_session() as session:
        agent = await resolve_agent(request, session)
        agent.printer_status = str((payload or {}).get("printer_status", ""))[:255]
        agent.queue_len = int((payload or {}).get("queue_len", 0) or 0)
        agent.last_seen_at = datetime.now()
        await session.commit()
    return {"ok": True}


@print_router.post("/report")
async def report(request: Request, payload: dict = Body(...)):
    order_id = (payload or {}).get("order_id")
    printed_ids = set((payload or {}).get("printed_photo_ids") or [])
    async with async_session() as session:
        agent = await resolve_agent(request, session)
        sid = agent.studio_id
        order_svc = OrderService(session, sid)
        order = await order_svc.get_order_by_id(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        studio = (await session.execute(
            select(Studio).where(Studio.id == sid))).scalar_one()
        # уже оттарифицированные позиции этого заказа
        billed_positions = set((await session.execute(
            select(BillingEvent.photo_position).where(BillingEvent.order_id == order.id)
        )).scalars().all())
        billed = 0
        for p in order.photos:
            if p.id in printed_ids and p.position not in billed_positions:
                session.add(BillingEvent(
                    studio_id=sid, order_id=order.id, photo_position=p.position,
                    fee=studio.platform_fee_per_photo, printed_at=datetime.now(),
                ))
                billed_positions.add(p.position)
                billed += 1
        # Статус двигаем только если по заказу есть оттарифицированные позиции,
        # иначе пустой/no-op рапорт не должен уводить CONFIRMED в PRINTING.
        if billed_positions:
            total_positions = {p.position for p in order.photos}
            new_status = OrderStatus.READY if billed_positions >= total_positions else OrderStatus.PRINTING
            await order_svc.update_order_status(order, new_status)
        await session.commit()
    return {"billed": billed}
