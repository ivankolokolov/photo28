"""Обработчики заказа и фотографий."""
import asyncio
from typing import Dict
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InputMediaDocument
from aiogram.fsm.context import FSMContext

from src.bot.states import OrderStates
from src.bot.keyboards import (
    get_format_keyboard,
    get_photo_actions_keyboard,
    get_order_summary_keyboard,
    get_delete_photos_keyboard,
    get_photo_preview_keyboard,
)
from src.database import async_session
from src.services.order_service import OrderService
from src.services.pricing import PricingService
from src.models.photo import PhotoFormat

router = Router()

# Словарь для отслеживания media_group: {media_group_id: {"task": Task, "count": int, "user_id": int, "order_id": int}}
_media_groups: Dict[str, dict] = {}

# Словарь для отслеживания одиночных фото (без media_group_id): {user_id: {"task": Task, "count": int}}
_single_photo_tasks: Dict[int, dict] = {}

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


async def _send_media_group_confirmation(
    bot: Bot,
    media_group_id: str,
):
    """Отправляет сообщение о добавленных фото из альбома после короткой задержки."""
    await asyncio.sleep(0.5)  # Короткая задержка для сбора всех фото из альбома
    
    group_info = _media_groups.pop(media_group_id, None)
    if not group_info:
        return
    
    user_id = group_info["user_id"]
    order_id = group_info["order_id"]
    added_count = group_info.get("count", 1)
    
    # Получаем актуальное количество фото
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        if not order:
            return
        photos_count = order.photos_count
    
    if added_count > 1:
        text = f"✅ Добавлено {added_count} фото! Всего загружено: {photos_count} шт."
    else:
        text = f"✅ Фото добавлено! Всего загружено: {photos_count} шт."
    
    await bot.send_message(
        chat_id=user_id,
        text=f"{text}\n\nПродолжайте отправлять фото или выберите действие:",
        reply_markup=get_photo_actions_keyboard(has_photos=True),
    )


async def _send_single_photo_confirmation(
    bot: Bot,
    user_id: int,
    order_id: int,
):
    """Отправляет сообщение о добавленном одиночном фото."""
    await asyncio.sleep(0.3)  # Небольшая задержка на случай быстрой отправки
    
    single_info = _single_photo_tasks.pop(user_id, None)
    if not single_info:
        return
    
    added_count = single_info.get("count", 1)
    
    # Получаем актуальное количество фото
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        if not order:
            return
        photos_count = order.photos_count
    
    if added_count > 1:
        text = f"✅ Добавлено {added_count} фото! Всего загружено: {photos_count} шт."
    else:
        text = f"✅ Фото добавлено! Всего загружено: {photos_count} шт."
    
    await bot.send_message(
        chat_id=user_id,
        text=f"{text}\n\nПродолжайте отправлять фото или выберите действие:",
        reply_markup=get_photo_actions_keyboard(has_photos=True),
    )


async def _add_photo_to_batch(
    message: Message,
    state: FSMContext,
    bot: Bot,
    file_id: str,
    is_document: bool = False,
):
    """Добавляет фото в заказ и планирует отправку подтверждения."""
    data = await state.get_data()
    order_id = data.get("order_id")
    current_format = data.get("current_format")
    user_id = message.from_user.id
    media_group_id = message.media_group_id
    
    if not order_id or not current_format:
        await message.answer("Ошибка. Пожалуйста, начните заново: /start")
        return
    
    photo_format = PhotoFormat(current_format)
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await message.answer("Заказ не найден. Начните заново: /start")
            return
        
        # Добавляем фото
        await service.add_photo(order, photo_format, file_id, is_document=is_document)
    
    # Если это фото из альбома (media_group)
    if media_group_id:
        if media_group_id in _media_groups:
            # Отменяем предыдущую задачу
            old_task = _media_groups[media_group_id].get("task")
            if old_task and not old_task.done():
                old_task.cancel()
            _media_groups[media_group_id]["count"] += 1
        else:
            _media_groups[media_group_id] = {
                "count": 1,
                "user_id": user_id,
                "order_id": order_id,
            }
        
        # Создаём новую задачу
        task = asyncio.create_task(
            _send_media_group_confirmation(bot, media_group_id)
        )
        _media_groups[media_group_id]["task"] = task
    else:
        # Одиночное фото
        if user_id in _single_photo_tasks:
            old_task = _single_photo_tasks[user_id].get("task")
            if old_task and not old_task.done():
                old_task.cancel()
            _single_photo_tasks[user_id]["count"] += 1
        else:
            _single_photo_tasks[user_id] = {"count": 1}
        
        task = asyncio.create_task(
            _send_single_photo_confirmation(bot, user_id, order_id)
        )
        _single_photo_tasks[user_id]["task"] = task


