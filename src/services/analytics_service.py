"""Сервис аналитики."""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.order import Order, OrderStatus
from src.models.photo import Photo, PhotoFormat
from src.models.user import User


class AnalyticsService:
    """Сервис для сбора аналитики."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_revenue_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Статистика по выручке."""
        # По умолчанию — текущий месяц
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Статусы, которые считаем "оплаченными"
        paid_statuses = [
            OrderStatus.PAID,
            OrderStatus.CONFIRMED,
            OrderStatus.PRINTING,
            OrderStatus.READY,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ]
        
        # Общая выручка за период
        # total_cost = photos_cost + delivery_cost - discount (это property, не колонка)
        total_expr = Order.photos_cost + Order.delivery_cost - Order.discount
        
        query = select(
            func.count(Order.id).label("orders_count"),
            func.coalesce(func.sum(total_expr), 0).label("total_revenue"),
            func.coalesce(func.sum(Order.photos_cost), 0).label("photos_revenue"),
            func.coalesce(func.sum(Order.delivery_cost), 0).label("delivery_revenue"),
            func.coalesce(func.sum(Order.discount), 0).label("total_discount"),
            func.coalesce(func.avg(total_expr), 0).label("avg_check"),
        ).where(
            and_(
                Order.status.in_(paid_statuses),
                Order.created_at >= start_date,
                Order.created_at <= end_date,
            )
        )
        
        result = await self.session.execute(query)
        row = result.one()
        
        return {
            "period_start": start_date,
            "period_end": end_date,
            "orders_count": row.orders_count,
            "total_revenue": int(row.total_revenue),
            "photos_revenue": int(row.photos_revenue),
            "delivery_revenue": int(row.delivery_revenue),
            "total_discount": int(row.total_discount),
            "avg_check": round(float(row.avg_check), 2),
        }
    
    async def get_revenue_by_days(
        self,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Выручка по дням для графика."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        paid_statuses = [
            OrderStatus.PAID,
            OrderStatus.CONFIRMED,
            OrderStatus.PRINTING,
            OrderStatus.READY,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ]
        
        # Группировка по дате
        total_expr = Order.photos_cost + Order.delivery_cost - Order.discount
        
        query = select(
            func.date(Order.created_at).label("date"),
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(total_expr), 0).label("revenue"),
        ).where(
            and_(
                Order.status.in_(paid_statuses),
                Order.created_at >= start_date,
            )
        ).group_by(
            func.date(Order.created_at)
        ).order_by(
            func.date(Order.created_at)
        )
        
        result = await self.session.execute(query)
        rows = result.all()
        
        # Заполняем пропущенные дни нулями
        data_by_date = {str(row.date): {"orders": row.orders, "revenue": int(row.revenue)} for row in rows}
        
        chart_data = []
        current = start_date.date()
        while current <= end_date.date():
            date_str = str(current)
            if date_str in data_by_date:
                chart_data.append({
                    "date": date_str,
                    "orders": data_by_date[date_str]["orders"],
                    "revenue": data_by_date[date_str]["revenue"],
                })
            else:
                chart_data.append({
                    "date": date_str,
                    "orders": 0,
                    "revenue": 0,
                })
            current += timedelta(days=1)
        
        return chart_data
    
    async def get_orders_by_status(self) -> Dict[str, int]:
        """Количество заказов по статусам."""
        query = select(
            Order.status,
            func.count(Order.id).label("count"),
        ).group_by(Order.status)
        
        result = await self.session.execute(query)
        rows = result.all()
        
        return {row.status.value: row.count for row in rows}
    
    async def get_format_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Статистика по форматам фото."""
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        paid_statuses = [
            OrderStatus.PAID,
            OrderStatus.CONFIRMED,
            OrderStatus.PRINTING,
            OrderStatus.READY,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ]
        
        query = select(
            Photo.format,
            func.count(Photo.id).label("count"),
        ).join(
            Order, Photo.order_id == Order.id
        ).where(
            and_(
                Order.status.in_(paid_statuses),
                Order.created_at >= start_date,
                Order.created_at <= end_date,
            )
        ).group_by(Photo.format)
        
        result = await self.session.execute(query)
        rows = result.all()
        
        total = sum(row.count for row in rows)
        
        return [
            {
                "format": row.format.value,
                "format_name": row.format.short_name,
                "count": row.count,
                "percent": round(row.count / total * 100, 1) if total > 0 else 0,
            }
            for row in sorted(rows, key=lambda x: x.count, reverse=True)
        ]
    
    async def get_delivery_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Статистика по способам доставки."""
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        paid_statuses = [
            OrderStatus.PAID,
            OrderStatus.CONFIRMED,
            OrderStatus.PRINTING,
            OrderStatus.READY,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ]
        
        query = select(
            Order.delivery_type,
            func.count(Order.id).label("count"),
        ).where(
            and_(
                Order.status.in_(paid_statuses),
                Order.delivery_type.isnot(None),
                Order.created_at >= start_date,
                Order.created_at <= end_date,
            )
        ).group_by(Order.delivery_type)
        
        result = await self.session.execute(query)
        rows = result.all()
        
        total = sum(row.count for row in rows)
        
        return [
            {
                "delivery_type": row.delivery_type.value if row.delivery_type else "unknown",
                "delivery_name": row.delivery_type.display_name if row.delivery_type else "Неизвестно",
                "count": row.count,
                "percent": round(row.count / total * 100, 1) if total > 0 else 0,
            }
            for row in sorted(rows, key=lambda x: x.count, reverse=True)
        ]
    
    async def get_photos_to_print(self) -> List[Dict[str, Any]]:
        """Фото к печати (подтверждённые заказы)."""
        # Заказы, которые нужно печатать
        printing_statuses = [OrderStatus.CONFIRMED, OrderStatus.PRINTING]
        
        query = select(
            Photo.format,
            func.count(Photo.id).label("count"),
        ).join(
            Order, Photo.order_id == Order.id
        ).where(
            Order.status.in_(printing_statuses)
        ).group_by(Photo.format)
        
        result = await self.session.execute(query)
        rows = result.all()
        
        return [
            {
                "format": row.format.value,
                "format_name": row.format.short_name,
                "count": row.count,
            }
            for row in sorted(rows, key=lambda x: x.count, reverse=True)
        ]
    
    async def get_customer_stats(self) -> Dict[str, Any]:
        """Статистика по клиентам."""
        # Всего клиентов
        total_users = await self.session.execute(
            select(func.count(User.id))
        )
        total = total_users.scalar()
        
        # Клиенты с заказами
        users_with_orders = await self.session.execute(
            select(func.count(func.distinct(Order.user_id))).where(
                Order.status != OrderStatus.DRAFT
            )
        )
        with_orders = users_with_orders.scalar()
        
        # Повторные клиенты (более 1 заказа)
        repeat_query = select(
            func.count()
        ).select_from(
            select(Order.user_id).where(
                Order.status != OrderStatus.DRAFT
            ).group_by(Order.user_id).having(
                func.count(Order.id) > 1
            ).subquery()
        )
        repeat_result = await self.session.execute(repeat_query)
        repeat_customers = repeat_result.scalar()
        
        return {
            "total_users": total,
            "users_with_orders": with_orders,
            "repeat_customers": repeat_customers,
            "repeat_rate": round(repeat_customers / with_orders * 100, 1) if with_orders > 0 else 0,
        }
    
    async def get_top_customers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Топ клиентов по сумме заказов."""
        paid_statuses = [
            OrderStatus.PAID,
            OrderStatus.CONFIRMED,
            OrderStatus.PRINTING,
            OrderStatus.READY,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ]
        
        total_expr = Order.photos_cost + Order.delivery_cost - Order.discount
        
        query = select(
            User.id,
            User.username,
            User.first_name,
            func.count(Order.id).label("orders_count"),
            func.sum(total_expr).label("total_spent"),
        ).join(
            Order, User.id == Order.user_id
        ).where(
            Order.status.in_(paid_statuses)
        ).group_by(
            User.id
        ).order_by(
            func.sum(total_expr).desc()
        ).limit(limit)
        
        result = await self.session.execute(query)
        rows = result.all()
        
        return [
            {
                "user_id": row.id,
                "username": row.username,
                "name": row.first_name or row.username or f"User #{row.id}",
                "orders_count": row.orders_count,
                "total_spent": int(row.total_spent),
            }
            for row in rows
        ]
    
    async def get_conversion_stats(self) -> Dict[str, Any]:
        """Статистика конверсии."""
        # Всего черновиков (начатых заказов)
        drafts = await self.session.execute(
            select(func.count(Order.id)).where(Order.status == OrderStatus.DRAFT)
        )
        total_drafts = drafts.scalar()
        
        # Заказы дошедшие до оплаты
        paid_statuses = [
            OrderStatus.PAID,
            OrderStatus.CONFIRMED,
            OrderStatus.PRINTING,
            OrderStatus.READY,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ]
        
        paid = await self.session.execute(
            select(func.count(Order.id)).where(Order.status.in_(paid_statuses))
        )
        total_paid = paid.scalar()
        
        # Отменённые
        cancelled = await self.session.execute(
            select(func.count(Order.id)).where(Order.status == OrderStatus.CANCELLED)
        )
        total_cancelled = cancelled.scalar()
        
        total_started = total_drafts + total_paid + total_cancelled
        
        return {
            "total_started": total_started,
            "total_drafts": total_drafts,
            "total_paid": total_paid,
            "total_cancelled": total_cancelled,
            "conversion_rate": round(total_paid / total_started * 100, 1) if total_started > 0 else 0,
        }
    
    async def get_dashboard_summary(self) -> Dict[str, Any]:
        """Сводка для дашборда."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Выручка за сегодня, неделю, месяц
        today_stats = await self.get_revenue_stats(today, datetime.now())
        week_stats = await self.get_revenue_stats(week_ago, datetime.now())
        month_stats = await self.get_revenue_stats(month_ago, datetime.now())
        
        # Заказы по статусам
        orders_by_status = await self.get_orders_by_status()
        
        # Фото к печати
        photos_to_print = await self.get_photos_to_print()
        total_photos_to_print = sum(p["count"] for p in photos_to_print)
        
        # Конверсия
        conversion = await self.get_conversion_stats()
        
        return {
            "revenue": {
                "today": today_stats["total_revenue"],
                "today_orders": today_stats["orders_count"],
                "week": week_stats["total_revenue"],
                "week_orders": week_stats["orders_count"],
                "month": month_stats["total_revenue"],
                "month_orders": month_stats["orders_count"],
                "avg_check": month_stats["avg_check"],
            },
            "orders_by_status": orders_by_status,
            "photos_to_print": {
                "total": total_photos_to_print,
                "by_format": photos_to_print,
            },
            "conversion": conversion,
        }

