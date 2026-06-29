"""Фоновые задачи бота (студия-скоупленные)."""
import logging
from src.services.order_service import OrderService

logger = logging.getLogger(__name__)


async def cleanup_old_drafts_once(session, studio_ids, days: int = 7) -> int:
    total = 0
    for sid in studio_ids:
        deleted = await OrderService(session, sid).delete_old_drafts(days=days)
        total += deleted
    if total:
        logger.info("Очищено %s старых черновиков по %s студиям", total, len(studio_ids))
    return total
