"""FastAPI приложение для админ-панели."""
import secrets
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from src.config import settings
from src.database import async_session
from src.services.order_service import OrderService
from src.services.file_service import FileService
from src.services.yandex_disk import YandexDiskService
from src.services.settings_service import SettingsService, SettingKeys
from src.services.analytics_service import AnalyticsService
from datetime import datetime, timedelta
from src.models.order import OrderStatus

# Создаём приложение
app = FastAPI(title="Photo28 Admin", docs_url=None, redoc_url=None)

# Сессии для авторизации
app.add_middleware(SessionMiddleware, secret_key=settings.admin_secret_key)

# Статика и шаблоны
BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def check_auth(request: Request) -> bool:
    """Проверяет авторизацию."""
    return request.session.get("authenticated", False)


async def require_auth(request: Request):
    """Требует авторизации."""
    if not check_auth(request):
        raise HTTPException(status_code=303, headers={"Location": "/login"})


# === Авторизация ===

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    """Страница входа."""
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": error},
    )


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Обработка входа."""
    if username == settings.admin_username and password == settings.admin_password:
        request.session["authenticated"] = True
        return RedirectResponse("/", status_code=303)
    
    return RedirectResponse("/login?error=invalid", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    """Выход."""
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# === Главная страница ===

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Главная страница — дашборд."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    async with async_session() as session:
        service = OrderService(session)
        
        # Получаем статистику
        all_orders = await service.get_all_orders(limit=1000)
        
        stats = {
            "total_orders": len(all_orders),
            "pending_payment": len([o for o in all_orders if o.status == OrderStatus.PENDING_PAYMENT]),
            "paid": len([o for o in all_orders if o.status == OrderStatus.PAID]),
            "confirmed": len([o for o in all_orders if o.status == OrderStatus.CONFIRMED]),
            "printing": len([o for o in all_orders if o.status == OrderStatus.PRINTING]),
            "shipped": len([o for o in all_orders if o.status == OrderStatus.SHIPPED]),
        }
        
        # Получаем последние заказы
        recent_orders = await service.get_all_orders(limit=10)
    
    # Статистика хранилища
    file_service = FileService(settings.bot_token)
    storage_stats = file_service.get_storage_stats()
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "stats": stats,
            "orders": recent_orders,
            "storage": storage_stats,
        },
    )


# === Список заказов ===

@app.get("/orders", response_class=HTMLResponse)
async def orders_list(
    request: Request,
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
):
    """Список заказов с фильтрацией."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    per_page = 20
    offset = (page - 1) * per_page
    
    async with async_session() as session:
        service = OrderService(session)
        
        if status:
            try:
                status_enum = OrderStatus(status)
                orders = await service.get_orders_by_status(status_enum)
            except ValueError:
                orders = await service.get_all_orders(limit=per_page, offset=offset)
        else:
            orders = await service.get_all_orders(limit=per_page, offset=offset)
    
    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "orders": orders,
            "current_status": status,
            "page": page,
            "statuses": OrderStatus,
        },
    )


# === Детали заказа ===

