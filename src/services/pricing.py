"""Сервис расчёта стоимости."""
from typing import Dict, List, Tuple
from src.models.photo import PhotoFormat


class PricingService:
    """Сервис для расчёта стоимости заказа."""
    
    # Цены на классические фото (за штуку)
    CLASSIC_PRICE_PER_PHOTO = 25
    
    # Цены на полароид/инстакс (прогрессивная шкала)
    # (количество, цена за комплект)
    POLAROID_PRICE_TIERS = [
        (1, 22),      # 1 шт = 22₽
        (28, 560),    # 28 шт = 560₽ (20₽/шт)
        (50, 950),    # 50 шт = 950₽ (19₽/шт)
        (100, 1900),  # 100 шт = 1900₽ (19₽/шт)
        (128, 2460),  # 128 шт = 2460₽
        (150, 2850),  # 150 шт = 2850₽ (19₽/шт)
        (200, 3800),  # 200 шт = 3800₽ (19₽/шт)
    ]
    
    # Количества, при которых выгоднее заказать набор
    SUBOPTIMAL_QUANTITIES = [
        26, 27,  # выгоднее взять 28
        46, 47, 49,  # выгоднее взять 50
        94, 95, 96, 97, 98, 99,  # выгоднее взять 100
        126, 127,  # выгоднее взять 128
        147, 149,  # выгоднее взять 150
        194, 195, 196, 197, 198, 199,  # выгоднее взять 200
    ]
    
    @classmethod
    def is_polaroid_type(cls, photo_format: PhotoFormat) -> bool:
        """Проверяет, относится ли формат к полароиду/инстаксу."""
        return photo_format in (
            PhotoFormat.POLAROID_STANDARD,
            PhotoFormat.POLAROID_WIDE,
            PhotoFormat.INSTAX,
        )
    
    @classmethod
    def calculate_classic_cost(cls, count: int) -> int:
        """Рассчитывает стоимость классических фото 10х15."""
        return count * cls.CLASSIC_PRICE_PER_PHOTO
    
    @classmethod
    def calculate_polaroid_cost(cls, count: int) -> int:
        """
        Рассчитывает стоимость фото типа полароид/инстакс.
        
        Используется прогрессивная шкала:
        - До 28 шт: 22₽/шт
        - 28+ шт: используются наборы
        """
        if count <= 0:
            return 0
        
        # Для малого количества - поштучная цена
        if count < 28:
            return count * 22
        
        # Находим оптимальную комбинацию наборов
        return cls._find_optimal_polaroid_price(count)
    
    @classmethod
    def _find_optimal_polaroid_price(cls, count: int) -> int:
        """Находит оптимальную цену для заданного количества полароидов."""
        # Сортируем тиры по убыванию количества
        tiers = sorted(cls.POLAROID_PRICE_TIERS, key=lambda x: x[0], reverse=True)
        
        total_cost = 0
        remaining = count
        
        # Жадный алгоритм: берём самые большие наборы
        for tier_count, tier_price in tiers:
            if tier_count <= remaining:
                num_sets = remaining // tier_count
                total_cost += num_sets * tier_price
                remaining = remaining % tier_count
        
        # Остаток (меньше 28) считаем поштучно
        if remaining > 0:
            total_cost += remaining * 22
        
        return total_cost
    
    @classmethod
    def calculate_total_cost(cls, photos_by_format: Dict[PhotoFormat, int]) -> int:
        """
        Рассчитывает общую стоимость фотографий.
        
        Args:
            photos_by_format: Словарь {формат: количество}
        
        Returns:
            Общая стоимость в рублях
        """
        total = 0
        
        # Считаем классические фото отдельно
        classic_count = photos_by_format.get(PhotoFormat.CLASSIC, 0)
        total += cls.calculate_classic_cost(classic_count)
        
        # Все полароиды/инстаксы считаем вместе (одна шкала)
        polaroid_count = sum(
            count for fmt, count in photos_by_format.items()
            if cls.is_polaroid_type(fmt)
        )
        total += cls.calculate_polaroid_cost(polaroid_count)
        
        return total
    
    @classmethod
    def get_price_optimization_hint(cls, photos_by_format: Dict[PhotoFormat, int]) -> str | None:
        """
        Проверяет, есть ли возможность сэкономить заказав больше фото.
        
        Returns:
            Текст подсказки или None, если оптимизация не нужна
        """
        # Считаем общее количество полароидов/инстаксов
        polaroid_count = sum(
            count for fmt, count in photos_by_format.items()
            if cls.is_polaroid_type(fmt)
        )
        
        # Проверяем, попадает ли количество в "невыгодные"
        if polaroid_count in cls.SUBOPTIMAL_QUANTITIES:
            # Находим ближайший выгодный набор
            optimal_sets = [28, 50, 100, 128, 150, 200]
            for optimal in optimal_sets:
                if optimal > polaroid_count:
                    current_cost = cls.calculate_polaroid_cost(polaroid_count)
                    optimal_cost = cls.calculate_polaroid_cost(optimal)
                    
                    # Если стоимость набора меньше или равна
                    if optimal_cost <= current_cost + (optimal - polaroid_count) * 5:
                        return (
                            f"💡 Рекомендуем заказать {optimal} фото вместо {polaroid_count} — "
                            f"это будет дешевле! (набор {optimal} шт. стоит {optimal_cost}₽)"
                        )
                    break
        
        return None
    
    @classmethod
    def format_price_breakdown(cls, photos_by_format: Dict[PhotoFormat, int]) -> List[str]:
        """
        Формирует детализацию стоимости.
        
        Returns:
            Список строк с описанием стоимости
        """
        lines = []
        
        for fmt in PhotoFormat:
            count = photos_by_format.get(fmt, 0)
            if count > 0:
                if fmt == PhotoFormat.CLASSIC:
                    cost = cls.calculate_classic_cost(count)
                    lines.append(f"• {fmt.short_name}: {count} шт. × {cls.CLASSIC_PRICE_PER_PHOTO}₽ = {cost}₽")
                else:
                    # Для полароидов показываем только количество
                    lines.append(f"• {fmt.short_name}: {count} шт.")
        
        # Добавляем итог по полароидам
        polaroid_count = sum(
            count for fmt, count in photos_by_format.items()
            if cls.is_polaroid_type(fmt)
        )
        if polaroid_count > 0:
            polaroid_cost = cls.calculate_polaroid_cost(polaroid_count)
            lines.append(f"  └ Итого полароид/инстакс ({polaroid_count} шт.): {polaroid_cost}₽")
        
        return lines