@router.message(OrderStates.uploading_photos, F.photo)
async def handle_photo(message: Message, state: FSMContext, bot: Bot):
    """Обработка загруженного фото (сжатого)."""
    file_id = message.photo[-1].file_id
    await _add_photo_to_batch(message, state, bot, file_id, is_document=False)


@router.message(OrderStates.uploading_photos, F.document)
async def handle_document(message: Message, state: FSMContext, bot: Bot):
    """Обработка загруженного документа (без сжатия)."""
    # Проверяем, что это изображение
    mime_type = message.document.mime_type or ""
    if not mime_type.startswith("image/"):
        await message.answer(
            "⚠️ Пожалуйста, отправляйте только изображения.\n"
            "Поддерживаемые форматы: JPG, PNG, HEIC"
        )
        return
    
    file_id = message.document.file_id
    await _add_photo_to_batch(message, state, bot, file_id, is_document=True)


@router.message(OrderStates.uploading_photos, F.video | F.video_note | F.animation)
async def handle_video_rejected(message: Message):
    """Отклонение видео."""
    await message.answer(
        "⚠️ Видео не поддерживается.\n"
        "Пожалуйста, отправляйте только фотографии (JPG, PNG, HEIC)."
    )


@router.message(OrderStates.uploading_photos, F.audio | F.voice)
async def handle_audio_rejected(message: Message):
    """Отклонение аудио."""
    await message.answer(
        "⚠️ Аудио не поддерживается.\n"
        "Пожалуйста, отправляйте только фотографии."
    )


@router.message(OrderStates.uploading_photos, F.sticker)
async def handle_sticker_rejected(message: Message):
    """Отклонение стикеров."""
    await message.answer(
        "⚠️ Стикеры не поддерживаются.\n"
        "Пожалуйста, отправляйте фотографии."
    )


