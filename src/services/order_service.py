"""Сервис управления заказами."""
import random
import string
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import select, update, func, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.user import User
from src.models.order import Order, OrderStatus, DeliveryType
from src.models.photo import Photo, PhotoFormat
from src.models.promocode import Promocode
from src.services.pricing import PricingService


class OrderService:
    """Сервис для работы с заказами."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    @staticmethod
    def generate_order_number() -> str:
        """Генерирует уникальный номер заказа."""
        # Формат: YYMMDD-XXXX (дата + 4 случайных символа)
        date_part = datetime.now().strftime("%y%m%d")
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"{date_part}-{random_part}"
    
    # === Работа с пользователями ===
    
    async def get_or_create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        """Получает или создаёт пользователя по Telegram ID."""
        query = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        
        if user:
            # Обновляем данные пользователя
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            await self.session.commit()
            return user
        
        # Создаём нового пользователя
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user
    
    # === Работа с заказами ===
    
    async def create_order(self, user: User) -> Order:
        """Создаёт новый заказ-черновик."""
        order = Order(
            user_id=user.id,
            order_number=self.generate_order_number(),
            status=OrderStatus.DRAFT,
        )
        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)
        return order
    
    async def get_order_by_id(self, order_id: int) -> Optional[Order]:
        """Получает заказ по ID."""
        query = select(Order).where(Order.id == order_id).options(
            selectinload(Order.photos),
            selectinload(Order.user),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_order_by_number(self, order_number: str) -> Optional[Order]:
        """Получает заказ по номеру."""
        query = select(Order).where(Order.order_number == order_number).options(
            selectinload(Order.photos),
            selectinload(Order.user),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_user_draft_order(self, user: User) -> Optional[Order]:
        """Получает последний заказ-черновик пользователя."""
        query = (
            select(Order)
            .where(Order.user_id == user.id, Order.status == OrderStatus.DRAFT)
            .options(selectinload(Order.photos))
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_user_orders(self, user: User, limit: int = 10) -> List[Order]:
        """Получает список заказов пользователя."""
        query = (
            select(Order)
            .where(Order.user_id == user.id, Order.status != OrderStatus.DRAFT)
            .options(selectinload(Order.photos))
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_orders_by_status(self, status: OrderStatus) -> List[Order]:
        """Получает все заказы с указанным статусом."""
        query = (
            select(Order)
            .where(Order.status == status)
            .options(selectinload(Order.photos), selectinload(Order.user))
            .order_by(Order.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_all_orders(self, limit: int = 100, offset: int = 0) -> List[Order]:
        """Получает все заказы (для админки)."""
        query = (
            select(Order)
            .where(Order.status != OrderStatus.DRAFT)
            .options(selectinload(Order.photos), selectinload(Order.user))
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def search_orders(
        self,
        search: Optional[str] = None,
        status: Optional[OrderStatus] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[Order], int]:
        """Поиск и фильтрация заказов с пагинацией. Возвращает (orders, total_count)."""
        from sqlalchemy import func, or_
        
        # Базовый запрос
        base_query = select(Order).where(Order.status != OrderStatus.DRAFT)
        count_query = select(func.count(Order.id)).where(Order.status != OrderStatus.DRAFT)
        
        # Фильтр по статусу
        if status:
            base_query = base_query.where(Order.status == status)
            count_query = count_query.where(Order.status == status)
        
        # Фильтр по дате
        if date_from:
            base_query = base_query.where(Order.created_at >= date_from)
            count_query = count_query.where(Order.created_at >= date_from)
        
        if date_to:
            # Добавляем время до конца дня
            date_to_end = date_to.replace(hour=23, minute=59, second=59)
            base_query = base_query.where(Order.created_at <= date_to_end)
            count_query = count_query.where(Order.created_at <= date_to_end)
        
        # Поиск по номеру заказа или username
        if search:
            search_term = f"%{search}%"
            base_query = base_query.join(User, Order.user_id == User.id).where(
                or_(
                    Order.order_number.ilike(search_term),
                    User.username.ilike(search_term),
                    User.first_name.ilike(search_term),
                )
            )
            count_query = count_query.join(User, Order.user_id == User.id).where(
                or_(
                    Order.order_number.ilike(search_term),
                    User.username.ilike(search_term),
                    User.first_name.ilike(search_term),
                )
            )
        
        # Получаем общее количество
        total_result = await self.session.execute(count_query)
        total_count = total_result.scalar() or 0
        
        # Получаем заказы с пагинацией
        orders_query = (
            base_query
            .options(selectinload(Order.photos), selectinload(Order.user))
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        result = await self.session.execute(orders_query)
        orders = list(result.scalars().all())
        
        return orders, total_count
    
    async def delete_old_drafts(self, days: int = 7) -> int:
        """Удаляет черновики старше указанного количества дней. Возвращает количество удалённых."""
        from sqlalchemy import delete
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Сначала считаем
        count_query = select(func.count(Order.id)).where(
            Order.status == OrderStatus.DRAFT,
            Order.created_at < cutoff_date
        )
        count_result = await self.session.execute(count_query)
        count = count_result.scalar() or 0
        
        # Удаляем
        delete_query = delete(Order).where(
            Order.status == OrderStatus.DRAFT,
            Order.created_at < cutoff_date
        )
        await self.session.execute(delete_query)
        await self.session.commit()
        
        return count
    
    async def update_order_status(self, order: Order, status: OrderStatus) -> Order:
        """Обновляет статус заказа."""
        order.status = status
        
        if status == OrderStatus.PAID:
            order.paid_at = datetime.now()
        
        await self.session.commit()
        await self.session.refresh(order)
        return order
    
    async def set_delivery_info(
        self,
        order: Order,
        delivery_type: DeliveryType,
        city: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        delivery_datetime: Optional[str] = None,
    ) -> Order:
        """Устанавливает информацию о доставке."""
        order.delivery_type = delivery_type
        order.delivery_city = city
        order.delivery_address = address
        order.delivery_phone = phone
        order.delivery_datetime = delivery_datetime
        order.delivery_cost = delivery_type.delivery_cost
        
        await self.session.commit()
        await self.session.refresh(order)
        return order
    
    async def recalculate_order_cost(self, order: Order) -> Order:
        """Пересчитывает стоимость заказа."""
        photos_by_format = order.photos_by_format()
        order.photos_cost = PricingService.calculate_total_cost(photos_by_format)
        
        await self.session.commit()
        await self.session.refresh(order)
        return order
    
    # === Работа с фотографиями ===
    
    async def add_photo(
        self,
        order: Order,
        photo_format: PhotoFormat,
        telegram_file_id: str,
        local_path: Optional[str] = None,
        is_document: bool = False,
        thumbnail_file_id: Optional[str] = None,
        auto_crop_data: Optional[str] = None,
        crop_confidence: Optional[float] = None,
        crop_method: Optional[str] = None,
        faces_found: int = 0,
    ) -> Photo:
        """Добавляет фотографию в заказ."""
        # Определяем позицию
        position = len(order.photos) if order.photos else 0
        
        photo = Photo(
            order_id=order.id,
            format=photo_format,
            telegram_file_id=telegram_file_id,
            local_path=local_path,
            position=position,
            is_document=is_document,
            thumbnail_file_id=thumbnail_file_id,
            auto_crop_data=auto_crop_data,
            crop_confidence=crop_confidence,
            crop_method=crop_method,
            faces_found=faces_found,
        )
        self.session.add(photo)
        await self.session.commit()
        
        # Пересчитываем стоимость
        await self.session.refresh(order)
        await self.recalculate_order_cost(order)
        
        return photo
    
    async def remove_photo(self, photo: Photo) -> None:
        """Удаляет фотографию из заказа."""
        order_id = photo.order_id
        await self.session.delete(photo)
        await self.session.commit()
        
        # Пересчитываем стоимость
        order = await self.get_order_by_id(order_id)
        if order:
            await self.recalculate_order_cost(order)
    
    async def get_order_photos(self, order: Order) -> List[Photo]:
        """Получает все фотографии заказа."""
        query = (
            select(Photo)
            .where(Photo.order_id == order.id)
            .order_by(Photo.position)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_photo_by_id(self, photo_id: int) -> Optional[Photo]:
        """Получает фото по ID."""
        query = select(Photo).where(Photo.id == photo_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def update_photo_crop(
        self,
        photo_id: int,
        crop_data: str,
        crop_confirmed: bool = True,
    ) -> Optional[Photo]:
        """Обновляет данные кадрирования фото."""
        photo = await self.get_photo_by_id(photo_id)
        if not photo:
            return None
        
        photo.crop_data = crop_data
        photo.crop_confirmed = crop_confirmed
        
        await self.session.commit()
        await self.session.refresh(photo)
        return photo
    
    # === Работа с промокодами ===
    
    async def get_promocode(self, code: str) -> Optional[Promocode]:
        """Получает промокод по коду."""
        query = select(Promocode).where(
            Promocode.code == code.upper().strip()
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def apply_promocode(self, order: Order, promocode: Promocode) -> Order:
        """Применяет промокод к заказу."""
        discount = promocode.calculate_discount(order.photos_cost)
        order.promocode_id = promocode.id
        order.discount = discount
        
        # Увеличиваем счётчик использований
        promocode.current_uses += 1
        
        await self.session.commit()
        await self.session.refresh(order)
        return order
    
    async def create_promocode(
        self,
        code: str,
        discount_percent: Optional[int] = None,
        discount_amount: Optional[int] = None,
        description: Optional[str] = None,
        max_uses: Optional[int] = None,
    ) -> Promocode:
        """Создаёт новый промокод."""
        promocode = Promocode(
            code=code.upper().strip(),
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            description=description,
            max_uses=max_uses,
        )
        self.session.add(promocode)
        await self.session.commit()
        await self.session.refresh(promocode)
        return promocode