@app.get("/orders/{order_id}", response_class=HTMLResponse)
async def order_detail(request: Request, order_id: int):
    """Детальная страница заказа."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")
    
    return templates.TemplateResponse(
        "order_detail.html",
        {
            "request": request,
            "order": order,
            "statuses": OrderStatus,
        },
    )


# === Изменение статуса ===

@app.post("/orders/{order_id}/status")
async def update_order_status(
    request: Request,
    order_id: int,
    status: str = Form(...),
):
    """Обновление статуса заказа."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        
        try:
            new_status = OrderStatus(status)
            await service.update_order_status(order, new_status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный статус")
    
    return RedirectResponse(f"/orders/{order_id}", status_code=303)


# === Скачивание фотографий ===

@app.get("/orders/{order_id}/download")
async def download_order_photos(request: Request, order_id: int):
    """Скачивает все фото заказа из Telegram и готовит для печати."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")
    
    # Скачиваем фото
    file_service = FileService(settings.bot_token)
    
    try:
        await file_service.download_all_order_photos(order)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка скачивания: {e}")
    
    return RedirectResponse(f"/orders/{order_id}?downloaded=1", status_code=303)


# === Загрузка на Яндекс.Диск ===

@app.post("/orders/{order_id}/upload-yandex")
async def upload_to_yandex(request: Request, order_id: int):
    """Загружает фото заказа на Яндекс.Диск."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")
    
    file_service = FileService(settings.bot_token)
    order_dir = file_service.get_order_dir(order)
    
    if not order_dir.exists() or not list(order_dir.glob("*.*")):
        raise HTTPException(
            status_code=400,
            detail="Сначала скачайте фото из Telegram",
        )
    
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
    """Список локальных фото заказа."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")
    
    file_service = FileService(settings.bot_token)
    photos = file_service.get_order_photos_paths(order)
    
    return templates.TemplateResponse(
        "photos.html",
        {
            "request": request,
            "order": order,
            "photos": photos,
        },
    )


@app.get("/storage/{order_number}/{filename}")
async def serve_photo(request: Request, order_number: str, filename: str):
    """Отдаёт файл фотографии."""
    if not check_auth(request):
        raise HTTPException(status_code=403)
    
    file_path = settings.photos_dir / order_number / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404)
    
    return FileResponse(file_path)


# === Промокоды ===

@app.get("/promocodes", response_class=HTMLResponse)
async def promocodes_list(request: Request):
    """Список промокодов."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    async with async_session() as session:
        from sqlalchemy import select
        from src.models.promocode import Promocode
        
        result = await session.execute(select(Promocode).order_by(Promocode.created_at.desc()))
        promocodes = result.scalars().all()
    
    return templates.TemplateResponse(
        "promocodes.html",
        {"request": request, "promocodes": promocodes},
    )


@app.post("/promocodes")
async def create_promocode(
    request: Request,
    code: str = Form(...),
    discount_percent: Optional[int] = Form(None),
    discount_amount: Optional[int] = Form(None),
    max_uses: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
):
    """Создание промокода."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    async with async_session() as session:
        service = OrderService(session)
        await service.create_promocode(
            code=code,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            max_uses=max_uses,
            description=description,
        )
    
    return RedirectResponse("/promocodes", status_code=303)


@app.post("/promocodes/{promo_id}/delete")
async def delete_promocode(request: Request, promo_id: int):
    """Удаление промокода."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    async with async_session() as session:
        from sqlalchemy import select
        from src.models.promocode import Promocode
        
        result = await session.execute(select(Promocode).where(Promocode.id == promo_id))
        promo = result.scalar_one_or_none()
        
        if promo:
            await session.delete(promo)
            await session.commit()
    
    return RedirectResponse("/promocodes", status_code=303)


@app.post("/promocodes/{promo_id}/toggle")
async def toggle_promocode(request: Request, promo_id: int):
    """Включение/отключение промокода."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    async with async_session() as session:
        from sqlalchemy import select
        from src.models.promocode import Promocode
        
        result = await session.execute(select(Promocode).where(Promocode.id == promo_id))
        promo = result.scalar_one_or_none()
        
        if promo:
            promo.is_active = not promo.is_active
            await session.commit()
    
    return RedirectResponse("/promocodes", status_code=303)


# === Настройки ===

SETTING_GROUPS = {
    "general": "Основные",
    "delivery": "Доставка",
    "contacts": "Контакты",
    "notifications": "Уведомления",
}

# Группы, которые не показываем в UI настроек
HIDDEN_SETTING_GROUPS = {"system"}


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, saved: str = None):
    """Страница настроек."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    async with async_session() as session:
        service = SettingsService(session)
        all_settings = await service.get_all()
        
        # Группируем настройки, исключая скрытые группы
        grouped = {}
        for setting in all_settings:
            group = setting.group
            if group in HIDDEN_SETTING_GROUPS:
                continue
            if group not in grouped:
                grouped[group] = []
            grouped[group].append(setting)
    
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "grouped_settings": grouped,
            "group_names": SETTING_GROUPS,
            "saved": saved == "1",
        },
    )


