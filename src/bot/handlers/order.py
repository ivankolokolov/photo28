"""Обработчики заказа и фотографий."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from src.bot.states import OrderStates
from src.bot.keyboards import (
    get_format_keyboard,
    get_photo_actions_keyboard,
    get_order_summary_keyboard,
    get_delete_photos_keyboard,
)
from src.database import async_session
from src.services.order_service import OrderService
from src.services.pricing import PricingService
from src.models.photo import PhotoFormat

router = Router()

UPLOAD_MESSAGE = """📸 Пожалуйста, ознакомьтесь с тем, как будут кадрироваться фото:
https://dariakis28.ru/kadrirovanie-fotografiy

Вы выбрали формат: <b>{format_name}</b>

Пришлите мне фото. Чтобы сохранить качество — присылайте файлами "без сжатия" 📎"""

MIN_PHOTOS = 10


@router.callback_query(F.data.startswith("format:"))
async def select_format(callback: CallbackQuery, state: FSMContext):
    """Выбор формата фотографий."""
    format_value = callback.data.split(":")[1]
    photo_format = PhotoFormat(format_value)
    
    await state.update_data(current_format=format_value)
    
    # Получаем текущий заказ для отображения кнопок
    data = await state.get_data()
    order_id = data.get("order_id")
    
    has_photos = False
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        if order and order.photos:
            has_photos = True
    
    await callback.message.edit_text(
        UPLOAD_MESSAGE.format(format_name=photo_format.display_name),
        reply_markup=get_photo_actions_keyboard(has_photos),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    
    await state.set_state(OrderStates.uploading_photos)
    await callback.answer()


@router.message(OrderStates.uploading_photos, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    """Обработка загруженного фото (сжатого)."""
    data = await state.get_data()
    order_id = data.get("order_id")
    current_format = data.get("current_format")
    
    if not order_id or not current_format:
        await message.answer("Ошибка. Пожалуйста, начните заново: /start")
        return
    
    photo_format = PhotoFormat(current_format)
    
    # Берём фото максимального размера
    file_id = message.photo[-1].file_id
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await message.answer("Заказ не найден. Начните заново: /start")
            return
        
        # Добавляем фото
        await service.add_photo(order, photo_format, file_id)
        
        # Обновляем данные заказа
        order = await service.get_order_by_id(order_id)
        photos_count = order.photos_count
    
    await message.answer(
        f"✅ Фото добавлено! Всего загружено: {photos_count} шт.\n\n"
        "Продолжайте отправлять фото или выберите действие:",
        reply_markup=get_photo_actions_keyboard(has_photos=True),
    )


@router.message(OrderStates.uploading_photos, F.document)
async def handle_document(message: Message, state: FSMContext):
    """Обработка загруженного документа (без сжатия)."""
    data = await state.get_data()
    order_id = data.get("order_id")
    current_format = data.get("current_format")
    
    if not order_id or not current_format:
        await message.answer("Ошибка. Пожалуйста, начните заново: /start")
        return
    
    # Проверяем, что это изображение
    mime_type = message.document.mime_type or ""
    if not mime_type.startswith("image/"):
        await message.answer(
            "⚠️ Пожалуйста, отправляйте только изображения.\n"
            "Поддерживаемые форматы: JPG, PNG, HEIC"
        )
        return
    
    photo_format = PhotoFormat(current_format)
    file_id = message.document.file_id
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await message.answer("Заказ не найден. Начните заново: /start")
            return
        
        await service.add_photo(order, photo_format, file_id)
        
        order = await service.get_order_by_id(order_id)
        photos_count = order.photos_count
    
    await message.answer(
        f"✅ Фото добавлено (оригинал)! Всего загружено: {photos_count} шт.\n\n"
        "Продолжайте отправлять фото или выберите действие:",
        reply_markup=get_photo_actions_keyboard(has_photos=True),
    )


@router.callback_query(F.data == "add_another_format")
async def add_another_format(callback: CallbackQuery, state: FSMContext):
    """Добавить фото другого формата."""
    await callback.message.edit_text(
        "Выберите формат для следующих фотографий:",
        reply_markup=get_format_keyboard(),
    )
    
    await state.set_state(OrderStates.selecting_format)
    await callback.answer()


@router.callback_query(F.data == "finish_photos")
async def finish_photos(callback: CallbackQuery, state: FSMContext):
    """Завершение отбора фото."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await callback.answer("Заказ не найден")
            return
        
        # Проверяем минимальное количество
        if order.photos_count < MIN_PHOTOS:
            await callback.answer(
                f"Минимальный заказ {MIN_PHOTOS} фото любого формата.",
                show_alert=True,
            )
            return
        
        # Показываем сводку заказа
        await show_order_summary(callback.message, order, edit=True)
    
    await state.set_state(OrderStates.reviewing_order)
    await callback.answer()