@router.message(OrderStates.uploading_photos, F.text)
async def handle_text_in_upload(message: Message):
    """Текст в режиме загрузки фото."""
    await message.answer(
        "📷 Сейчас я жду фотографии.\n"
        "Отправьте фото или нажмите кнопку ниже.",
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

def _get_photo_caption(photo, idx: int, total: int, extra_text: str = "") -> str:
    """Формирует подпись для фото при удалении."""
    caption = (
        f"🗑 <b>Удаление фото</b>\n\n"
        f"Фото {idx + 1} из {total}\n"
        f"Формат: {photo.format.short_name}"
    )
    if extra_text:
        caption += f"\n\n{extra_text}"
    return caption


async def _send_photo_preview(bot: Bot, chat_id: int, photo, idx: int, total: int, extra_text: str = ""):
    """Отправляет превью фото (photo или document)."""
    caption = _get_photo_caption(photo, idx, total, extra_text)
    keyboard = get_photo_preview_keyboard(photo, idx, total)
    
    if photo.is_document:
        await bot.send_document(
            chat_id=chat_id,
            document=photo.telegram_file_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo.telegram_file_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )


@router.callback_query(F.data == "delete_photos")
async def start_delete_photos(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Начало удаления фото — показываем первое фото с превью."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order or not order.photos:
            await callback.answer("Нет фото для удаления")
            return
        
        # Сохраняем текущий индекс фото
        await state.update_data(delete_photo_idx=0)
        
        # Удаляем старое сообщение
        await callback.message.delete()
        
        # Отправляем первое фото с превью
        photo = order.photos[0]
        await _send_photo_preview(bot, callback.from_user.id, photo, 0, len(order.photos))
    
    await state.set_state(OrderStates.deleting_photos)
    await callback.answer()


@router.callback_query(OrderStates.deleting_photos, F.data.startswith("preview_photo:"))
async def preview_photo(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Переход к другому фото для превью."""
    idx = int(callback.data.split(":")[1])
    data = await state.get_data()
    order_id = data.get("order_id")
    current_idx = data.get("delete_photo_idx", 0)
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order or not order.photos:
            await callback.answer("Фото не найдены")
            return
        
        if idx < 0 or idx >= len(order.photos):
            await callback.answer("Фото не найдено")
            return
        
        await state.update_data(delete_photo_idx=idx)
        
        photo = order.photos[idx]
        current_photo = order.photos[current_idx] if current_idx < len(order.photos) else None
        
        # Если тип файла совпадает, можно использовать edit_media
        if current_photo and current_photo.is_document == photo.is_document:
            media_class = InputMediaDocument if photo.is_document else InputMediaPhoto
            await callback.message.edit_media(
                media=media_class(
                    media=photo.telegram_file_id,
                    caption=_get_photo_caption(photo, idx, len(order.photos)),
                    parse_mode="HTML",
                ),
                reply_markup=get_photo_preview_keyboard(photo, idx, len(order.photos)),
            )
        else:
            # Типы разные — удаляем и отправляем заново
            await callback.message.delete()
            await _send_photo_preview(bot, callback.from_user.id, photo, idx, len(order.photos))
    
    await callback.answer()


@router.callback_query(OrderStates.deleting_photos, F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    """Пустой обработчик для кнопки-счётчика."""
    await callback.answer()


@router.callback_query(OrderStates.deleting_photos, F.data.startswith("delete_photo:"))
async def delete_photo(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Удаление конкретного фото."""
    photo_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    order_id = data.get("order_id")
    current_idx = data.get("delete_photo_idx", 0)
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await callback.answer("Заказ не найден")
            return
        
        # Запоминаем тип текущего фото для сравнения
        current_photo = order.photos[current_idx] if current_idx < len(order.photos) else None
        current_is_document = current_photo.is_document if current_photo else False
        
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
            # Все фото удалены
            await callback.message.delete()
            await bot.send_message(
                chat_id=callback.from_user.id,
                text="Все фото удалены. Выберите формат для добавления новых:",
                reply_markup=get_format_keyboard(),
            )
            await state.set_state(OrderStates.selecting_format)
        else:
            # Корректируем индекс если нужно
            if current_idx >= len(order.photos):
                current_idx = len(order.photos) - 1
            
            await state.update_data(delete_photo_idx=current_idx)
            
            photo = order.photos[current_idx]
            extra_text = f"✅ Фото удалено! Осталось: {len(order.photos)}"
            
            # Если тип файла совпадает, можно использовать edit_media
            if current_is_document == photo.is_document:
                media_class = InputMediaDocument if photo.is_document else InputMediaPhoto
                await callback.message.edit_media(
                    media=media_class(
                        media=photo.telegram_file_id,
                        caption=_get_photo_caption(photo, current_idx, len(order.photos), extra_text),
                        parse_mode="HTML",
                    ),
                    reply_markup=get_photo_preview_keyboard(photo, current_idx, len(order.photos)),
                )
            else:
                # Типы разные — удаляем и отправляем заново
                await callback.message.delete()
                await _send_photo_preview(
                    bot, callback.from_user.id, photo, current_idx, len(order.photos), extra_text
                )


@router.callback_query(OrderStates.deleting_photos, F.data == "finish_deleting")
async def finish_deleting(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Завершение удаления фото."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if order and order.photos_count >= MIN_PHOTOS:
            # Удаляем сообщение с фото
            await callback.message.delete()
            # Отправляем сводку
            await show_order_summary_new(bot, callback.from_user.id, order)
            await state.set_state(OrderStates.reviewing_order)
        elif order and order.photos_count > 0:
            await callback.answer(
                f"Минимальный заказ {MIN_PHOTOS} фото. "
                f"Сейчас: {order.photos_count}",
                show_alert=True,
            )
            return
        else:
            await callback.message.delete()
            await bot.send_message(
                chat_id=callback.from_user.id,
                text="Выберите формат фотографий:",
                reply_markup=get_format_keyboard(),
            )
            await state.set_state(OrderStates.selecting_format)
    
    await callback.answer()


async def show_order_summary_new(bot: Bot, chat_id: int, order):
    """Отправляет новое сообщение со сводкой заказа."""
    photos_by_format = order.photos_by_format()
    
    lines = ["<b>📋 Ваш заказ:</b>\n"]
    
    for fmt, count in photos_by_format.items():
        lines.append(f"• {fmt.short_name}: {count} шт.")
    
    lines.append(f"\nВсего фото: <b>{order.photos_count}</b> шт.")
    
    cost = PricingService.calculate_total_cost(photos_by_format)
    lines.append(f"\n💰 Предварительная стоимость (без доставки): <b>{cost}₽</b>")
    
    hint = PricingService.get_price_optimization_hint(photos_by_format)
    if hint:
        lines.append(f"\n{hint}")
    
    text = "\n".join(lines)
    
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=get_order_summary_keyboard(),
        parse_mode="HTML",
    )

