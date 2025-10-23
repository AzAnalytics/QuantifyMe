# app/persistence/repositories/records_repo.py
# -*- coding: utf-8 -*-
from sqlalchemy import select, func, and_
from app.persistence.db import get_session
from app.persistence.models import Record
import datetime as dt

def _normalize_date(d):
    if isinstance(d, dt.datetime):
        return d.date()
    if isinstance(d, dt.date):
        return d
    if isinstance(d, str):
        return dt.date.fromisoformat(d)
    raise TypeError("Invalid date type")

class RecordRepository:
    def add(self, user_id: int, date, **fields) -> Record:
        day = _normalize_date(date)
        with get_session() as s:
            exists = s.scalar(select(Record.id).where(and_(Record.user_id == user_id, Record.date == day)))
            if exists:
                raise ValueError(f"Record déjà présent pour {day}")
            r = Record(user_id=user_id, date=day, **fields)
            s.add(r); s.flush(); s.refresh(r); s.expunge(r)
            return r

    def upsert(self, user_id: int, date, **fields) -> Record:
        day = _normalize_date(date)
        with get_session() as s:
            rec = s.scalar(select(Record).where(and_(Record.user_id == user_id, Record.date == day)).limit(1))
            if rec:
                for k, v in fields.items():
                    setattr(rec, k, v)
                s.add(rec); s.flush(); s.refresh(rec); s.expunge(rec)
                return rec
            r = Record(user_id=user_id, date=day, **fields)
            s.add(r); s.flush(); s.refresh(r); s.expunge(r)
            return r

    def get_range(self, user_id: int, start=None, end=None, asc=True):
        with get_session() as s:
            stmt = select(Record).where(Record.user_id == user_id)
            if start is not None:
                stmt = stmt.where(Record.date >= _normalize_date(start))
            if end is not None:
                stmt = stmt.where(Record.date <= _normalize_date(end))
            stmt = stmt.order_by(Record.date.asc() if asc else Record.date.desc())
            rows = list(s.scalars(stmt))
            for r in rows:
                s.expunge(r)
            return rows

    def last_n(self, user_id: int, n: int = 7):
        with get_session() as s:
            stmt = select(Record).where(Record.user_id == user_id).order_by(Record.date.desc()).limit(n)
            rows = list(s.scalars(stmt))
            for r in rows:
                s.expunge(r)
            return list(reversed(rows))

    def delete(self, user_id: int, date) -> bool:
        day = _normalize_date(date)
        with get_session() as s:
            rec = s.scalar(select(Record).where(and_(Record.user_id == user_id, Record.date == day)).limit(1))
            if not rec:
                return False
            s.delete(rec)
            return True

    def exists(self, user_id: int, date) -> bool:
        day = _normalize_date(date)
        with get_session() as s:
            c = s.scalar(select(func.count(Record.id)).where(and_(Record.user_id == user_id, Record.date == day))) or 0
            return c > 0

    def weekly_avg(self, user_id: int, end_date=None):
        end = _normalize_date(end_date) if end_date else dt.date.today()
        start = end - dt.timedelta(days=6)
        with get_session() as s:
            avg = s.scalar(select(func.avg(Record.scj)).where(
                and_(Record.user_id == user_id, Record.date >= start, Record.date <= end)
            ))
            return float(avg) if avg is not None else None