async def show_order_summary(message, order, edit: bool = False):
    """Отображает сводку заказа."""
    photos_by_format = order.photos_by_format()
    
    # Формируем текст сводки
    lines = ["<b>📋 Ваш заказ:</b>\n"]
    
    for fmt, count in photos_by_format.items():
        lines.append(f"• {fmt.short_name}: {count} шт.")
    
    lines.append(f"\nВсего фото: <b>{order.photos_count}</b> шт.")
    
    # Расчёт стоимости
    cost = PricingService.calculate_total_cost(photos_by_format)
    lines.append(f"\n💰 Предварительная стоимость (без доставки): <b>{cost}₽</b>")
    
    # Проверяем оптимизацию
    hint = PricingService.get_price_optimization_hint(photos_by_format)
    if hint:
        lines.append(f"\n{hint}")
    
    text = "\n".join(lines)
    
    if edit:
        await message.edit_text(
            text,
            reply_markup=get_order_summary_keyboard(),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            text,
            reply_markup=get_order_summary_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "back_to_photos")
async def back_to_photos(callback: CallbackQuery, state: FSMContext):
    """Возврат к сводке заказа."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if order and order.photos_count > 0:
            await show_order_summary(callback.message, order, edit=True)
            await state.set_state(OrderStates.reviewing_order)
        else:
            await callback.message.edit_text(
                "Выберите формат фотографий:",
                reply_markup=get_format_keyboard(),
            )
            await state.set_state(OrderStates.selecting_format)
    
    await callback.answer()


@router.callback_query(F.data == "back_to_summary")
async def back_to_summary(callback: CallbackQuery, state: FSMContext):
    """Возврат к сводке заказа."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if order:
            await show_order_summary(callback.message, order, edit=True)
    
    await state.set_state(OrderStates.reviewing_order)
    await callback.answer()


# === Удаление фото ===

@router.callback_query(F.data == "delete_photos")
async def start_delete_photos(callback: CallbackQuery, state: FSMContext):
    """Начало удаления фото."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order or not order.photos:
            await callback.answer("Нет фото для удаления")
            return
        
        await state.update_data(delete_page=0)
        
        await callback.message.edit_text(
            "🗑 <b>Удаление фото</b>\n\n"
            "Выберите фото для удаления.\n"
            "После удаления нажмите «Закончить удаление»",
            reply_markup=get_delete_photos_keyboard(order.photos, page=0),
            parse_mode="HTML",
        )
    
    await state.set_state(OrderStates.deleting_photos)
    await callback.answer()


@router.callback_query(OrderStates.deleting_photos, F.data.startswith("delete_photo:"))
async def delete_photo(callback: CallbackQuery, state: FSMContext):
    """Удаление конкретного фото."""
    photo_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    order_id = data.get("order_id")
    page = data.get("delete_page", 0)
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await callback.answer("Заказ не найден")
            return
        
        # Находим и удаляем фото
        photo_to_delete = None
        for photo in order.photos:
            if photo.id == photo_id:
                photo_to_delete = photo
                break
        
        if photo_to_delete:
            await service.remove_photo(photo_to_delete)
            await callback.answer("Фото удалено ✓")
        
        # Обновляем заказ
        order = await service.get_order_by_id(order_id)
        
        if not order.photos:
            await callback.message.edit_text(
                "Все фото удалены. Выберите формат для добавления новых:",
                reply_markup=get_format_keyboard(),
            )
            await state.set_state(OrderStates.selecting_format)
        else:
            # Корректируем страницу если нужно
            max_page = (len(order.photos) - 1) // 5
            if page > max_page:
                page = max_page
                await state.update_data(delete_page=page)
            
            await callback.message.edit_text(
                f"🗑 <b>Удаление фото</b>\n\n"
                f"Осталось фото: {len(order.photos)}\n"
                "Выберите фото для удаления или завершите:",
                reply_markup=get_delete_photos_keyboard(order.photos, page=page),
                parse_mode="HTML",
            )


@router.callback_query(OrderStates.deleting_photos, F.data.startswith("photos_page:"))
async def photos_page(callback: CallbackQuery, state: FSMContext):
    """Переключение страницы фото."""
    page = int(callback.data.split(":")[1])
    data = await state.get_data()
    order_id = data.get("order_id")
    
    await state.update_data(delete_page=page)
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if order:
            await callback.message.edit_reply_markup(
                reply_markup=get_delete_photos_keyboard(order.photos, page=page)
            )
    
    await callback.answer()


@router.callback_query(OrderStates.deleting_photos, F.data == "finish_deleting")
async def finish_deleting(callback: CallbackQuery, state: FSMContext):
    """Завершение удаления фото."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if order and order.photos_count >= MIN_PHOTOS:
            await show_order_summary(callback.message, order, edit=True)
            await state.set_state(OrderStates.reviewing_order)
        elif order and order.photos_count > 0:
            await callback.answer(
                f"Минимальный заказ {MIN_PHOTOS} фото. "
                f"Сейчас: {order.photos_count}",
                show_alert=True,
            )
        else:
            await callback.message.edit_text(
                "Выберите формат фотографий:",
                reply_markup=get_format_keyboard(),
            )
            await state.set_state(OrderStates.selecting_format)
    
    await callback.answer()

