from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, Deliveries, Shift
from config import config

from sqlalchemy import select, and_

# user
async def add_user(session: AsyncSession, tg_id: int, full_name: str, phone_number: str):
    new_user = User(
        tg_id=tg_id,
        full_name=full_name,
        phone_number=phone_number,
    )
    session.add(new_user)

    await session.commit()

async def get_user(session: AsyncSession, tg_id: int):
    query = select(User).where(User.tg_id==tg_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()

async def update_user_name(session: AsyncSession, tg_id: int, new_name: str):
    user = await get_user(session, tg_id)
    if user:
        user.full_name = new_name
        await session.commit()

# shift
async def get_or_create_shift(session: AsyncSession, user_id: int):
    query = select(Shift).where(
        and_(
            Shift.driver_id == user_id,
            Shift.is_closed == False
        )
    )
    result = await session.execute(query)
    shift = result.scalar_one_or_none()
    if not shift:
        shift = Shift(driver_id=user_id)
        session.add(shift)
        await session.commit()
        await session.refresh(shift)

    return shift

#delivery
async def add_delivery(session: AsyncSession, shift_id: int, object_name: str, weight_plan: float,
                       weight_fact: float):
    new_delivery = Deliveries(
        shift_id=shift_id,
        object_name=object_name,
        weight_plan=weight_plan,
        weight_fact=weight_fact,
        price_per_kg=config.meat_price
    )
    session.add(new_delivery)
    await session.commit()
    return new_delivery