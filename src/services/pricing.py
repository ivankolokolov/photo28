"""Сервис расчёта стоимости (studio-скоупленный)."""
from typing import Dict, List, Optional

from src.models.product import Product


class PricingService:
    """Расчёт стоимости заказа на каталоге конкретной студии."""

    @classmethod
    def get_product(cls, studio_id: int, product_id: int) -> Optional[Product]:
        from src.services.product_service import ProductService
        return ProductService.get_product(studio_id, product_id)

    @classmethod
    def calculate_total_cost(cls, studio_id: int, photos_by_product: Dict[int, int]) -> int:
        if not photos_by_product:
            return 0
        total = 0
        group_counts: Dict[str, int] = {}
        group_products: Dict[str, List[int]] = {}
        for product_id, count in photos_by_product.items():
            product = cls.get_product(studio_id, product_id)
            if not product:
                continue
            if product.price_type in ("fixed", "per_unit"):
                if product.pricing_group:
                    g = product.pricing_group
                    group_counts[g] = group_counts.get(g, 0) + count
                    group_products.setdefault(g, []).append(product_id)
                else:
                    total += product.price_per_unit * count
            elif product.price_type == "tiered":
                if product.pricing_group:
                    g = product.pricing_group
                    group_counts[g] = group_counts.get(g, 0) + count
                    group_products.setdefault(g, []).append(product_id)
                else:
                    total += cls._calculate_tiered_cost(product, count)
        for g, total_count in group_counts.items():
            if group_products[g]:
                product = cls.get_product(studio_id, group_products[g][0])
                if product:
                    total += cls._calculate_tiered_cost(product, total_count)
        return total

    @classmethod
    def _calculate_tiered_cost(cls, product: Product, count: int) -> int:
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
    def format_price_breakdown(cls, studio_id: int, photos_by_product: Dict[int, int]) -> List[str]:
        lines = []
        group_counts: Dict[str, int] = {}
        group_names: Dict[str, str] = {}
        for product_id, count in photos_by_product.items():
            product = cls.get_product(studio_id, product_id)
            if not product:
                continue
            if product.pricing_group:
                g = product.pricing_group
                group_counts[g] = group_counts.get(g, 0) + count
                group_names.setdefault(g, product.pricing_group.capitalize())
                lines.append(f"• {product.short_name}: {count} шт.")
            else:
                cost = product.price_per_unit * count
                lines.append(f"• {product.short_name}: {count} шт. × {product.price_per_unit}₽ = {cost}₽")
        for g, total_count in group_counts.items():
            for pid, cnt in photos_by_product.items():
                p = cls.get_product(studio_id, pid)
                if p and p.pricing_group == g:
                    cost = cls._calculate_tiered_cost(p, total_count)
                    lines.append(f"  └ Итого ({total_count} шт.): {cost}₽")
                    break
        return lines

    @classmethod
    def get_price_optimization_hint(cls, studio_id: int, photos_by_product: Dict[int, int]) -> Optional[str]:
        group_totals: Dict[str, int] = {}
        group_example: Dict[str, Product] = {}
        for product_id, count in photos_by_product.items():
            product = cls.get_product(studio_id, product_id)
            if not product:
                continue
            key = product.pricing_group or f"individual_{product_id}"
            group_totals[key] = group_totals.get(key, 0) + count
            group_example.setdefault(key, product)
        for key, total_count in group_totals.items():
            product = group_example.get(key)
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
