import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from database.models import Base, Kindergarten
from utils.constants import KINDERGARTENS  # Импортируем твой существующий список

# Укажи свои данные подключения (как в seed_products)
DATABASE_URL = "postgresql+asyncpg://postgres:rama@localhost:5432/meat_bot_db"

engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed_kindergartens():
    async with async_session() as session:
        print("Начинаю загрузку садиков...")

        for kg_name in KINDERGARTENS:
            # Проверяем, нет ли такого садика уже в базе, чтобы не было дублей
            new_kg = Kindergarten(name=kg_name, is_active=True)
            session.add(new_kg)

        try:
            await session.commit()
            print(f"✅ Успешно добавлено садиков: {len(KINDERGARTENS)}")
        except Exception as e:
            await session.rollback()
            print(f"❌ Ошибка при загрузке: {e}")


if __name__ == "__main__":
    asyncio.run(seed_kindergartens())