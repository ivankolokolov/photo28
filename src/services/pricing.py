"""Сервис расчёта стоимости."""
from typing import Dict, List, Optional

from src.models.product import Product


class PricingService:
    """Сервис для расчёта стоимости заказа.
    
    Использует кеш ProductService для получения данных о товарах.
    """
    
    @classmethod
    def get_product(cls, product_id: int) -> Optional[Product]:
        """Получает продукт из кеша ProductService."""
        from src.services.product_service import ProductService
        return ProductService.get_product(product_id)
    
    @classmethod
    def calculate_total_cost(cls, photos_by_product: Dict[int, int]) -> int:
        """
        Рассчитывает общую стоимость фотографий.
        
        Args:
            photos_by_product: Словарь {product_id: количество}
        
        Returns:
            Общая стоимость в рублях
        """
        if not photos_by_product:
            return 0
        
        total = 0
        
        # Группируем по pricing_group для совместного подсчёта тиров
        group_counts: Dict[str, int] = {}
        group_products: Dict[str, List[int]] = {}
        
        for product_id, count in photos_by_product.items():
            product = cls.get_product(product_id)
            if not product:
                continue
            
            if product.price_type == "fixed" or product.price_type == "per_unit":
                if product.pricing_group:
                    # Группируем для совместного тиерного расчёта
                    group = product.pricing_group
                    group_counts[group] = group_counts.get(group, 0) + count
                    if group not in group_products:
                        group_products[group] = []
                    group_products[group].append(product_id)
                else:
                    total += product.price_per_unit * count
            elif product.price_type == "tiered":
                if product.pricing_group:
                    group = product.pricing_group
                    group_counts[group] = group_counts.get(group, 0) + count
                    if group not in group_products:
                        group_products[group] = []
                    group_products[group].append(product_id)
                else:
                    total += cls._calculate_tiered_cost(product, count)
        
        # Рассчитываем стоимость по группам
        for group, total_count in group_counts.items():
            if group_products[group]:
                product = cls.get_product(group_products[group][0])
                if product:
                    total += cls._calculate_tiered_cost(product, total_count)
        
        return total
    
    @classmethod
    def _calculate_tiered_cost(cls, product: Product, count: int) -> int:
        """Рассчитывает стоимость с учётом тиров."""
        if count <= 0:
            return 0
        
        tiers = product.get_price_tiers()
        if not tiers:
            return product.price_per_unit * count
        
        sorted_tiers = sorted(tiers, key=lambda t: t.get("min_qty", 0), reverse=True)
        
        for tier in sorted_tiers:
            if count >= tier.get("min_qty", 0):
                return tier.get("price", product.price_per_unit) * count
        
        return product.price_per_unit * count
    
    @classmethod
    def format_price_breakdown(cls, photos_by_product: Dict[int, int]) -> List[str]:
        """Формирует детализацию стоимости."""
        lines = []
        
        group_counts: Dict[str, int] = {}
        group_names: Dict[str, str] = {}
        
        for product_id, count in photos_by_product.items():
            product = cls.get_product(product_id)
            if not product:
                continue
            
            if product.pricing_group:
                group = product.pricing_group
                group_counts[group] = group_counts.get(group, 0) + count
                if group not in group_names:
                    group_names[group] = product.pricing_group.capitalize()
                lines.append(f"• {product.short_name}: {count} шт.")
            else:
                cost = product.price_per_unit * count
                lines.append(f"• {product.short_name}: {count} шт. × {product.price_per_unit}₽ = {cost}₽")
        
        for group, total_count in group_counts.items():
            for pid, cnt in photos_by_product.items():
                p = cls.get_product(pid)
                if p and p.pricing_group == group:
                    cost = cls._calculate_tiered_cost(p, total_count)
                    lines.append(f"  └ Итого ({total_count} шт.): {cost}₽")
                    break
        
        return lines
    
    @classmethod
    def get_price_optimization_hint(cls, photos_by_product: Dict[int, int]) -> Optional[str]:
        """Подсказка об оптимизации цены."""
        # Считаем по группам
        group_totals: Dict[str, int] = {}
        group_example: Dict[str, Product] = {}
        
        for product_id, count in photos_by_product.items():
            product = cls.get_product(product_id)
            if not product:
                continue
            
            group_key = product.pricing_group or f"individual_{product_id}"
            group_totals[group_key] = group_totals.get(group_key, 0) + count
            if group_key not in group_example:
                group_example[group_key] = product
        
        for group_key, total_count in group_totals.items():
            product = group_example.get(group_key)
            if not product:
                continue
            
            tiers = product.get_price_tiers()
            if not tiers:
                continue
            
            for tier in sorted(tiers, key=lambda t: t.get("min_qty", 0)):
                min_qty = tier.get("min_qty", 0)
                tier_price = tier.get("price", 0)
                
                if total_count < min_qty and (min_qty - total_count) <= 10:
                    current_cost = product.price_per_unit * total_count
                    optimal_cost = tier_price * min_qty
                    
                    if optimal_cost <= current_cost + 200:
                        return (
                            f"💡 Если заказать {min_qty} шт вместо {total_count} — "
                            f"цена за штуку станет {tier_price}₽!"
                        )
        
        return None
