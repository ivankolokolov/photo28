"""Reconcile-цикл: сверяет реестр активных студий с состоянием БД."""
import logging

from src.bot.registry import StudioBotRegistry, load_active_studios
from src.bot.lifecycle import register_studio, unregister_studio

logger = logging.getLogger(__name__)


async def reconcile_studios(registry: StudioBotRegistry, session) -> tuple:
    """Сверяет реестр с БД: добавляет новые активные и удаляет деактивированные.

    Returns:
        (added, removed) — количество добавленных и удалённых студий.
    """
    active_studios = await load_active_studios(session)
    active_ids = {s.id for s in active_studios}
    active_by_id = {s.id: s for s in active_studios}

    registered_ids = registry.studio_ids()

    added = 0
    for studio_id, studio in active_by_id.items():
        if studio_id not in registered_ids:
            await register_studio(registry, studio)
            added += 1
            logger.info("Reconcile: добавлена студия %s", studio_id)

    removed = 0
    for studio_id in list(registered_ids):
        if studio_id not in active_ids:
            await unregister_studio(registry, studio_id)
            removed += 1
            logger.info("Reconcile: удалена студия %s", studio_id)

    if added or removed:
        logger.info("Reconcile завершён: +%d -%d студий", added, removed)

    return added, removed
