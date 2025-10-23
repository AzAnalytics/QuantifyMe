# app/persistence/repositories/users_repo.py
# -*- coding: utf-8 -*-
from sqlalchemy import select
from app.persistence.db import get_session
from app.persistence.models import User

class UserRepository:
    def create(self, email: str, is_premium: bool = False) -> User:
        with get_session() as s:
            u = User(email=email.strip().lower(), is_premium=is_premium)
            s.add(u)
            s.flush(); s.refresh(u); s.expunge(u)
            return u

    def get_by_email(self, email: str) -> User | None:
        with get_session() as s:
            u = s.scalar(select(User).where(User.email == email.strip().lower()))
            if not u:
                return None
            s.expunge(u)
            return u

    def get_or_create(self, email: str, is_premium: bool = False) -> User:
        u = self.get_by_email(email)
        return u or self.create(email=email, is_premium=is_premium)

    def set_premium(self, email: str, value: bool = True) -> None:
        with get_session() as s:
            u = s.scalar(select(User).where(User.email == email.strip().lower()))
            if not u:
                raise ValueError(f"Utilisateur introuvable: {email}")
            u.is_premium = value
            s.add(u)
