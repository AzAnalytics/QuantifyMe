# app/persistence/models.py
# -*- coding: utf-8 -*-
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Float, Date, DateTime, Boolean, ForeignKey, UniqueConstraint, func
import datetime as dt

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    records = relationship("Record", back_populates="user", cascade="all, delete-orphan", lazy="selectin")

class Record(Base):
    __tablename__ = "records"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, index=True, nullable=False)

    humeur: Mapped[float] = mapped_column(Float, nullable=False)
    sommeil: Mapped[float] = mapped_column(Float, nullable=False)
    stress: Mapped[float] = mapped_column(Float, nullable=False)
    concentration: Mapped[float] = mapped_column(Float, nullable=False)

    scj: Mapped[float] = mapped_column(Float, nullable=False)
    interpretation: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    user = relationship("User", back_populates="records")
