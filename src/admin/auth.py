"""Авторизация и роли админки."""
from typing import Optional
from fastapi import Request, HTTPException
from sqlalchemy import select

from src.models.admin_user import AdminUser, AdminRole
from src.services.auth import verify_password


async def authenticate(session, username: str, password: str) -> Optional[AdminUser]:
    admin = (await session.execute(
        select(AdminUser).where(AdminUser.username == username)
    )).scalar_one_or_none()
    if admin and verify_password(password, admin.password_hash):
        return admin
    return None


def current_admin(request: Request) -> Optional[dict]:
    if not request.session.get("user_id"):
        return None
    return {
        "user_id": request.session["user_id"],
        "username": request.session.get("username"),
        "role": request.session.get("role"),
        "studio_id": request.session.get("studio_id"),
    }


def effective_studio_id(request: Request) -> Optional[int]:
    admin = current_admin(request)
    if not admin:
        return None
    if admin["role"] == AdminRole.STUDIO_ADMIN.value:
        return admin["studio_id"]
    return request.session.get("active_studio_id")


def require_admin(request: Request) -> dict:
    admin = current_admin(request)
    if not admin:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return admin


def require_super_admin(request: Request) -> dict:
    admin = require_admin(request)
    if admin["role"] != AdminRole.SUPER_ADMIN.value:
        raise HTTPException(status_code=403, detail="Только для супер-админа")
    return admin


def require_studio(request: Request) -> int:
    admin = require_admin(request)
    sid = effective_studio_id(request)
    if sid is None:
        # super_admin без выбранной студии → на список студий
        raise HTTPException(status_code=303, headers={"Location": "/studios"})
    return sid
