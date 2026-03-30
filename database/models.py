from typing import List

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text, DateTime, Boolean, Float
from datetime import datetime

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    shifts: Mapped[List["Shift"]] = relationship(back_populates="user", cascade="all, delete-orphan")

class Deliveries(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"))

    object_name: Mapped[str] = mapped_column(String(100)) # Название садика
    weight_plan: Mapped[float] = mapped_column(Float) # План (кг)
    weight_fact: Mapped[float] = mapped_column(Float) # Факт (кг) сколько принял садик
    price_per_kg: Mapped[int] = mapped_column()

    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    shift: Mapped["Shift"] = relationship(back_populates="deliveries")

    @property
    def diff(self) -> str:
        """ Разница между планом и фактом  | Разница в таблице"""
        val = round(self.weight_plan - self.weight_fact, 2)
        if val > 0:
            return f"⚠️ Недостача {val} кг"
        return "✅ Норма"

    @property
    def total_price(self) -> int:
        """ Итоговая сумма(факт кг сколько принял садик * цена за кг мяса) | Сумма в таблице """
        return int(self.weight_fact * self.price_per_kg)


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    fuel_expense: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="shifts")
    deliveries: Mapped[List["Deliveries"]] = relationship(back_populates="shift", cascade="all, delete-orphan")

