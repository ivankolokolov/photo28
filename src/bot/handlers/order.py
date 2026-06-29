"""Обработчики заказа и фотографий."""
import asyncio
import logging
from typing import Dict, List
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, BufferedInputFile
from aiogram.fsm.context import FSMContext

from src.bot.states import OrderStates
from src.bot.context import StudioContext
from src.bot.keyboards import (
    get_format_keyboard,
    get_subcategory_keyboard,
    get_photo_actions_keyboard,
    get_order_summary_keyboard,
    get_photo_preview_keyboard,
    get_crop_option_keyboard,
)
from src.database import async_session
from src.services.order_service import OrderService
from src.services.pricing import PricingService
from src.services.settings_service import SettingKeys
from src.models.photo import Photo

logger = logging.getLogger(__name__)

# Словарь для отслеживания media_group
_media_groups: Dict[str, dict] = {}
_single_photo_tasks: Dict[int, dict] = {}

UPLOAD_MESSAGE = """📸 Пожалуйста, ознакомьтесь с тем, как будут кадрироваться фото:
https://dariakis28.ru/kadrirovanie-fotografiy

Вы выбрали формат: <b>{format_name}</b>

Пришлите мне фото. Чтобы сохранить качество — присылайте файлами "без сжатия" 📎"""

def get_min_photos(ctx: StudioContext) -> int:
    """Получает минимальное количество фото из настроек студии."""
    return ctx.settings.get_int(SettingKeys.MIN_PHOTOS, 10)

async def analyze_photos_for_crop(
    bot: Bot,
    photos: List[Photo],
    session,
    ctx: StudioContext,
) -> tuple:
    """Анализирует фото для умного кропа."""
    from src.services.smart_crop_service import get_smart_crop_service, SmartCropService

    if not ctx.settings.get_bool(SettingKeys.SMART_CROP_ENABLED, True):
        return len(photos), 0, 0

    if not SmartCropService.is_available():
        logger.warning("SmartCropService недоступен (OpenCV не установлен)")
        return len(photos), 0, 0

    face_priority = ctx.settings.get_int(SettingKeys.CROP_FACE_PRIORITY, 80)
    confidence_threshold = ctx.settings.get_int(SettingKeys.CROP_CONFIDENCE_THRESHOLD, 85) / 100.0

    crop_service = get_smart_crop_service(face_priority)

    auto_approved = 0
    needs_review = 0

    for photo in photos:
        if photo.auto_crop_data:
            if photo.crop_confidence and photo.crop_confidence >= confidence_threshold:
                auto_approved += 1
            else:
                needs_review += 1
            continue

        try:
            file = await bot.get_file(photo.telegram_file_id)
            photo_bytes = await bot.download_file(file.file_path)
            image_data = photo_bytes.read()

            # Получаем aspect_ratio из продукта
            product = ctx.products.get(photo.product_id)
            aspect_ratio = product.aspect_ratio if product and product.aspect_ratio else 0.76

            result = crop_service.analyze_photo(image_data, aspect_ratio=aspect_ratio)

            photo.auto_crop_data = result.to_json()
            photo.crop_confidence = result.confidence
            photo.crop_method = result.method
            photo.faces_found = result.faces_found

            if result.confidence >= confidence_threshold:
                auto_approved += 1
            else:
                needs_review += 1

        except Exception as e:
            logger.error(f"Ошибка анализа фото {photo.id}: {e}")
            needs_review += 1

    await session.commit()

    return len(photos), auto_approved, needs_review

# === Выбор формата (двухуровневый) ===

async def select_format_category(callback: CallbackQuery, state: FSMContext, ctx: StudioContext):
    """Выбор категории формата — показываем варианты."""
    cat_id = int(callback.data.split(":")[1])
    product = ctx.products.get(cat_id)

    if not product:
        await callback.answer("Формат не найден")
        return

    children = ctx.products.children(cat_id)

    text = f"{product.emoji} <b>{product.name}</b>\n\nВыберите вариант:"
    if product.description:
        text = f"{product.emoji} <b>{product.name}</b>\n{product.description}\n\nВыберите вариант:"

    await callback.message.edit_text(
        text,
        reply_markup=get_subcategory_keyboard(cat_id, ctx),
        parse_mode="HTML",
    )
    await callback.answer()

