"""Тесты studio-скоупленного PricingService."""
import pytest
from src.models.studio import Studio
from src.models.product import Product
from src.services.product_service import ProductService
from src.services.pricing import PricingService


@pytest.mark.asyncio
async def test_pricing_uses_studio_catalog(db_session):
    ProductService.invalidate_cache()
    s1 = Studio(slug="s1", name="S1"); s2 = Studio(slug="s2", name="S2")
    db_session.add_all([s1, s2]); await db_session.commit()
    p1 = Product(studio_id=s1.id, slug="x", name="X", short_name="X",
                 price_per_unit=25, price_type="per_unit", is_active=True)
    p2 = Product(studio_id=s2.id, slug="x", name="X", short_name="X",
                 price_per_unit=40, price_type="per_unit", is_active=True)
    db_session.add_all([p1, p2]); await db_session.commit()
    await ProductService(db_session).load_cache(s1.id)
    await ProductService(db_session).load_cache(s2.id)

    assert PricingService.calculate_total_cost(s1.id, {p1.id: 10}) == 250
    assert PricingService.calculate_total_cost(s2.id, {p2.id: 10}) == 400
