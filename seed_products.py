import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from database.models import Base, Product  # Убедись, что models.py в той же папке

# Укажи свои данные подключения к базе
DATABASE_URL = "postgresql+asyncpg://postgres:rama@localhost:5432/meat_bot_db"

engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

products_data = [
    # Список из фото №1 (1-59)
    {"name": "1-toifali mol go'shti", "unit": "кг", "p_s": 100000},
    {"name": "Mol go'shti (muzlatilgan)", "unit": "кг", "p_s": 80000},
    {"name": "Parranda go'shti (muzlatilgan)", "unit": "кг", "p_s": 34000},
    {"name": "Tozalangan baliq", "unit": "кг", "p_s": 48000},
    {"name": "Tirik baliq", "unit": "кг", "p_s": 18000},
    {"name": "Tovuq tuxumi 1-toifa", "unit": "шт", "p_s": 1400},
    {"name": "Guruch", "unit": "кг", "p_s": 12000},
    {"name": "Goroh", "unit": "кг", "p_s": 10000},
    {"name": "No'xot", "unit": "кг", "p_s": 26000},
    {"name": "Mosh", "unit": "кг", "p_s": 16000},
    {"name": "Grechka yormasi", "unit": "кг", "p_s": 11000},
    {"name": "Nadir yormasi (perlovaya)", "unit": "кг", "p_s": 9000},
    {"name": "Suli yormasi (bug'doy yormasi)", "unit": "кг", "p_s": 11000},
    {"name": "Gerkules (ovsyaniy)", "unit": "кг", "p_s": 10000},
    {"name": "Mannaya krupa", "unit": "кг", "p_s": 11000},
    {"name": "Pista yog'i (o'simlik)", "unit": "литр", "p_s": 21000},
    {"name": "Mol suti (pasterizatsiyalangan)", "unit": "литр", "p_s": 10000},
    {"name": "Mol suti (qaynatilgan)", "unit": "литр", "p_s": 15000},
    {"name": "Tvorog 5%", "unit": "кг", "p_s": 30000},
    {"name": "Pishloq 45%", "unit": "кг", "p_s": 55000},
    {"name": "Kefir 3,2%", "unit": "литр", "p_s": 10000},
    {"name": "Saryog' 82,5%", "unit": "кг", "p_s": 80000},
    {"name": "Smetana 20%", "unit": "кг", "p_s": 35000},
    {"name": "Kartoshka", "unit": "кг", "p_s": 7000},
    {"name": "Karam", "unit": "кг", "p_s": 5000},
    {"name": "Piyoz", "unit": "кг", "p_s": 2500},
    {"name": "Sabzi", "unit": "кг", "p_s": 4000},
    {"name": "Lavlagi", "unit": "кг", "p_s": 8000},
    {"name": "Bodiring", "unit": "кг", "p_s": 20000},
    {"name": "Pomidor", "unit": "кг", "p_s": 25000},
    {"name": "Bulg'or qalampiri", "unit": "кг", "p_s": 5000},
    {"name": "Ho'l mevalar (olma)", "unit": "кг", "p_s": 15000},
    {"name": "Murabbo (varenye)", "unit": "кг", "p_s": 45000},
    {"name": "Shakar", "unit": "кг", "p_s": 12000},
    {"name": "Kartoshka kraxmali", "unit": "кг", "p_s": 45000},
    {"name": "Ko'katlar (ukrop, kashnich)", "unit": "кг", "p_s": 22000},
    {"name": "Meva qiyomi (povidlo)", "unit": "кг", "p_s": 18000},
    {"name": "Meva qoqisi (suxofrukti)", "unit": "кг", "p_s": 22000},
    {"name": "Qora choy", "unit": "кг", "p_s": 45000},
    {"name": "Yo'dlangan osh tuzi", "unit": "кг", "p_s": 3500},
    {"name": "Zira", "unit": "кг", "p_s": 90000},
    {"name": "Asal", "unit": "кг", "p_s": 100000},
    {"name": "Kakao kukuni", "unit": "кг", "p_s": 110000},
    {"name": "Non pishirish xamirturi (droji)", "unit": "кг", "p_s": 60000},
    {"name": "Tomat pastasi", "unit": "кг", "p_s": 30000},
    {"name": "Makaron mahsulotlari", "unit": "кг", "p_s": 8000},
    {"name": "Pishiriq kukuni", "unit": "кг", "p_s": 40000},
    {"name": "Un (1-navli)", "unit": "кг", "p_s": 6000},
    {"name": "Un (oliy navli)", "unit": "кг", "p_s": 11000},
    {"name": "Sholg'om", "unit": "кг", "p_s": 5000},
    {"name": "Non (qolipli) 600gr", "unit": "шт", "p_s": 3000},
    {"name": "Qotirilgan non (suxari)", "unit": "кг", "p_s": 25000},
    {"name": "Mayiz", "unit": "кг", "p_s": 60000},
    {"name": "Namatak", "unit": "кг", "p_s": 35000},
    {"name": "Yong'oq", "unit": "кг", "p_s": 70000},
    {"name": "Limon", "unit": "кг", "p_s": 35000},
    {"name": "Turp", "unit": "кг", "p_s": 6000},
    {"name": "Sarimsoq", "unit": "кг", "p_s": 25000},
    {"name": "Ismaloq", "unit": "кг", "p_s": 5000},
    # Список из фото №2 (60-70)
    {"name": "Rediska", "unit": "кг", "p_s": 12000},
    {"name": "Vanilin 5gr", "unit": "шт", "p_s": 2000},
    {"name": "Parranda go'shti (file)", "unit": "кг", "p_s": 45000},
    {"name": "Qand upasi", "unit": "кг", "p_s": 25000},
    {"name": "Kabachki", "unit": "кг", "p_s": 5000},
    {"name": "Oshqovoq", "unit": "кг", "p_s": 8000},
    {"name": "Bio muesli (20gr)", "unit": "шт", "p_s": 3500},
    {"name": "Bolgar kukuni", "unit": "кг", "p_s": 38000},
    {"name": "Qizil piyoz", "unit": "кг", "p_s": 8000},
    {"name": "Kashnich doni", "unit": "кг", "p_s": 35000},
    {"name": "Quruq rayxon", "unit": "кг", "p_s": 75000},
]


async def seed_products():
    async with async_session() as session:
        for p in products_data:
            # Считаем вашу цену (закуп) как -15% от садика
            p_zakup = round(p["p_s"] * 0.85, 2)

            new_product = Product(
                name=p["name"],
                unit=p["unit"],
                price_sadik=p["p_s"],
                price_zakup=p_zakup
            )
            session.add(new_product)

        await session.commit()
        print("✅ 70 товаров успешно загружены в базу!")


if __name__ == "__main__":
    asyncio.run(seed_products())