async def back_to_formats(callback: CallbackQuery, state: FSMContext, ctx: StudioContext):
    """Возврат к списку форматов."""
    await callback.message.edit_text(
        "Выберите формат фотографий:",
        reply_markup=get_format_keyboard(ctx),
    )
    await state.set_state(OrderStates.selecting_format)
    await callback.answer()

async def select_format(callback: CallbackQuery, state: FSMContext, ctx: StudioContext):
    """Выбор конкретного формата фотографий."""
    product_id = int(callback.data.split(":")[1])
    product = ctx.products.get(product_id)

    if not product:
        await callback.answer("Формат не найден")
        return

    await state.update_data(current_product_id=product_id)

    # Получаем текущий заказ для отображения кнопок
    data = await state.get_data()
    order_id = data.get("order_id")

    has_photos = False
    order = await ctx.orders.get_order_by_id(order_id)
    if order and order.photos:
        has_photos = True

    # Формируем название с учётом родителя
    format_name = product.name
    if product.parent_id:
        parent = ctx.products.get(product.parent_id)
        if parent:
            format_name = f"{parent.name} — {product.name}"

    await callback.message.edit_text(
        UPLOAD_MESSAGE.format(format_name=format_name),
        reply_markup=get_photo_actions_keyboard(has_photos),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    await state.set_state(OrderStates.uploading_photos)
    await callback.answer()

# === Загрузка фото ===

async def _send_media_group_confirmation(bot: Bot, media_group_id: str, studio_id: int):
    """Отправляет сообщение о добавленных фото из альбома."""
    await asyncio.sleep(0.5)

    group_info = _media_groups.pop(media_group_id, None)
    if not group_info:
        return

    user_id = group_info["user_id"]
    order_id = group_info["order_id"]
    added_count = group_info.get("count", 1)

    async with async_session() as session:
        service = OrderService(session, studio_id)
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

async def _send_single_photo_confirmation(bot: Bot, user_id: int, order_id: int, studio_id: int):
    """Отправляет сообщение о добавленном одиночном фото."""
    await asyncio.sleep(0.3)

    single_info = _single_photo_tasks.pop(user_id, None)
    if not single_info:
        return

    added_count = single_info.get("count", 1)

    async with async_session() as session:
        service = OrderService(session, studio_id)
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
    ctx: StudioContext,
    is_document: bool = False,
    thumbnail_file_id: str = None,
):
    """Добавляет фото в заказ и планирует отправку подтверждения."""
    data = await state.get_data()
    order_id = data.get("order_id")
    product_id = data.get("current_product_id")
    user_id = message.from_user.id
    media_group_id = message.media_group_id

    if not order_id or not product_id:
        await message.answer("Ошибка. Пожалуйста, начните заново: /start")
        return

    order = await ctx.orders.get_order_by_id(order_id)

    if not order:
        await message.answer("Заказ не найден. Начните заново: /start")
        return

    await ctx.orders.add_photo(
        order, product_id, file_id,
        is_document=is_document,
        thumbnail_file_id=thumbnail_file_id,
    )

    # Если это фото из альбома (media_group)
    if media_group_id:
        if media_group_id in _media_groups:
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

        task = asyncio.create_task(
            _send_media_group_confirmation(bot, media_group_id, ctx.studio_id)
        )
        _media_groups[media_group_id]["task"] = task
    else:
        if user_id in _single_photo_tasks:
            old_task = _single_photo_tasks[user_id].get("task")
            if old_task and not old_task.done():
                old_task.cancel()
            _single_photo_tasks[user_id]["count"] += 1
        else:
            _single_photo_tasks[user_id] = {"count": 1}

        task = asyncio.create_task(
            _send_single_photo_confirmation(bot, user_id, order_id, ctx.studio_id)
        )
        _single_photo_tasks[user_id]["task"] = task

