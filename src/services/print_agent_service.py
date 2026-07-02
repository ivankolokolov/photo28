"""Пайринг и аутентификация агентов печати."""
import hashlib
import secrets
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.print_agent import PrintAgent


class PrintAgentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    async def create_pairing(self, studio_id: int, name: str = "") -> PrintAgent:
        agent = PrintAgent(
            studio_id=studio_id,
            name=name,
            pairing_code=secrets.token_urlsafe(6),
        )
        self.session.add(agent)
        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def pair(self, code: str) -> Optional[Tuple[PrintAgent, str]]:
        agent = (await self.session.execute(
            select(PrintAgent).where(PrintAgent.pairing_code == code)
        )).scalar_one_or_none()
        if agent is None:
            return None
        raw = secrets.token_urlsafe(32)
        agent.token_hash = self._hash_token(raw)
        agent.pairing_code = None
        agent.paired_at = datetime.now()
        await self.session.commit()
        await self.session.refresh(agent)
        return agent, raw

    async def authenticate(self, token: str) -> Optional[PrintAgent]:
        if not token:
            return None
        agent = (await self.session.execute(
            select(PrintAgent).where(PrintAgent.token_hash == self._hash_token(token))
        )).scalar_one_or_none()
        return agent
