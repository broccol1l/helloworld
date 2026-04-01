from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, delete, update
from database.models import User, Delivery, Shift, Product, Kindergarten
from sqlalchemy.orm import selectinload

# --- РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ---
async def get_user(session: AsyncSession, tg_id: int):
    return await session.get(User, tg_id)


async def add_user(session: AsyncSession, tg_id: int, full_name: str):
    user = User(id=tg_id, full_name=full_name)
    session.add(user)
    await session.commit()
    return user


# --- РАБОТА С САДИКАМИ (НОВОЕ) ---
async def get_active_kindergartens(session: AsyncSession):
    """Получаем список только активных садиков для водителя"""
    query = select(Kindergarten).where(Kindergarten.is_active == True).order_by(Kindergarten.name)
    result = await session.execute(query)
    return result.scalars().all()


async def add_kindergarten(session: AsyncSession, name: str):
    """Для админ-панели: добавление нового объекта"""
    new_kg = Kindergarten(name=name)
    session.add(new_kg)
    await session.commit()
    return new_kg


# --- РАБОТА С ТОВАРАМИ ---
async def get_all_products(session: AsyncSession):
    query = select(Product).order_by(Product.name)
    result = await session.execute(query)
    return result.scalars().all()


# --- РАБОТА СО СМЕНАМИ ---
async def get_or_create_shift(session: AsyncSession, user_id: int):
    query = select(Shift).where(
        and_(Shift.user_id == user_id, Shift.is_closed == False)
    )
    result = await session.execute(query)
    shift = result.scalar_one_or_none()

    if not shift:
        shift = Shift(user_id=user_id)
        session.add(shift)
        await session.commit()
        await session.refresh(shift)
    return shift


# --- ОБНОВЛЕННАЯ ОТГРУЗКА ---
async def add_delivery(session: AsyncSession, shift_id: int, product_id: int,
                       kindergarten_id: int, weight_plan: float, weight_fact: float):
    # Подтягиваем продукт, чтобы взять цены для Snapshot
    product = await session.get(Product, product_id)

    new_delivery = Delivery(
        shift_id=shift_id,
        product_id=product_id,
        kindergarten_id=kindergarten_id,  # Теперь используем ID
        weight_plan=weight_plan,
        weight_fact=weight_fact,
        # Замораживаем цены в момент отгрузки
        p_sadik_fact=product.price_sadik,
        p_zakup_fact=product.price_zakup
    )

    session.add(new_delivery)
    await session.commit()
    await session.refresh(new_delivery)
    return new_delivery

from datetime import datetime

async def close_shift(session: AsyncSession, shift_id: int, fuel_amount: float):
    shift = await session.get(Shift, shift_id)
    if shift:
        shift.fuel_expense = fuel_amount
        shift.is_closed = True
        shift.closed_at = datetime.now()
        await session.commit()
        return shift
    return None


async def get_shift_deliveries(session: AsyncSession, shift_id: int):
    # Загружаем отгрузки этой смены вместе с данными о товарах и садиках
    query = select(Delivery).where(
        Delivery.shift_id == shift_id
    ).options(
        selectinload(Delivery.product),
        selectinload(Delivery.kindergarten)
    )
    result = await session.execute(query)
    return result.scalars().all()


# --- ДЛЯ АРХИВА ОТЧЕТОВ ---

async def get_user_shifts(session: AsyncSession, user_id: int, limit: int = 5, offset: int = 0):
    query = (
        select(
            Shift.id,
            Shift.closed_at,
            # Считаем сумму по ЗАМОРОЖЕННОЙ цене p_sadik_fact
            func.sum(Delivery.weight_fact * Delivery.p_sadik_fact).label('total_sum')
        )
        .join(Delivery, Delivery.shift_id == Shift.id)
        .where(Shift.user_id == user_id, Shift.is_closed == True)
        .group_by(Shift.id, Shift.closed_at)
        .order_by(Shift.closed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    return result.all()

# Жесткое удаление всей смены (сначала кишки-отгрузки, потом саму смену)
async def delete_shift_full(session: AsyncSession, shift_id: int):
    await session.execute(delete(Delivery).where(Delivery.shift_id == shift_id))
    await session.execute(delete(Shift).where(Shift.id == shift_id))
    await session.commit()

# Удаление одного садика из текущей (открытой) смены
async def delete_kg_from_active_shift(session: AsyncSession, shift_id: int, kg_id: int):
    await session.execute(
        delete(Delivery).where(Delivery.shift_id == shift_id, Delivery.kindergarten_id == kg_id)
    )
    await session.commit()

# Получить отгрузки конкретного садика в конкретной смене
async def get_kg_deliveries_in_shift(session: AsyncSession, shift_id: int, kg_id: int):
    query = (
        select(Delivery)
        .where(Delivery.shift_id == shift_id, Delivery.kindergarten_id == kg_id)
        .options(selectinload(Delivery.product))
    )
    result = await session.execute(query)
    return result.scalars().all()

# 1. Ищем открытую смену (is_closed == False)
async def get_active_shift(session: AsyncSession, user_id: int):
    result = await session.execute(
        select(Shift).where(Shift.user_id == user_id, Shift.is_closed == False)
    )
    return result.scalar_one_or_none()

# 2. Создаем смену с конкретной датой
async def create_shift_with_date(session: AsyncSession, user_id: int, date: datetime):
    new_shift = Shift(
        user_id=user_id,
        opened_at=date, # <--- Исправлено: теперь имя совпадает с тем, что в моделях
        is_closed=False
    )
    session.add(new_shift)
    await session.commit()
    return new_shift

# Получить данные смены по её ID (нужно для деталей отчета)
async def get_shift_by_id(session: AsyncSession, shift_id: int):
    return await session.get(Shift, shift_id)

# И на всякий случай проверь, есть ли у тебя эта функция
# (она нужна для вызова списка садиков в delivery.py)
async def get_all_kindergartens(session: AsyncSession):
    result = await session.execute(select(Kindergarten).where(Kindergarten.is_active == True))
    return result.scalars().all()

from sqlalchemy import update

async def update_shift_date(session: AsyncSession, shift_id: int, new_date: datetime):
    """Просто меняем дату открытия смены, не трогая данные"""
    await session.execute(
        update(Shift).where(Shift.id == shift_id).values(opened_at=new_date)
    )
    await session.commit()

# Раскрыть смену для редактирования
async def unclose_shift(session: AsyncSession, shift_id: int):
    await session.execute(
        update(Shift).where(Shift.id == shift_id).values(is_closed=False)
    )
    await session.commit()