async def handle_photo(message: Message, state: FSMContext, bot: Bot, ctx: StudioContext):
    """Обработка загруженного фото (сжатого)."""
    file_id = message.photo[-1].file_id
    thumb_idx = min(1, len(message.photo) - 1)
    thumbnail_file_id = message.photo[thumb_idx].file_id
    await _add_photo_to_batch(message, state, bot, file_id, ctx, is_document=False, thumbnail_file_id=thumbnail_file_id)

async def handle_document(message: Message, state: FSMContext, bot: Bot, ctx: StudioContext):
    """Обработка загруженного документа (без сжатия)."""
    mime_type = message.document.mime_type or ""
    if not mime_type.startswith("image/"):
        await message.answer(
            "⚠️ Пожалуйста, отправляйте только изображения.\n"
            "Поддерживаемые форматы: JPG, PNG, HEIC"
        )
        return

    file_id = message.document.file_id
    thumbnail_file_id = message.document.thumbnail.file_id if message.document.thumbnail else None
    await _add_photo_to_batch(message, state, bot, file_id, ctx, is_document=True, thumbnail_file_id=thumbnail_file_id)

async def handle_video_rejected(message: Message):
    """Отклонение видео."""
    await message.answer(
        "⚠️ Видео не поддерживается.\n"
        "Пожалуйста, отправляйте только фотографии (JPG, PNG, HEIC)."
    )

async def handle_audio_rejected(message: Message):
    """Отклонение аудио."""
    await message.answer(
        "⚠️ Аудио не поддерживается.\n"
        "Пожалуйста, отправляйте только фотографии."
    )

async def handle_sticker_rejected(message: Message):
    """Отклонение стикеров."""
    await message.answer(
        "⚠️ Стикеры не поддерживаются.\n"
        "Пожалуйста, отправляйте фотографии."
    )

async def handle_text_in_upload(message: Message):
    """Текст в режиме загрузки фото."""
    await message.answer(
        "📷 Сейчас я жду фотографии.\n"
        "Отправьте фото или нажмите кнопку ниже.",
        reply_markup=get_photo_actions_keyboard(has_photos=True),
    )

async def add_another_format(callback: CallbackQuery, state: FSMContext, ctx: StudioContext):
    """Добавить фото другого формата."""
    await callback.message.edit_text(
        "Выберите формат для следующих фотографий:",
        reply_markup=get_format_keyboard(ctx),
    )

    await state.set_state(OrderStates.selecting_format)
    await callback.answer()

async def finish_photos(callback: CallbackQuery, state: FSMContext, bot: Bot, ctx: StudioContext):
    """Завершение отбора фото."""
    data = await state.get_data()
    order_id = data.get("order_id")

    order = await ctx.orders.get_order_by_id(order_id)

    if not order:
        await callback.answer("Заказ не найден")
        return

    min_photos = get_min_photos(ctx)
    if order.photos_count < min_photos:
        await callback.answer(
            f"Минимальный заказ {min_photos} фото любого формата.",
            show_alert=True,
        )
        return

    # Проверяем настройки кропа
    crop_enabled = ctx.settings.get_bool(SettingKeys.CROP_ENABLED, True)
    smart_crop_enabled = ctx.settings.get_bool(SettingKeys.SMART_CROP_ENABLED, True)
    crop_show_mode = ctx.settings.get(SettingKeys.CROP_SHOW_EDITOR, "problems_only")

    if crop_enabled and smart_crop_enabled:
        await callback.message.edit_text(
            f"🔍 Анализирую {order.photos_count} фото...\n"
            "Определяю лица и важные области для кадрирования."
        )

        total, auto_approved, needs_review = await analyze_photos_for_crop(
            bot, order.photos, ctx.session, ctx
        )

        show_editor = False
        if crop_show_mode == "always":
            show_editor = True
        elif crop_show_mode == "problems_only" and needs_review > 0:
            show_editor = True

        if show_editor:
            if needs_review > 0:
                text = (
                    f"✅ Анализ завершён!\n\n"
                    f"📊 Результат:\n"
                    f"• Готовы к печати: {auto_approved} фото\n"
                    f"• Требуют внимания: {needs_review} фото\n\n"
                    f"Рекомендуем проверить кадрирование."
                )
            else:
                text = (
                    f"✅ Все {total} фото готовы к печати!\n\n"
                    f"Авто-кадрирование определило оптимальные области.\n"
                    f"Вы можете проверить и скорректировать при желании."
                )

            await callback.message.edit_text(
                text,
                reply_markup=get_crop_option_keyboard(order_id)
            )
            await state.set_state(OrderStates.editing_crop)
            await callback.answer()
            return

    await show_order_summary(callback.message, order, ctx, edit=True)

    await state.set_state(OrderStates.reviewing_order)
    await callback.answer()

