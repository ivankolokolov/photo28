"""FastAPI приложение для админ-панели."""
import json
import time
import hashlib
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import FastAPI, Depends, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.config import settings
from src.database import async_session
from src.services.order_service import OrderService
from src.services.file_service import FileService
from src.services.yandex_disk import YandexDiskService
from src.services.settings_service import SettingsService, SettingKeys
from src.services.analytics_service import AnalyticsService
from src.services.product_service import ProductService
from src.services.studio_provisioning import provision_studio
from src.models.order import Order, OrderStatus
from src.models.photo import Photo
from src.models.studio import Studio
from src.admin.auth import authenticate, current_admin, effective_studio_id, require_super_admin, require_studio
from src.services.crypto import decrypt_secret


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Кеши настроек/товаров грузятся пер-студийно в роутах (per-request), не глобально."""
    yield


# Создаём приложение
app = FastAPI(title="Photo28 Admin", docs_url=None, redoc_url=None, lifespan=_lifespan)


# === Security Middleware: заголовки безопасности ===

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Сессии для авторизации (secret_key из .env, HTTPS-only cookie)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.admin_secret_key,
    https_only=True,
    same_site="lax",
)


# === Rate Limiting для логина ===

_login_attempts: dict = defaultdict(list)  # {ip: [timestamp, ...]}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300  # 5 минут


def _check_rate_limit(ip: str) -> bool:
    """Возвращает True если лимит НЕ превышен."""
    now = time.time()
    # Удаляем старые попытки
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < LOGIN_WINDOW_SECONDS]
    return len(_login_attempts[ip]) < MAX_LOGIN_ATTEMPTS


def _record_login_attempt(ip: str):
    """Записывает попытку логина."""
    _login_attempts[ip].append(time.time())


# === API-токен для Mini App ===

def generate_api_token(order_id: int) -> str:
    """Генерирует токен для доступа к API заказа."""
    raw = f"{order_id}:{settings.admin_secret_key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def verify_api_token(order_id: int, token: str) -> bool:
    """Проверяет токен доступа к API."""
    expected = generate_api_token(order_id)
    return secrets.compare_digest(token, expected)

# Статика и шаблоны
BASE_DIR = Path(__file__).parent
PROJECT_DIR = BASE_DIR.parent.parent  # корень проекта
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Mini App статика (css, js)
WEBAPP_DIR = PROJECT_DIR / "docs"
app.mount("/webapp/css", StaticFiles(directory=WEBAPP_DIR / "css"), name="webapp_css")
app.mount("/webapp/js", StaticFiles(directory=WEBAPP_DIR / "js"), name="webapp_js")

templates = Jinja2Templates(directory=BASE_DIR / "templates")


def base_context(request: Request, **extra) -> dict:
    """Базовый контекст для всех TemplateResponse: admin + active_studio_name."""
    admin = current_admin(request)
    active_name = extra.pop("active_studio_name", None)
    return {"request": request, "admin": admin, "active_studio_name": active_name, **extra}


def check_auth(request: Request) -> bool:
    """Проверяет авторизацию (новая сессия на базе AdminUser)."""
    return bool(request.session.get("user_id"))


async def require_auth(request: Request):
    """Требует авторизации."""
    if not check_auth(request):
        raise HTTPException(status_code=303, headers={"Location": "/login"})


# === Авторизация ===

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse(request, "login.html", {"error": error})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    client_ip = request.client.host if request.client else "unknown"
    
    # Rate limiting
    if not _check_rate_limit(client_ip):
        return RedirectResponse("/login?error=rate_limit", status_code=303)
    
    async with async_session() as session:
        admin = await authenticate(session, username, password)

    if admin:
        request.session["user_id"] = admin.id
        request.session["username"] = admin.username
        request.session["role"] = admin.role.value
        request.session["studio_id"] = admin.studio_id
        # Очищаем попытки при успешном входе
        _login_attempts.pop(client_ip, None)
        return RedirectResponse("/", status_code=303)

    _record_login_attempt(client_ip)
    return RedirectResponse("/login?error=invalid", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# === Главная страница ===

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    studio_id = require_studio(request)

    async with async_session() as session:
        service = OrderService(session, studio_id)
        all_orders = await service.get_all_orders(limit=1000)

        stats = {
            "total_orders": len(all_orders),
            "pending_payment": len([o for o in all_orders if o.status == OrderStatus.PENDING_PAYMENT]),
            "paid": len([o for o in all_orders if o.status == OrderStatus.PAID]),
            "confirmed": len([o for o in all_orders if o.status == OrderStatus.CONFIRMED]),
            "printing": len([o for o in all_orders if o.status == OrderStatus.PRINTING]),
            "shipped": len([o for o in all_orders if o.status == OrderStatus.SHIPPED]),
        }

        recent_orders = await service.get_all_orders(limit=10)

    file_service = FileService(settings.bot_token)
    storage_stats = file_service.get_storage_stats(studio_id)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        base_context(request, stats=stats, orders=recent_orders, storage=storage_stats),
    )


# === Список заказов ===

@app.get("/orders", response_class=HTMLResponse)
async def orders_list(
    request: Request,
    status: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = Query(default=1, ge=1),
):
    studio_id = require_studio(request)

    per_page = 20
    offset = (page - 1) * per_page

    date_from_dt = None
    date_to_dt = None

    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            pass

    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, "%Y-%m-%d")
        except ValueError:
            pass

    status_enum = None
    if status:
        try:
            status_enum = OrderStatus(status)
        except ValueError:
            pass

    async with async_session() as session:
        service = OrderService(session, studio_id)
        orders, total_count = await service.search_orders(
            search=search, status=status_enum,
            date_from=date_from_dt, date_to=date_to_dt,
            limit=per_page, offset=offset,
        )

    total_pages = (total_count + per_page - 1) // per_page

    return templates.TemplateResponse(
        request,
        "orders.html",
        base_context(
            request,
            orders=orders,
            current_status=status, search=search or "",
            date_from=date_from or "", date_to=date_to or "",
            page=page, total_pages=total_pages,
            total_count=total_count, statuses=OrderStatus,
        ),
    )


# === Детали заказа ===

@app.get("/orders/{order_id}", response_class=HTMLResponse)
async def order_detail(request: Request, order_id: int):
    studio_id = require_studio(request)

    async with async_session() as session:
        await SettingsService(session).load_cache(studio_id)
        await ProductService(session).load_cache(studio_id)

        service = OrderService(session, studio_id)
        order = await service.get_order_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")

        # Resolve product display names server-side
        photos_by_product = order.photos_by_product()
        photos_info = []
        for pid, count in photos_by_product.items():
            product = ProductService.get_product(studio_id, pid)
            name = product.short_name if product else f"Товар #{pid}"
            photos_info.append({"name": name, "count": count})

    return templates.TemplateResponse(
        request,
        "order_detail.html",
        base_context(request, order=order, statuses=OrderStatus, photos_by_product=photos_info),
    )


# === Изменение статуса ===

async def send_client_notification(order, new_status: str, studio_id: int):
    from aiogram import Bot
    from sqlalchemy import select as _select
    from src.services.notification_service import NotificationService
    from src.bot.context import SettingsFacade, ProductsFacade
    try:
        async with async_session() as session:
            result = await session.execute(_select(Studio).where(Studio.id == studio_id))
            studio = result.scalar_one_or_none()
            if not studio or not studio.bot_token:
                import logging
                logging.warning("send_client_notification: studio %s not found or no bot_token", studio_id)
                return
        bot_token = decrypt_secret(studio.bot_token)
        bot = Bot(token=bot_token)
        notification_service = NotificationService(
            bot,
            studio,
            SettingsFacade(studio_id),
            ProductsFacade(studio_id),
        )
        await notification_service.notify_client_status_changed(order, new_status)
        await bot.session.close()
    except Exception as e:
        import logging
        logging.error(f"Ошибка отправки уведомления клиенту: {e}")


@app.post("/orders/{order_id}/status")
async def update_order_status(
    request: Request, order_id: int,
    status: str = Form(...), notify_client: bool = Form(default=True),
):
    studio_id = require_studio(request)

    async with async_session() as session:
        service = OrderService(session, studio_id)
        order = await service.get_order_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")

        old_status = order.status.value
        try:
            new_status = OrderStatus(status)
            await service.update_order_status(order, new_status)
            if notify_client and old_status != status:
                order = await service.get_order_by_id(order_id)
                await send_client_notification(order, status, studio_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный статус")

    return RedirectResponse(f"/orders/{order_id}", status_code=303)


# === Скачивание фотографий ===

@app.get("/orders/{order_id}/download")
async def download_order_photos(request: Request, order_id: int):
    studio_id = require_studio(request)

    async with async_session() as session:
        service = OrderService(session, studio_id)
        order = await service.get_order_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")

    file_service = FileService(settings.bot_token)
    try:
        await file_service.download_all_order_photos(order)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка скачивания: {e}")

    return RedirectResponse(f"/orders/{order_id}?downloaded=1", status_code=303)


# === Загрузка на Яндекс.Диск ===

@app.post("/orders/{order_id}/upload-yandex")
async def upload_to_yandex(request: Request, order_id: int):
    studio_id = require_studio(request)

    async with async_session() as session:
        service = OrderService(session, studio_id)
        order = await service.get_order_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")

    file_service = FileService(settings.bot_token)
    order_dir = file_service.get_order_dir(order)

    if not order_dir.exists() or not list(order_dir.glob("*.*")):
        raise HTTPException(status_code=400, detail="Сначала скачайте фото из Telegram")

    yandex_service = YandexDiskService()
    try:
        await yandex_service.upload_order_photos(order, order_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {e}")
    finally:
        await yandex_service.close()

    return RedirectResponse(f"/orders/{order_id}?uploaded=1", status_code=303)


# === Просмотр локальных фото ===

@app.get("/orders/{order_id}/photos")
async def list_order_photos(request: Request, order_id: int):
    studio_id = require_studio(request)

    async with async_session() as session:
        service = OrderService(session, studio_id)
        order = await service.get_order_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")

    file_service = FileService(settings.bot_token)
    photos = file_service.get_order_photos_paths(order)

    return templates.TemplateResponse(
        "photos.html",
        {"request": request, "order": order, "photos": photos},
    )


@app.get("/storage/{order_number}/{filename}")
async def serve_photo(request: Request, order_number: str, filename: str):
    if not check_auth(request):
        raise HTTPException(status_code=403)
    file_path = settings.photos_dir / order_number / filename
    if not file_path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(file_path)


# === Промокоды ===

@app.get("/promocodes", response_class=HTMLResponse)
async def promocodes_list(request: Request):
    studio_id = require_studio(request)
    async with async_session() as session:
        from sqlalchemy import select
        from src.models.promocode import Promocode
        result = await session.execute(
            select(Promocode)
            .where(Promocode.studio_id == studio_id)
            .order_by(Promocode.created_at.desc())
        )
        promocodes = result.scalars().all()
    return templates.TemplateResponse(request, "promocodes.html", base_context(request, promocodes=promocodes))


@app.post("/promocodes")
async def create_promocode(request: Request):
    studio_id = require_studio(request)
    form = await request.form()
    async with async_session() as session:
        from src.models.promocode import Promocode
        promo = Promocode(
            studio_id=studio_id,
            code=form.get("code", "").upper().strip(),
            discount_percent=int(form["discount_percent"]) if form.get("discount_percent") else None,
            discount_amount=int(form["discount_amount"]) if form.get("discount_amount") else None,
            max_uses=int(form["max_uses"]) if form.get("max_uses") else None,
            description=form.get("description") or None,
            min_order_amount=int(form.get("min_order_amount") or 0),
            min_photos=int(form.get("min_photos") or 0),
            require_subscription=form.get("require_subscription") == "1",
        )
        session.add(promo)
        await session.commit()
    return RedirectResponse("/promocodes", status_code=303)


@app.post("/promocodes/{promo_id}/delete")
async def delete_promocode(request: Request, promo_id: int):
    studio_id = require_studio(request)
    async with async_session() as session:
        from sqlalchemy import select
        from src.models.promocode import Promocode
        result = await session.execute(
            select(Promocode).where(Promocode.id == promo_id, Promocode.studio_id == studio_id)
        )
        promo = result.scalar_one_or_none()
        if promo is None:
            raise HTTPException(status_code=404, detail="Промокод не найден")
        await session.delete(promo)
        await session.commit()
    return RedirectResponse("/promocodes", status_code=303)


@app.post("/promocodes/{promo_id}/toggle")
async def toggle_promocode(request: Request, promo_id: int):
    studio_id = require_studio(request)
    async with async_session() as session:
        from sqlalchemy import select
        from src.models.promocode import Promocode
        result = await session.execute(
            select(Promocode).where(Promocode.id == promo_id, Promocode.studio_id == studio_id)
        )
        promo = result.scalar_one_or_none()
        if promo is None:
            raise HTTPException(status_code=404, detail="Промокод не найден")
        promo.is_active = not promo.is_active
        await session.commit()
    return RedirectResponse("/promocodes", status_code=303)


# === Настройки ===

SETTING_GROUPS = {
    "general": "Основные",
    "bot": "Бот",
    "crop": "Кадрирование",
    "delivery_ozon": "📦 ОЗОН доставка",
    "delivery_courier": "🚗 Курьерская доставка",
    "delivery_pickup": "🏠 Самовывоз",
    "delivery_general": "🚚 Доставка — общие",
    "contacts": "Контакты",
    "subscription": "Подписка на канал",
    "notifications": "Уведомления",
}

HIDDEN_SETTING_GROUPS = {"system"}


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, saved: str = None):
    studio_id = require_studio(request)
    async with async_session() as session:
        service = SettingsService(session)
        await service.load_cache(studio_id)
        all_settings = await service.get_all(studio_id)
        grouped = {}
        for setting in all_settings:
            group = setting.group
            if group in HIDDEN_SETTING_GROUPS:
                continue
            if group not in grouped:
                grouped[group] = []
            grouped[group].append(setting)
    return templates.TemplateResponse(
        request,
        "settings.html",
        base_context(request, grouped_settings=grouped, group_names=SETTING_GROUPS, saved=saved == "1"),
    )


@app.post("/settings")
async def save_settings(request: Request):
    studio_id = require_studio(request)
    form_data = await request.form()
    async with async_session() as session:
        service = SettingsService(session)
        for key, value in form_data.items():
            if key.startswith("setting_"):
                setting_key = key[8:]
                try:
                    await service.set_value(studio_id, setting_key, value)
                except ValueError:
                    pass  # настройка не найдена для этой студии — пропускаем
    return RedirectResponse("/settings?saved=1", status_code=303)


# ============== ТОВАРЫ / ФОРМАТЫ ==============

@app.get("/products", response_class=HTMLResponse)
async def products_list(request: Request, saved: str = None):
    """Управление товарами и форматами."""
    studio_id = require_studio(request)

    async with async_session() as session:
        service = ProductService(session)
        products = await service.get_all_products(studio_id)

    # Группируем: top-level и их children
    top_level = [p for p in products if p.parent_id is None]
    children_map = {}
    for p in products:
        if p.parent_id:
            if p.parent_id not in children_map:
                children_map[p.parent_id] = []
            children_map[p.parent_id].append(p)

    return templates.TemplateResponse(
        request,
        "products.html",
        base_context(
            request,
            products=top_level,
            children_map=children_map,
            all_products=products,
            saved=saved == "1",
        ),
    )


@app.post("/products")
async def create_product(
    request: Request,
    name: str = Form(...),
    short_name: str = Form(...),
    slug: str = Form(...),
    emoji: str = Form("📷"),
    description: str = Form(""),
    parent_id: Optional[int] = Form(None),
    price_per_unit: int = Form(0),
    price_type: str = Form("per_unit"),
    price_tiers_json: str = Form(""),
    pricing_group: str = Form(""),
    aspect_ratio: Optional[float] = Form(None),
    sort_order: int = Form(0),
):
    """Создание нового товара."""
    studio_id = require_studio(request)

    async with async_session() as session:
        service = ProductService(session)
        await service.create_product(
            studio_id=studio_id,
            name=name,
            short_name=short_name,
            slug=slug,
            emoji=emoji,
            description=description or None,
            parent_id=parent_id if parent_id and parent_id > 0 else None,
            price_per_unit=price_per_unit,
            price_type=price_type,
            price_tiers=price_tiers_json if price_tiers_json else None,
            pricing_group=pricing_group or None,
            aspect_ratio=aspect_ratio,
            sort_order=sort_order,
        )

    return RedirectResponse("/products?saved=1", status_code=303)


@app.post("/products/{product_id}/update")
async def update_product(
    request: Request,
    product_id: int,
    name: str = Form(...),
    short_name: str = Form(...),
    emoji: str = Form("📷"),
    description: str = Form(""),
    price_per_unit: int = Form(0),
    price_type: str = Form("per_unit"),
    price_tiers_json: str = Form(""),
    pricing_group: str = Form(""),
    aspect_ratio: Optional[float] = Form(None),
    sort_order: int = Form(0),
):
    """Обновление товара."""
    studio_id = require_studio(request)

    async with async_session() as session:
        service = ProductService(session)
        result = await service.update_product(
            product_id,
            studio_id=studio_id,
            name=name,
            short_name=short_name,
            emoji=emoji,
            description=description or None,
            price_per_unit=price_per_unit,
            price_type=price_type,
            price_tiers=price_tiers_json if price_tiers_json else None,
            pricing_group=pricing_group or None,
            aspect_ratio=aspect_ratio,
            sort_order=sort_order,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Товар не найден")

    return RedirectResponse("/products?saved=1", status_code=303)


@app.post("/products/{product_id}/toggle")
async def toggle_product(request: Request, product_id: int):
    """Включение/выключение товара."""
    studio_id = require_studio(request)

    async with async_session() as session:
        service = ProductService(session)
        result = await service.toggle_product(product_id, studio_id=studio_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Товар не найден")

    return RedirectResponse("/products", status_code=303)


@app.post("/products/{product_id}/delete")
async def delete_product(request: Request, product_id: int):
    """Удаление товара."""
    studio_id = require_studio(request)

    async with async_session() as session:
        service = ProductService(session)
        ok = await service.delete_product(product_id, studio_id=studio_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Товар не найден")

    return RedirectResponse("/products", status_code=303)


# ============== MINI APP ==============

@app.get("/webapp", response_class=HTMLResponse)
async def webapp_page():
    """Отдаёт Mini App (index.html)."""
    html_path = WEBAPP_DIR / "index.html"
    return FileResponse(html_path, media_type="text/html")


# ============== API ДЛЯ MINI APP ==============

@app.get("/api/photos/{order_id}")
async def get_order_photos_api(order_id: int, token: str = None):
    """API для Mini App: получение фото заказа с данными авто-кропа."""
    if not token or not verify_api_token(order_id, token):
        raise HTTPException(status_code=403, detail="Invalid or missing token")

    async with async_session() as session:
        order_result = await session.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.photos), selectinload(Order.user))
        )
        order = order_result.scalar_one_or_none()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        studio_id = order.studio_id
        await ProductService(session).load_cache(studio_id)

        photos_data = []
        for photo in order.photos:
            auto_crop = None
            if photo.auto_crop_data:
                try:
                    auto_crop = json.loads(photo.auto_crop_data)
                except json.JSONDecodeError:
                    pass

            product = ProductService.get_product(studio_id, photo.product_id)
            product_name = product.short_name if product else "Unknown"

            photos_data.append({
                "id": photo.id,
                "url": f"/api/photo-proxy/{photo.telegram_file_id}",
                "product_id": photo.product_id,
                "product_name": product_name,
                "aspect_ratio": product.aspect_ratio if product and product.aspect_ratio else 0.76,
                "auto_crop": auto_crop,
                "confidence": photo.crop_confidence or 0.5,
                "method": photo.crop_method or "center",
                "faces_found": photo.faces_found or 0,
                "crop_data": photo.crop_data,
                "crop_confirmed": photo.crop_confirmed,
            })

        return {
            "order_id": order_id,
            "order_number": order.order_number,
            "photos": photos_data,
        }


@app.get("/api/photo-proxy/{file_id}")
async def photo_proxy(request: Request, file_id: str):
    """Проксирует фото из Telegram для Mini App."""
    # file_id сам по себе unguessable, но проверяем Referer для доп. защиты
    referer = request.headers.get("referer", "")
    admin_url = settings.admin_url or ""
    if referer and admin_url and not referer.startswith(admin_url):
        raise HTTPException(status_code=403, detail="Forbidden")
    from aiogram import Bot
    import io
    from fastapi.responses import StreamingResponse
    
    bot = Bot(token=settings.bot_token)
    try:
        file = await bot.get_file(file_id)
        photo_bytes = await bot.download_file(file.file_path)
        return StreamingResponse(
            io.BytesIO(photo_bytes.read()),
            media_type="image/jpeg",
            headers={"Cache-Control": "max-age=86400"}
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Photo not found: {e}")
    finally:
        await bot.session.close()


@app.post("/api/crop/save")
async def save_crop_data(request: Request):
    """API для Mini App: сохранение данных кадрирования."""
    from aiogram import Bot
    from src.bot.context import build_studio_context
    from src.bot.keyboards.main import get_delivery_keyboard
    from src.bot.handlers.delivery import get_delivery_message

    data = await request.json()
    order_id = data.get("order_id")
    token = data.get("token", "")
    user_id = data.get("user_id")
    photos = data.get("photos", [])

    if not order_id:
        raise HTTPException(status_code=400, detail="order_id is required")

    if not verify_api_token(order_id, token):
        raise HTTPException(status_code=403, detail="Invalid or missing token")
    if not photos:
        raise HTTPException(status_code=400, detail="No photos data provided")

    async with async_session() as session:
        order_result = await session.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.photos), selectinload(Order.user))
        )
        order = order_result.scalar_one_or_none()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        studio_id = order.studio_id
        service = OrderService(session, studio_id)

        saved_count = 0
        for photo_data in photos:
            photo_id = photo_data.get("id")
            crop = photo_data.get("crop")
            if photo_id and crop:
                await service.update_photo_crop(
                    photo_id=photo_id,
                    crop_data=json.dumps(crop),
                    crop_confirmed=True
                )
                saved_count += 1

        studio_result = await session.execute(select(Studio).where(Studio.id == studio_id))
        studio = studio_result.scalar_one_or_none()

    telegram_user_id = user_id or order.user.telegram_id
    if telegram_user_id and studio and studio.bot_token:
        bot_token = decrypt_secret(studio.bot_token)
        bot = Bot(token=bot_token)
        try:
            async with async_session() as notify_session:
                ctx = build_studio_context(notify_session, studio)
                await bot.send_message(
                    chat_id=telegram_user_id,
                    text=get_delivery_message(ctx),
                    reply_markup=get_delivery_keyboard(ctx),
                    parse_mode="HTML"
                )
        except Exception as e:
            import logging
            logging.error(f"Failed to send message to user: {e}")
        finally:
            await bot.session.close()

    return {"status": "ok", "saved_count": saved_count}


# ============== АНАЛИТИКА ==============

# ============== СТУДИИ (только super_admin) ==============

@app.get("/studios", response_class=HTMLResponse)
async def studios_list(request: Request):
    """Список всех студий — только для super_admin."""
    require_super_admin(request)
    async with async_session() as session:
        result = await session.execute(select(Studio).order_by(Studio.id))
        studios = result.scalars().all()
    return templates.TemplateResponse(request, "studios.html", base_context(request, studios=studios))


@app.post("/studios")
async def studios_create(
    request: Request,
    slug: str = Form(...),
    name: str = Form(...),
    bot_token: str = Form(...),
    admin_username: str = Form(...),
    admin_password: str = Form(...),
):
    """Создать новую студию — только для super_admin."""
    require_super_admin(request)
    async with async_session() as session:
        await provision_studio(
            session,
            slug=slug,
            name=name,
            bot_token=bot_token,
            admin_username=admin_username,
            admin_password=admin_password,
        )
    return RedirectResponse("/studios", status_code=303)


# ВАЖНО: /studios/exit-view зарегистрирован ДО /studios/{studio_id}/...
# иначе FastAPI матчит "exit-view" как studio_id.

@app.post("/studios/exit-view")
async def studios_exit_view(request: Request):
    """Выйти из режима просмотра от имени студии."""
    require_super_admin(request)
    request.session.pop("active_studio_id", None)
    return RedirectResponse("/studios", status_code=303)


@app.post("/studios/{studio_id}/toggle")
async def studios_toggle(request: Request, studio_id: int):
    """Инвертировать kill-switch студии — только для super_admin."""
    require_super_admin(request)
    async with async_session() as session:
        result = await session.execute(select(Studio).where(Studio.id == studio_id))
        studio = result.scalar_one_or_none()
        if not studio:
            raise HTTPException(status_code=404, detail="Студия не найдена")
        studio.is_active = not studio.is_active
        await session.commit()
    return RedirectResponse("/studios", status_code=303)


@app.post("/studios/{studio_id}/view-as")
async def studios_view_as(request: Request, studio_id: int):
    """Переключить активную студию для super_admin (view-as)."""
    require_super_admin(request)
    request.session["active_studio_id"] = studio_id
    return RedirectResponse("/", status_code=303)


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    studio_id = require_studio(request)
    async with async_session() as session:
        service = AnalyticsService(session, studio_id)
        summary = await service.get_dashboard_summary()
        chart_data = await service.get_revenue_by_days(30)
        format_stats = await service.get_format_stats()
        delivery_stats = await service.get_delivery_stats()
        top_customers = await service.get_top_customers(10)
        customer_stats = await service.get_customer_stats()

    return templates.TemplateResponse(
        request,
        "analytics.html",
        base_context(
            request,
            summary=summary, chart_data=chart_data,
            format_stats=format_stats, delivery_stats=delivery_stats,
            top_customers=top_customers, customer_stats=customer_stats,
        ),
    )