@app.post("/settings")
async def save_settings(request: Request):
    """Сохранение настроек."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    form_data = await request.form()
    
    async with async_session() as session:
        service = SettingsService(session)
        
        for key, value in form_data.items():
            if key.startswith("setting_"):
                setting_key = key[8:]  # Убираем префикс "setting_"
                await service.set_value(setting_key, value)
    
    return RedirectResponse("/settings?saved=1", status_code=303)


# === Управление ботом ===

@app.get("/bot-control", response_class=HTMLResponse)
async def bot_control_page(request: Request, action: str = None):
    """Страница управления ботом."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    # Получаем текущий статус
    restart_requested = SettingsService.get_bool(SettingKeys.RESTART_REQUESTED, False)
    scheduled_time_str = SettingsService.get(SettingKeys.RESTART_SCHEDULED_TIME, "")
    
    scheduled_time = None
    if scheduled_time_str:
        try:
            scheduled_time = datetime.fromisoformat(scheduled_time_str)
        except ValueError:
            pass
    
    return templates.TemplateResponse(
        "bot_control.html",
        {
            "request": request,
            "restart_requested": restart_requested,
            "scheduled_time": scheduled_time,
            "action": action,
        },
    )


@app.post("/bot-control/restart-now")
async def restart_bot_now(request: Request):
    """Запросить немедленный перезапуск бота."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    async with async_session() as session:
        service = SettingsService(session)
        await service.set_value(SettingKeys.RESTART_REQUESTED, "true")
        await service.set_value(SettingKeys.RESTART_SCHEDULED_TIME, "")
    
    return RedirectResponse("/bot-control?action=restart_requested", status_code=303)


@app.post("/bot-control/schedule-restart")
async def schedule_restart(request: Request, hour: int = Form(5)):
    """Запланировать перезапуск на определённое время."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    # Вычисляем следующее время hour:00
    now = datetime.now()
    scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    
    # Если это время уже прошло сегодня — планируем на завтра
    if scheduled <= now:
        scheduled += timedelta(days=1)
    
    async with async_session() as session:
        service = SettingsService(session)
        await service.set_value(SettingKeys.RESTART_SCHEDULED_TIME, scheduled.isoformat())
        await service.set_value(SettingKeys.RESTART_REQUESTED, "false")
    
    return RedirectResponse("/bot-control?action=scheduled", status_code=303)


@app.post("/bot-control/cancel-restart")
async def cancel_restart(request: Request):
    """Отменить запланированный перезапуск."""
    if not check_auth(request):
        return RedirectResponse("/login", status_code=303)
    
    async with async_session() as session:
        service = SettingsService(session)
        await service.set_value(SettingKeys.RESTART_REQUESTED, "false")
        await service.set_value(SettingKeys.RESTART_SCHEDULED_TIME, "")
    
    return RedirectResponse("/bot-control?action=cancelled", status_code=303)


# ============== АНАЛИТИКА ==============

@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request, _: None = Depends(require_auth)):
    """Страница аналитики."""
    async with async_session() as session:
        service = AnalyticsService(session)
        
        # Основная сводка
        summary = await service.get_dashboard_summary()
        
        # Данные для графика (30 дней)
        chart_data = await service.get_revenue_by_days(30)
        
        # Статистика по форматам
        format_stats = await service.get_format_stats()
        
        # Статистика по доставке
        delivery_stats = await service.get_delivery_stats()
        
        # Топ клиентов
        top_customers = await service.get_top_customers(10)
        
        # Статистика клиентов
        customer_stats = await service.get_customer_stats()
    
    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "summary": summary,
            "chart_data": chart_data,
            "format_stats": format_stats,
            "delivery_stats": delivery_stats,
            "top_customers": top_customers,
            "customer_stats": customer_stats,
        },
    )