# === Сводка заказа ===

async def show_order_summary(message, order, ctx: StudioContext, edit: bool = False):
    """Отображает сводку заказа."""
    photos_by_product = order.photos_by_product()

    lines = ["<b>📋 Ваш заказ:</b>\n"]

    for product_id, count in photos_by_product.items():
        product = ctx.products.get(product_id)
        if product:
            name = product.short_name
            if product.parent_id:
                parent = ctx.products.get(product.parent_id)
                if parent:
                    name = f"{parent.short_name} {product.short_name}"
        else:
            name = f"Товар #{product_id}"
        lines.append(f"• {name}: {count} шт.")

    lines.append(f"\nВсего фото: <b>{order.photos_count}</b> шт.")

    cost = PricingService.calculate_total_cost(ctx.studio_id, photos_by_product)
    lines.append(f"\n💰 Предварительная стоимость (без доставки): <b>{cost}₽</b>")

    hint = PricingService.get_price_optimization_hint(ctx.studio_id, photos_by_product)
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

async def show_order_summary_new(bot: Bot, chat_id: int, order, ctx: StudioContext):
    """Отправляет новое сообщение со сводкой заказа."""
    photos_by_product = order.photos_by_product()

    lines = ["<b>📋 Ваш заказ:</b>\n"]

    for product_id, count in photos_by_product.items():
        product = ctx.products.get(product_id)
        if product:
            name = product.short_name
            if product.parent_id:
                parent = ctx.products.get(product.parent_id)
                if parent:
                    name = f"{parent.short_name} {product.short_name}"
        else:
            name = f"Товар #{product_id}"
        lines.append(f"• {name}: {count} шт.")

    lines.append(f"\nВсего фото: <b>{order.photos_count}</b> шт.")

    cost = PricingService.calculate_total_cost(ctx.studio_id, photos_by_product)
    lines.append(f"\n💰 Предварительная стоимость (без доставки): <b>{cost}₽</b>")

    hint = PricingService.get_price_optimization_hint(ctx.studio_id, photos_by_product)
    if hint:
        lines.append(f"\n{hint}")

    text = "\n".join(lines)

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=get_order_summary_keyboard(),
        parse_mode="HTML",
    )

# === Навигация ===

async def back_to_photos(callback: CallbackQuery, state: FSMContext, ctx: StudioContext):
    """Возврат к сводке заказа."""
    data = await state.get_data()
    order_id = data.get("order_id")

    order = await ctx.orders.get_order_by_id(order_id)

    if order and order.photos_count > 0:
        await show_order_summary(callback.message, order, ctx, edit=True)
        await state.set_state(OrderStates.reviewing_order)
    else:
        await callback.message.edit_text(
            "Выберите формат фотографий:",
            reply_markup=get_format_keyboard(ctx),
        )
        await state.set_state(OrderStates.selecting_format)

    await callback.answer()

async def back_to_summary(callback: CallbackQuery, state: FSMContext, ctx: StudioContext):
    """Возврат к сводке заказа."""
    data = await state.get_data()
    order_id = data.get("order_id")

    order = await ctx.orders.get_order_by_id(order_id)

    if order:
        await show_order_summary(callback.message, order, ctx, edit=True)

    await state.set_state(OrderStates.reviewing_order)
    await callback.answer()

# === Удаление фото ===

def _get_photo_caption(photo, idx: int, total: int, ctx: StudioContext, extra_text: str = "") -> str:
    """Формирует подпись для фото при удалении."""
    min_photos = get_min_photos(ctx)

    product = ctx.products.get(photo.product_id)
    product_name = product.short_name if product else "Неизвестный формат"

    caption = (
        f"🗑 <b>Удаление фото</b>\n\n"
        f"Фото {idx + 1} из {total}\n"
        f"Формат: {product_name}"
    )

    if total <= min_photos:
        caption += f"\n\n⚠️ Минимальный заказ: {min_photos} фото"

    if extra_text:
        caption += f"\n\n{extra_text}"
    return caption

