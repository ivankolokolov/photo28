"""Обработка кадрирования фото через Mini App."""
import json
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, WebAppInfo
from aiogram.fsm.context import FSMContext

from src.database import async_session
from src.services.order_service import OrderService
from src.bot.states import OrderStates
from src.bot.keyboards import get_main_menu_keyboard
from src.config import settings

router = Router()
logger = logging.getLogger(__name__)

# URL Mini App на GitHub Pages
WEBAPP_URL = "https://ivankolokolov.github.io/photo28"


def get_crop_webapp_keyboard(order_id: int):
    """Клавиатура с кнопкой открытия Mini App."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from urllib.parse import quote
    
    # Формируем URL с параметрами
    api_url = settings.admin_url or "http://localhost:8080"
    webapp_url = f"{WEBAPP_URL}?order_id={order_id}&api_url={quote(api_url)}"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✂️ Настроить кадрирование",
            web_app=WebAppInfo(url=webapp_url)
        )],
        [InlineKeyboardButton(
            text="⏭ Пропустить (авто-кадр)",
            callback_data="skip_crop"
        )],
    ])


@router.message(F.web_app_data)
async def handle_webapp_data(message: Message, state: FSMContext):
    """Обработка данных из Mini App."""
    logger.info(f"=== WEB APP DATA RECEIVED ===")
    logger.info(f"Raw data: {message.web_app_data.data[:500] if message.web_app_data else 'None'}")
    
    try:
        data = json.loads(message.web_app_data.data)
        logger.info(f"Parsed crop data: {data}")
        
        photos = data.get("photos", [])
        logger.info(f"Photos count: {len(photos)}")
        
        if not photos:
            await message.answer("⚠️ Не получены данные кадрирования")
            return
        
        async with async_session() as session:
            service = OrderService(session)
            
            # Сохраняем данные кропа для каждого фото
            saved_count = 0
            for photo_data in photos:
                photo_id = photo_data.get("id")
                crop = photo_data.get("crop")
                
                logger.info(f"Processing photo {photo_id}: crop={crop}")
                
                if photo_id and crop:
                    await service.update_photo_crop(
                        photo_id=photo_id,
                        crop_data=json.dumps(crop),
                        crop_confirmed=True
                    )
                    saved_count += 1
        
        logger.info(f"Saved {saved_count} photos crop data")
        
        # Сразу показываем меню доставки
        from src.bot.keyboards.main import get_delivery_keyboard
        
        await message.answer(
            f"✅ Кадрирование сохранено!\n"
            f"Обработано фото: {saved_count} шт.\n\n"
            "📦 <b>Выберите способ доставки:</b>\n\n"
            "🟠 <b>OZON</b> — до пункта выдачи OZON\n"
            "🔴 <b>СДЭК</b> — до пункта выдачи СДЭК\n"
            "📬 <b>Почта России</b> — до почтового отделения\n"
            "🚗 <b>Курьер по Москве</b> — доставка до двери\n"
            "🏠 <b>Самовывоз</b> — бесплатно, м. Чертановская",
            reply_markup=get_delivery_keyboard(),
            parse_mode="HTML"
        )
        
        # Переходим к выбору доставки
        await state.set_state(OrderStates.selecting_delivery)
        logger.info("State set to selecting_delivery")
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse webapp data: {e}")
        await message.answer("❌ Ошибка обработки данных. Попробуйте ещё раз.")
    except Exception as e:
        logger.exception(f"Error handling webapp data: {e}")
        await message.answer(f"❌ Произошла ошибка: {str(e)[:100]}")


@router.callback_query(F.data == "skip_crop")
async def skip_crop(callback: CallbackQuery, state: FSMContext):
    """Пропустить ручное кадрирование, использовать авто-кадр."""
    await callback.answer()
    
    data = await state.get_data()
    order_id = data.get("order_id")
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if order:
            # Показываем сводку заказа
            from src.bot.handlers.order import show_order_summary
            await show_order_summary(callback.message, order, edit=True)
    
    await state.set_state(OrderStates.reviewing_order)


@router.callback_query(F.data == "open_crop_editor")
async def open_crop_editor(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Открыть редактор кадрирования."""
    await callback.answer()
    
    # Получаем текущий заказ
    data = await state.get_data()
    order_id = data.get("order_id")
    
    if not order_id:
        await callback.message.answer("❌ Заказ не найден. Начните сначала: /start")
        return
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order or not order.photos:
            await callback.message.answer("❌ Фото не найдены.")
            return
        
        photos_count = len(order.photos)
    
    await callback.message.edit_text(
        f"✂️ *Кадрирование фото*\n\n"
        f"У вас {photos_count} фото.\n"
        f"Нажмите кнопку ниже, чтобы открыть редактор кадрирования.\n\n"
        f"💡 Вы можете настроить область печати для каждого фото или пропустить этот шаг.",
        parse_mode="Markdown",
        reply_markup=get_crop_webapp_keyboard(order_id)
    )


async def suggest_crop_after_photos(message: Message, state: FSMContext, order_id: int, photos_count: int):
    """Предложить кадрирование после загрузки всех фото."""
    
    # Проверяем нужно ли предлагать кадрирование
    # (можно вынести в настройки админки)
    
    await message.answer(
        f"📷 Отлично! Загружено {photos_count} фото.\n\n"
        f"✂️ Хотите настроить кадрирование?\n"
        f"Это позволит выбрать, какая часть фото попадёт в печать.\n\n"
        f"💡 Если пропустить — будет использовано авто-кадрирование по центру.",
        reply_markup=get_crop_webapp_keyboard(order_id)
    )