async def _send_photo_preview(bot: Bot, chat_id: int, photo, idx: int, total: int, ctx: StudioContext, extra_text: str = ""):
    """Отправляет превью фото."""
    caption = _get_photo_caption(photo, idx, total, ctx, extra_text)
    keyboard = get_photo_preview_keyboard(photo.id, idx, total)

    preview_mode = ctx.settings.get(SettingKeys.PREVIEW_MODE, "thumbnail")

    if photo.is_document:
        if preview_mode == "thumbnail" and photo.thumbnail_file_id:
            try:
                file = await bot.get_file(photo.thumbnail_file_id)
                file_data = await bot.download_file(file.file_path)
                photo_input = BufferedInputFile(file_data.read(), filename="preview.jpg")
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_input,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
                return
            except Exception:
                pass

        await bot.send_document(
            chat_id=chat_id,
            document=photo.telegram_file_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        preview_file_id = photo.thumbnail_file_id or photo.telegram_file_id
        await bot.send_photo(
            chat_id=chat_id,
            photo=preview_file_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )

async def start_delete_photos(callback: CallbackQuery, state: FSMContext, bot: Bot, ctx: StudioContext):
    """Начало удаления фото."""
    data = await state.get_data()
    order_id = data.get("order_id")

    order = await ctx.orders.get_order_by_id(order_id)

    if not order or not order.photos:
        await callback.answer("Нет фото для удаления")
        return

    await state.update_data(delete_photo_idx=0)
    await callback.message.delete()

    photo = order.photos[0]
    await _send_photo_preview(bot, callback.from_user.id, photo, 0, len(order.photos), ctx)

    await state.set_state(OrderStates.deleting_photos)
    await callback.answer()

async def preview_photo(callback: CallbackQuery, state: FSMContext, bot: Bot, ctx: StudioContext):
    """Переход к другому фото для превью."""
    idx = int(callback.data.split(":")[1])
    data = await state.get_data()
    order_id = data.get("order_id")

    order = await ctx.orders.get_order_by_id(order_id)

    if not order or not order.photos:
        await callback.answer("Фото не найдены")
        return

    if idx < 0 or idx >= len(order.photos):
        await callback.answer("Фото не найдено")
        return

    await state.update_data(delete_photo_idx=idx)

    photo = order.photos[idx]
    current_idx = data.get("delete_photo_idx", 0)
    current_photo = order.photos[current_idx] if current_idx < len(order.photos) else None

    same_type = current_photo and (current_photo.is_document == photo.is_document)
    if same_type and not photo.is_document:
        preview_file_id = photo.thumbnail_file_id or photo.telegram_file_id
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=preview_file_id,
                caption=_get_photo_caption(photo, idx, len(order.photos), ctx),
                parse_mode="HTML",
            ),
            reply_markup=get_photo_preview_keyboard(photo.id, idx, len(order.photos)),
        )
    else:
        await callback.message.delete()
        await _send_photo_preview(bot, callback.from_user.id, photo, idx, len(order.photos), ctx)

    await callback.answer()

async def nav_disabled_handler(callback: CallbackQuery):
    """Неактивная кнопка навигации."""
    await callback.answer()

async def delete_photo(callback: CallbackQuery, state: FSMContext, bot: Bot, ctx: StudioContext):
    """Удаление конкретного фото."""
    photo_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    order_id = data.get("order_id")
    current_idx = data.get("delete_photo_idx", 0)

    order = await ctx.orders.get_order_by_id(order_id)

    if not order:
        await callback.answer("Заказ не найден")
        return

    photo_to_delete = None
    for photo in order.photos:
        if photo.id == photo_id:
            photo_to_delete = photo
            break

    if photo_to_delete:
        await ctx.orders.remove_photo(photo_to_delete)
        await callback.answer("Фото удалено ✓")

    order = await ctx.orders.get_order_by_id(order_id)

    if not order.photos:
        await callback.message.delete()
        await bot.send_message(
            chat_id=callback.from_user.id,
            text="Все фото удалены. Выберите формат для добавления новых:",
            reply_markup=get_format_keyboard(ctx),
        )
        await state.set_state(OrderStates.selecting_format)
    else:
        if current_idx >= len(order.photos):
            current_idx = len(order.photos) - 1

        await state.update_data(delete_photo_idx=current_idx)

        photo = order.photos[current_idx]
        extra_text = f"✅ Фото удалено! Осталось: {len(order.photos)}"

        if not photo.is_document:
            preview_file_id = photo.thumbnail_file_id or photo.telegram_file_id
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=preview_file_id,
                    caption=_get_photo_caption(photo, current_idx, len(order.photos), ctx, extra_text),
                    parse_mode="HTML",
                ),
                reply_markup=get_photo_preview_keyboard(photo.id, current_idx, len(order.photos)),
            )
        else:
            await callback.message.delete()
            await _send_photo_preview(
                bot, callback.from_user.id, photo, current_idx, len(order.photos), ctx, extra_text
            )

async def finish_deleting(callback: CallbackQuery, state: FSMContext, bot: Bot, ctx: StudioContext):
    """Завершение удаления фото."""
    data = await state.get_data()
    order_id = data.get("order_id")

    order = await ctx.orders.get_order_by_id(order_id)

    min_photos = get_min_photos(ctx)
    if order and order.photos_count >= min_photos:
        await callback.message.delete()
        await show_order_summary_new(bot, callback.from_user.id, order, ctx)
        await state.set_state(OrderStates.reviewing_order)
    elif order and order.photos_count > 0:
        await callback.message.delete()
        need_more = min_photos - order.photos_count
        await bot.send_message(
            chat_id=callback.from_user.id,
            text=f"⚠️ Минимальный заказ: <b>{min_photos}</b> фото.\n"
                 f"У вас: <b>{order.photos_count}</b>. Нужно ещё: <b>{need_more}</b>\n\n"
                 f"Выберите формат для добавления:",
            reply_markup=get_format_keyboard(ctx),
            parse_mode="HTML",
        )
        await state.set_state(OrderStates.selecting_format)
    else:
        await callback.message.delete()
        await bot.send_message(
            chat_id=callback.from_user.id,
            text="Выберите формат фотографий:",
            reply_markup=get_format_keyboard(ctx),
        )
        await state.set_state(OrderStates.selecting_format)

    await callback.answer()

def build_order_router() -> Router:
    r = Router(name="order")
    r.callback_query.register(select_format_category, F.data.startswith("format_cat:"))
    r.callback_query.register(back_to_formats, F.data == "back_to_formats")
    r.callback_query.register(select_format, F.data.startswith("format:"))
    r.message.register(handle_photo, OrderStates.uploading_photos, F.photo)
    r.message.register(handle_document, OrderStates.uploading_photos, F.document)
    r.message.register(handle_video_rejected, OrderStates.uploading_photos, F.video | F.video_note | F.animation)
    r.message.register(handle_audio_rejected, OrderStates.uploading_photos, F.audio | F.voice)
    r.message.register(handle_sticker_rejected, OrderStates.uploading_photos, F.sticker)
    r.message.register(handle_text_in_upload, OrderStates.uploading_photos, F.text)
    r.callback_query.register(add_another_format, F.data == "add_another_format")
    r.callback_query.register(finish_photos, F.data == "finish_photos")
    r.callback_query.register(back_to_photos, F.data == "back_to_photos")
    r.callback_query.register(back_to_summary, F.data == "back_to_summary")
    r.callback_query.register(start_delete_photos, F.data == "delete_photos")
    r.callback_query.register(preview_photo, OrderStates.deleting_photos, F.data.startswith("preview_photo:"))
    r.callback_query.register(nav_disabled_handler, OrderStates.deleting_photos, F.data == "nav_disabled")
    r.callback_query.register(delete_photo, OrderStates.deleting_photos, F.data.startswith("delete_photo:"))
    r.callback_query.register(finish_deleting, OrderStates.deleting_photos, F.data == "finish_deleting")
    return r
