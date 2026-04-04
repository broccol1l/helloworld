import os
from datetime import datetime, timedelta
from fpdf import FPDF
from aiogram.dispatcher.event.bases import SkipHandler

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from aiogram.types import Message
import pandas as pd
from io import BytesIO
from aiogram.types import FSInputFile, BufferedInputFile
from database.requests import (get_user_shifts, update_shift_date, get_user, delete_shift_full,
                               get_shift_by_id, get_shift_deliveries, unclose_shift,
                               delete_kg_from_active_shift, get_dashboard_stats,
                               get_drivers_performance, get_all_deliveries_for_export,
                               get_deliveries_by_period)

# Импортируем твои модели, стейты и клавиатуры
from database.models import User, Product, Kindergarten, Shift, Delivery
from utils.states import AdminState, AdminEdit, KGState, DeliveryState, AdminStatsState
from keyboards.inline import (admin_main_kb, get_products_list_kb, get_product_card_kb,
                              get_cancel_kb, get_units_kb, get_kg_list_kb,
                              get_kg_card_kb, get_user_card_kb, get_users_list_kb,
                              get_admin_user_history_kb, get_admin_report_tools_kb,
                              get_admin_edit_menu_kb, get_admin_manage_kgs_kb,
                              get_admin_edit_loop_kb, get_kg_paging_kb, get_products_paging_kb,
                              get_analytics_period_kb, get_dashboard_kb, get_drivers_stats_kb)

from keyboards.reply import main_menu_kb

router = Router()


# --- ВХОД В АДМИНКУ ---

@router.message(F.text == "⚙️ Admin paneli") # ⚙️ Админ-панель
@router.message(Command("admin"))
async def admin_mode_entry(message: types.Message, session: AsyncSession):
    # Проверка на админа (на всякий случай)
    result = await session.execute(select(User).where(User.id == message.from_user.id))
    user = result.scalar_one_or_none()

    if user and user.is_admin:
        await message.answer(
            "🛡 **Boshqaruv paneli (Admin Mode)**\nKerakli bo'limni tanlang:",
            reply_markup=admin_main_kb(),  # Главное Inline-меню
            parse_mode="Markdown"
        )
        # "🛡 **Панель управления (Admin Mode)**\nВыберите нужный раздел:"
    else:
        await message.answer("❌ Ushbu bo'limga kirish huquqingiz yo'q.")
        # "❌ У вас нет прав доступа к этому разделу."


# --- ВЫХОД ИЗ АДМИНКИ ---

@router.callback_query(F.data == "admin_exit")
async def exit_admin_mode(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()  # Сброс всех ожиданий ввода

    # Редактируем старое сообщение, чтобы кнопки не висели
    await callback.message.edit_text("✅ Admin rejimidan chiqdingiz. Endi haydovchi menyusi mavjud.")
    # "✅ Вы вышли из режима админа. Теперь вам доступно меню водителя."
    # Отправляем новое сообщение с кнопками водителя
    await callback.message.answer(
        "🚚 Ishchi menyuga qaytdingiz:",
        reply_markup=main_menu_kb(is_admin=True)  # Показываем кнопку админки внизу
    )
    # 🚚 Вы вернулись в рабочее меню:
    await callback.answer()


# --- КНОПКА "В НАЧАЛО" (Универсальная) ---

@router.callback_query(F.data == "admin_home")
async def back_to_admin_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🛡 **Boshqaruv paneli (Admin Mode)**\nKerakli bo'limni tanlang:",
        reply_markup=admin_main_kb(),
        parse_mode="Markdown"
    )
    # "🛡 **Панель управления (Admin Mode)**\nВыберите нужный раздел:"
    await callback.answer()


# --- РАЗДЕЛ: ТОВАРЫ ---
@router.callback_query(F.data.startswith("adm_prod_view:"))
async def admin_product_view(callback: types.CallbackQuery, session: AsyncSession):
    # 1. Сразу отвечаем серверу Telegram, чтобы кнопка перестала крутиться
    await callback.answer()

    # 2. Достаем ID товара
    product_id = int(callback.data.split(":")[1])

    # 3. Ищем товар
    product = await session.get(Product, product_id)

    if not product:
        await callback.message.edit_text("❌ Mahsulot bazadan topilmadi.") # ❌ Товар не найден в базе.
        return

    # 4. Формируем текст
    text = (
        f"📦 **Mahsulot kartochkasi:**\n\n"
        f"📝 **Nomi:** {product.name}\n"
        f"📏 **O'lchov birligi:** {product.unit}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"💰 **Bog'cha narxi:** {int(product.price_sadik)} сум\n"
        f"📉 **Sotib olish narxi:** {int(product.price_zakup)} сум\n"
        f"📈 **Marja:** {int(product.price_sadik - product.price_zakup)} сум\n"
    )
        # f"📦 **Карточка товара:**\n\n"
        # f"📝 **Название:** {product.name}\n"
        # f"📏 **Ед. измерения:** {product.unit}\n"
        # f"➖➖➖➖➖➖➖➖\n"
        # f"💰 **Цена садика:** {int(product.price_sadik)} сум\n"
        # f"📉 **Цена закупа:** {int(product.price_zakup)} сум\n"
        # f"📈 **Маржа:** {int(product.price_sadik - product.price_zakup)} сум\n"

    # 5. Редактируем сообщение
    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_product_card_kb(product_id),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Ошибка при выводе карточки: {e}") # f"Ошибка при выводе карточки: {e}"


# --- ОТМЕНА РЕДАКТИРОВАНИЯ ---
@router.callback_query(F.data == "admin_cancel_edit")
async def cancel_editing(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("edit_product_id")
    await state.clear()

    if product_id:
        # Если был ID товара, возвращаем в его карточку
        await admin_product_view(callback, None)  # Вызываем хендлер просмотра
    else:
        await back_to_admin_main(callback, state)
    await callback.answer("Amal bekor qilindi") # "Действие отменено"




# --- ДОБАВЛЕНИЕ ТОВАРА ---

@router.callback_query(F.data == "adm_prod_add")
async def admin_product_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.waiting_product_name)
    await callback.message.edit_text(
        "📝 **1-qadam: Nomi**\nMahsulot nomini kiriting (masalan: Smetana 20%):",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )
    # "📝 **Шаг 1: Название**\nВведите название товара (например: *Сметана 20%*):"
    await callback.answer()


# 1. Получаем название -> спрашиваем Единицу Измерения
@router.message(AdminState.waiting_product_name)
async def admin_product_add_name(message: types.Message, state: FSMContext):
    await state.update_data(new_name=message.text)
    await state.set_state(AdminState.waiting_product_unit)  # Переходим к единицам

    await message.answer(
        f"✅ Nomi: {message.text}\n\n**2-qadam:** O'lchov birligini tanlang:",
        reply_markup=get_units_kb(),
        parse_mode="Markdown"
    )
    # f"✅ Название: {message.text}\n\n**Шаг 2:** Выберите единицу измерения:"


# 2. Получаем Единицу (через callback) -> спрашиваем Цену Садика
@router.callback_query(F.data.startswith("unit_set:"))
async def admin_product_add_unit(callback: types.CallbackQuery, state: FSMContext):
    unit = callback.data.split(":")[1]
    await state.update_data(new_unit=unit)

    await state.set_state(AdminState.waiting_p_sadik_add)
    await callback.message.edit_text(
        f"✅ O'lchov birligi: {unit}\n\n**3-qadam:** **BOG'CHA NARXINI** kiriting (son):",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )
    # f"✅ Единица измерения: {unit}\n\n**Шаг 3:** Введите **ЦЕНУ САДИКА** (число):"
    await callback.answer()

# 3. Получаем Цену Садика -> спрашиваем Цену Закупа
@router.message(AdminState.waiting_p_sadik_add)
async def admin_product_add_p_sadik(message: types.Message, state: FSMContext):
    # Очищаем текст от пробелов и меняем запятую на точку
    clean_text = message.text.replace(" ", "").replace(",", ".")

    # Проверяем, число ли это (разрешаем одну точку)
    if not clean_text.replace(".", "", 1).isdigit():
        await message.answer("❌ To'g'ri son kiriting (masalan: 100 000 yoki 105.5):", reply_markup=get_cancel_kb())
        # "❌ Введите корректное число (например: 100 000 или 105.5):"
        return

    await state.update_data(new_p_sadik=float(clean_text))  # Используем clean_text!
    await state.set_state(AdminState.waiting_p_zakup_add)
    await message.answer("💰 **4-qadam:** **SOTIB OLISH NARXINI** kiriting (son):", reply_markup=get_cancel_kb())
    #"💰 **Шаг 4:** Введите **ЦЕНУ ЗАКУПА** (число):"



# 4. Финал: сохранение в базу
@router.message(AdminState.waiting_p_zakup_add)
async def admin_product_add_finish(message: types.Message, state: FSMContext, session: AsyncSession):
    clean_text = message.text.replace(" ", "").replace(",", ".")

    if not clean_text.replace(".", "", 1).isdigit():
        await message.answer("❌ Son kiriting!", reply_markup=get_cancel_kb())
        # "❌ Введите число!"
        return

    data = await state.get_data()
    p_zakup = float(clean_text)  # Используем clean_text!

    # Создаем объект товара с учетом выбранной единицы
    new_product = Product(
        name=data['new_name'],
        unit=data['new_unit'], # Берем из памяти
        price_sadik=data['new_p_sadik'],
        price_zakup=p_zakup,
        is_active=True
    )

    session.add(new_product)
    await session.commit()
    await state.clear()

    await message.answer(
        f"🎉 **Mahsulot muvaffaqiyatli qo'shildi!**\n\n"
        f"📦 {new_product.name}\n"
        f"📏 O'lchov birligi: {new_product.unit}\n"
        f"💰 Bog'cha narxi: {int(new_product.price_sadik)} сум\n"
        f"📉 Sotib olish narxi: {int(new_product.price_zakup)} сум",
        reply_markup=admin_main_kb(),
        parse_mode="Markdown"
    )
        # f"🎉 **Товар успешно добавлен!**\n\n"
        # f"📦 {new_product.name}\n"
        # f"📏 Ед. изм.: {new_product.unit}\n"
        # f"💰 Цена садика: {int(new_product.price_sadik)} сум\n"
        # f"📉 Цена закупа: {int(new_product.price_zakup)} сум"

@router.callback_query(F.data.startswith("adm_prod_delete:"))
async def delete_product(callback: types.CallbackQuery, session: AsyncSession):
    product_id = int(callback.data.split(":")[1])
    product = await session.get(Product, product_id)

    if product:
        product.is_active = False  # Soft delete
        await session.commit()
        await callback.answer(f"🗑'{product.name}' mahsuloti o'chirildi") # f"🗑 Товар '{product.name}' удален"
        # Возвращаемся к списку товаров
        await admin_products_list(callback, session)

@router.callback_query(F.data == "admin_products")
@router.callback_query(F.data.startswith("adm_prod_page:"))
async def admin_products_list(callback: types.CallbackQuery, session: AsyncSession):
    # Определяем текущую страницу
    page = 0
    if callback.data.startswith("adm_prod_page:"):
        page = int(callback.data.split(":")[1])

    # Получаем все активные товары
    result = await session.execute(select(Product).where(Product.is_active == True).order_by(Product.name))
    products = result.scalars().all()

    if not products:
        await callback.message.edit_text(
            "📦 Mahsulotlar ro'yxati bo'sh.",
            reply_markup=get_products_list_kb([], page)
        )
        # "📦 Список товаров пуст."
    else:
        await callback.message.edit_text(
            f"📦 **Mahsulotlar ro'yxati (Страница {page + 1})**\nTahrirlash uchun mahsulot ustiga bosing:",
            reply_markup=get_products_list_kb(products, page),
            parse_mode="Markdown"
        )
        # f"📦 **Список товаров (Страница {page + 1})**\nНажмите на товар для редактирования:"
    await callback.answer()


# --- РЕДАКТИРОВАНИЕ ЦЕНЫ (НАЧАЛО) ---

@router.callback_query(F.data.startswith("adm_prod_edit:"))
async def admin_product_edit_start(callback: types.CallbackQuery, state: FSMContext):
    _, field, product_id = callback.data.split(":")
    product_id = int(product_id)

    await state.update_data(edit_product_id=product_id, edit_field=field)

    if field == "p_sadik":
        # 💰 Введите новую **ЦЕНУ САДИКА**:
        await callback.message.answer("💰 Yangi BOG'CHA NARXINI kiriting:", reply_markup=get_cancel_kb())
        await state.set_state(AdminEdit.waiting_p_sadik_edit)
    elif field == "p_zakup":
        # 📉 Введите новую **ЦЕНУ ЗАКУПА**:
        await callback.message.answer("📉 Yangi SOTIB OLISH NARXINI kiriting:", reply_markup=get_cancel_kb())
        await state.set_state(AdminEdit.waiting_p_zakup_edit)
    # --- ВОТ ЭТОГО КУСКА НЕ ХВАТАЛО ---
    elif field == "name":
        # ✏️ Введите новое **НАЗВАНИЕ** товара:
        await callback.message.answer("✏️ Mahsulotning yangi NOMINI kiriting:", reply_markup=get_cancel_kb())
        await state.set_state(AdminEdit.waiting_name_edit) # Убедись, что этот стейт есть в states.py
    # ---------------------------------

    await callback.answer()


# --- СОХРАНЕНИЕ ЦЕНЫ ---
# --- ЕДИНАЯ ФУНКЦИЯ СОХРАНЕНИЯ ПРИ РЕДАКТИРОВАНИИ ---
@router.message(AdminEdit.waiting_p_sadik_edit)
@router.message(AdminEdit.waiting_p_zakup_edit)
async def save_edited_price(message: Message, state: FSMContext, session: AsyncSession):
    # 1. Умная очистка текста (пробелы, запятые)
    clean_text = message.text.replace(" ", "").replace(",", ".")

    # Проверяем, число ли это
    if not clean_text.replace(".", "", 1).isdigit():
        await message.answer("❌ Xato! To'g'ri son kiriting (masalan: 105000):", reply_markup=get_cancel_kb())
        return

    new_price = float(clean_text)

    # 2. Достаем данные из памяти
    data = await state.get_data()
    product_id = data.get("edit_product_id")
    field = data.get("edit_field")

    # 3. Ищем продукт в базе
    product = await session.get(Product, product_id)
    if not product:
        await message.answer("❌ Xatolik: mahsulot topilmadi.")
        await state.clear()
        return

    # 4. Обновляем нужное поле
    if field == "p_sadik":
        product.price_sadik = new_price
    else:
        product.price_zakup = new_price

    await session.commit()
    await state.clear()  # Очищаем FSM

    # 5. Красивый ответ с возвратом в карточку
    text = (
        f"✅ **{product.name}** mahsuloti narxi muvaffaqiyatli yangilandi!\n\n"
        f"💰 Bog'cha narxi: {int(product.price_sadik)} so'm\n"
        f"📉 Sotib olish narxi: {int(product.price_zakup)} so'm\n"
        f"📈 Marja: {int(product.price_sadik - product.price_zakup)} so'm"
    )
      # f"✅ Цена товара **{product.name}** успешно обновлена!\n\n"
      # f"💰 Цена садика: {int(product.price_sadik)} сум\n"
      # f"📉 Цена закупа: {int(product.price_zakup)} сум\n"
      # f"📈 Маржа: {int(product.price_sadik - product.price_zakup)} сум"

    await message.answer(
        text,
        reply_markup=get_product_card_kb(product.id),
        parse_mode="Markdown"
    )


@router.message(AdminEdit.waiting_name_edit)
async def save_edited_name(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    product_id = data.get("edit_product_id")

    product = await session.get(Product, product_id)
    if product:
        old_name = product.name
        product.name = message.text  # Просто текст, проверка на число не нужна
        await session.commit()
        await state.clear()

        await message.answer(
            f"✅ Nomi o'zgartirildi!\nEski nomi: {old_name}\nYangi nomi: **{product.name}**",
            reply_markup=get_product_card_kb(product.id),
            parse_mode="Markdown"
        )
        # f"✅ Название изменено!\nБыло: {old_name}\nСтало: **{product.name}**"


# --- РАЗДЕЛ: САДИКИ ---

@router.callback_query(F.data == "admin_kindergartens")
@router.callback_query(F.data.startswith("adm_kg_page:"))
async def admin_kg_list(callback: types.CallbackQuery, session: AsyncSession):
    page = int(callback.data.split(":")[1]) if ":" in callback.data else 0

    result = await session.execute(
        select(Kindergarten).where(Kindergarten.is_active == True).order_by(Kindergarten.name))
    kg_list = list(result.scalars().all())

    await callback.message.edit_text(
        f"🏫 **Bog'chalar ro'yxati ({page + 1}-sahifa)**:",
        reply_markup=get_kg_list_kb(kg_list, page),
        parse_mode="Markdown"
    )
    # f"🏫 **Список садиков (Страница {page + 1})**:"
    await callback.answer()


@router.callback_query(F.data.startswith("adm_kg_view:"))
async def admin_kg_view(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    kg = await session.get(Kindergarten, kg_id)

    if not kg:
        await callback.answer("❌ Bog'cha topilmadi")
        # "❌ Садик не найден"
        return

    await callback.message.edit_text(
        f"🏫 **Obyekt:** {kg.name}\n\nBu yerda nomni o'zgartirish yoki obyektni faol ro'yxatdan o'chirish mumkin.",
        reply_markup=get_kg_card_kb(kg_id),
        parse_mode="Markdown"
    )
    # f"🏫 **Объект:** {kg.name}\n\nЗдесь можно изменить название или удалить объект из активного списка."
    await callback.answer()


# --- РАЗДЕЛ: САДИКИ ---

@router.callback_query(F.data == "admin_kindergartens")
@router.callback_query(F.data.startswith("adm_kg_page:"))
async def admin_kg_list(callback: types.CallbackQuery, session: AsyncSession):
    # Теперь мы берем цифру только если нажата кнопка "Страница"
    if callback.data.startswith("adm_kg_page:"):
        page = int(callback.data.split(":")[1])
    else:
        page = 0 # Во всех остальных случаях (удаление, первый вход) — 1-я страница

    result = await session.execute(
        select(Kindergarten).where(Kindergarten.is_active == True).order_by(Kindergarten.name)
    )
    kg_list = list(result.scalars().all())

    # Маленькая проверка: если на странице пусто (например, удалили последний садик на стр. 2)
    # Перекидываем на страницу назад
    limit = 6
    if page > 0 and len(kg_list) <= page * limit:
        page -= 1

    await callback.message.edit_text(
        f"🏫 **Bog'chalar ro'yxati ({page + 1}-sahifa)**:",
        reply_markup=get_kg_list_kb(kg_list, page),
        parse_mode="Markdown"
    )
    # f"🏫 **Список садиков (Страница {page + 1})**:"
    await callback.answer()


@router.callback_query(F.data.startswith("adm_kg_view:"))
async def admin_kg_view(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    kg = await session.get(Kindergarten, kg_id)

    if not kg:
        await callback.answer("❌ Bog'cha topilmadi")
        return

    await callback.message.edit_text(
        f"🏫 **Obyekt:** {kg.name}\n\nBu yerda nomni o'zgartirish yoki obyektni faol ro'yxatdan o'chirish mumkin",
        reply_markup=get_kg_card_kb(kg_id),
        parse_mode="Markdown"
    )
    # f"🏫 **Объект:** {kg.name}\n\nЗдесь можно изменить название или удалить объект из активного списка."
    await callback.answer()


# --- ДОБАВЛЕНИЕ САДИКА ---

@router.callback_query(F.data == "adm_kg_add")
async def admin_kg_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(KGState.waiting_kg_name)  # Используем твой стейт
    await callback.message.edit_text(
        "📝 Yangi bog'cha nomini kiriting (masalan: 52-sonli bog'cha):",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )
    # "📝 Введите название нового садика (например: *Садик №52*):"
    await callback.answer()


@router.message(KGState.waiting_kg_name)
async def admin_kg_add_finish(message: types.Message, state: FSMContext, session: AsyncSession):
    new_kg = Kindergarten(name=message.text, is_active=True)
    session.add(new_kg)

    try:
        await session.commit()
        await state.clear()
        # f"✅ Садик **{new_kg.name}** успешно добавлен!"
        await message.answer(f"✅ **{new_kg.name}** bog'chasi muvaffaqiyatli qo'shildi!", reply_markup=admin_main_kb())
    except Exception:
        await session.rollback()
        # "❌ Ошибка: садик с таким названием уже существует."
        await message.answer("❌ Xatolik: bunday nomli bog'cha allaqachon mavjud.")


@router.callback_query(F.data.startswith("adm_kg_delete:"))
async def admin_kg_delete(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    kg = await session.get(Kindergarten, kg_id)

    if kg:
        kg.is_active = False  # Просто скрываем
        await session.commit()
        await callback.answer(f"🗑 {kg.name} o'chirildi")
        # f"🗑 {kg.name} удален"
        await admin_kg_list(callback, session)  # Возвращаемся к списку


@router.callback_query(F.data.startswith("adm_kg_edit:"))
async def admin_kg_edit_start(callback: types.CallbackQuery, state: FSMContext):
    kg_id = int(callback.data.split(":")[1])

    # Сохраняем ID садика в память, чтобы знать, чье имя менять
    await state.update_data(edit_kg_id=kg_id)
    await state.set_state(KGState.waiting_kg_edit_name)

    await callback.message.answer(
        "✏️ Ushbu bog'cha uchun yangi nom kiriting:",
        reply_markup=get_cancel_kb()  # Используем нашу кнопку отмены
    )
    # "✏️ Введите **новое название** для этого садика:"
    await callback.answer()


@router.message(KGState.waiting_kg_edit_name)
async def admin_kg_edit_save(message: types.Message, state: FSMContext, session: AsyncSession):
    # Достаем ID из памяти
    data = await state.get_data()
    kg_id = data.get("edit_kg_id")

    # Ищем садик в базе
    kg = await session.get(Kindergarten, kg_id)

    if not kg:
        await message.answer("❌ Xatolik: bog'cha topilmadi.")
        # "❌ Ошибка: садик не найден."
        await state.clear()
        return

    old_name = kg.name
    kg.name = message.text  # Обновляем имя

    await session.commit()  # Фиксируем в БД
    await state.clear()  # Очищаем состояние

    await message.answer(
        f"✅ Nomi muvaffaqiyatli o'zgartirildi!\n\n"
        f"Было: *{old_name}*\n"
        f"Стало: **{kg.name}**",
        reply_markup=get_kg_card_kb(kg.id),  # Возвращаем кнопки управления этим садиком
        parse_mode="Markdown"
    )
    # f"✅ Название успешно изменено!\n\n"
    #         f"Eski nomi: *{old_name}*\n"
    #         f"Yangi nomi: **{kg.name}**",


# --- РАЗДЕЛ: ПОЛЬЗОВАТЕЛИ ---

@router.callback_query(F.data == "admin_drivers")
@router.callback_query(F.data.startswith("adm_user_page:"))
async def admin_users_list(callback: types.CallbackQuery, session: AsyncSession):
    page = int(callback.data.split(":")[1]) if ":" in callback.data else 0

    # Показываем только тех, кто видим для админа
    result = await session.execute(
        select(User)
        .where(User.is_visible_in_admin == True)
        .order_by(User.full_name)
    )
    users = list(result.scalars().all())

    await callback.message.edit_text(
        f"👥 **Foydalanuvchilarni boshqarish ({page + 1}-sahifa)**\n\n"
        f"🛡️ — Admin\n🚚 — Haydovchi\n🚫 — Bloklangan",
        reply_markup=get_users_list_kb(users, page),
        parse_mode="Markdown"
    )
    # f"👥 **Управление пользователями (Стр. {page + 1})**\n\n"
    #         f"🛡️ — Админ\n🚚 — Водитель\n🚫 — Заблокирован"
    await callback.answer()


@router.callback_query(F.data.startswith("adm_user_view:"))
async def admin_user_view(callback: types.CallbackQuery, session: AsyncSession):
    # ПРОВЕРЬ ЭТУ СТРОКУ! Должно быть [-1]
    user_id = int(callback.data.split(":")[-1])

    user = await session.get(User, user_id)

    if not user:
        await callback.message.edit_text("❌ Пользователь не найден в базе.") # "❌ Пользователь не найден в базе."
        return

    role = "Administrator 🛡️" if user.is_admin else "Haydovchi 🚚"  # "Администратор 🛡️" if user.is_admin else "Водитель 🚚"
    status = "Bloklangan 🚫" if user.is_blocked else "Faol ✅" # "Заблокирован 🚫" if user.is_blocked else "Работает ✅"

    text = (
        f"👤 **Foydalanuvchi kartochkasi**\n\n"
        f"🆔 ID: `{user.id}`\n"
        f"📝 Ism: {user.full_name or 'Ko\'rsatilmagan'}\n"
        f"📞 Tel: {user.phone or 'Bog\'lanmagan'}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"🎭 Rol: {role}\n"
        f"📊 Status: {status}"
    )
      # f"👤 **Карточка пользователя**\n\n"
      # f"🆔 ID: `{user.id}`\n"
      # f"📝 Имя: {user.full_name or 'Не указано'}\n"
      # f"📞 Тел: {user.phone or 'Не привязан'}\n"
      # f"➖➖➖➖➖➖➖➖\n"
      # f"🎭 Роль: {role}\n"
      # f"📊 Статус: {status}"

    # Используем edit_text, чтобы обновить текущее сообщение
    await callback.message.edit_text(
        text,
        reply_markup=get_user_card_kb(user_id, user.is_admin, user.is_blocked),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_user_set:"))
async def admin_user_set_role(callback: types.CallbackQuery, session: AsyncSession):
    _, action, user_id = callback.data.split(":")
    user_id = int(user_id)

    if user_id == callback.from_user.id:
        await callback.answer("❌ O'z huquqlaringizni o'zgartira olmaysiz!", show_alert=True) # "❌ Нельзя менять права самому себе!"
        return

    user = await session.get(User, user_id)
    if not user:
        await callback.answer("Foydalanuvchi topilmadi") # "Пользователь не найден"
        return

    # Логика изменений
    if action == "promote":
        user.is_admin = True
    elif action == "demote":
        user.is_admin = False
    elif action == "block":
        user.is_blocked = True
        user.is_admin = False  # Админ не может быть заблокированным
    elif action == "unblock":
        user.is_blocked = False

    await session.commit()
    # Обновляем объект в памяти, чтобы admin_user_view увидел изменения
    await session.refresh(user)

    await callback.answer(f"✅ Status yangilandi") # ✅ Статус обновлен"

    # Сразу перерисовываем карточку
    await admin_user_view(callback, session)


# @router.callback_query(F.data == "admin_stats")
# async def admin_stats_view(callback: types.CallbackQuery, session: AsyncSession):
#     # Просто считаем количество всего в базе
#     from sqlalchemy import func
#
#     users_count = await session.scalar(select(func.count(User.id)))
#     products_count = await session.scalar(select(func.count(Product.id)))
#     kg_count = await session.scalar(select(func.count(Kindergarten.id)))
#
#     text = (
#         "📊 **Общая статистика бота**\n\n"
#         f"👥 Пользователей в базе: {users_count}\n"
#         f"📦 Видов товаров: {products_count}\n"
#         f"🏫 Садиков (объектов): {kg_count}\n\n"
#         "📈 Подробные отчеты будут доступны после первых отгрузок!"
#     )
#
#     await callback.message.edit_text(text, reply_markup=admin_main_kb(), parse_mode="Markdown")
#     await callback.answer()


# 1. Исправленный список истории
@router.callback_query(F.data.startswith("adm_history:"))
@router.callback_query(F.data.startswith("adm_rep_page:"))
async def admin_show_user_history(callback: types.CallbackQuery, session: AsyncSession, user_id_override: int = None):
    # Если мы передали ID вручную (после удаления), берем его
    if user_id_override:
        user_id = user_id_override
        page = 0
    else:
        # Иначе парсим из нажатой кнопки как обычно
        parts = callback.data.split(":")
        user_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0

    limit = 5
    offset = page * limit
    shifts = await get_user_shifts(session, user_id, limit, offset)

    # Если отчетов нет (например, удалили единственный отчет)
    if not shifts and page == 0:
        await callback.message.edit_text(
            "Ushbu haydovchida boshqa hisobotlar yo'q.",
            # Возвращаем кнопку в карточку юзера
            reply_markup=get_user_card_kb(user_id, False, False)
        )
        # "У этого водителя больше нет отчетов."
        return

    await callback.message.edit_text(
        f"📂 **Hisobotlar tarixi ({page + 1}-sahifa)**",
        reply_markup=get_admin_user_history_kb(shifts, user_id, page),
        parse_mode="Markdown"
    )
    # f"📂 **История отчетов (стр. {page + 1})**"


# handlers/admin.py

@router.callback_query(F.data.startswith("adm_view_rep:"))
async def admin_view_single_report(callback: types.CallbackQuery, session: AsyncSession, shift_id_override: int = None):
    if shift_id_override:
        shift_id = shift_id_override
    else:
        shift_id = int(callback.data.split(":")[1])

    result_shift = await session.execute(
        select(Shift).where(Shift.id == shift_id).options(selectinload(Shift.driver))
    )
    shift = result_shift.scalar_one_or_none()

    result_deliveries = await session.execute(
        select(Delivery).where(Delivery.shift_id == shift_id).options(
            selectinload(Delivery.product),
            selectinload(Delivery.kindergarten)
        )
    )
    deliveries = result_deliveries.scalars().all()

    if not shift:
        await callback.answer("⚠️ Smena topilmadi.", show_alert=True) # "⚠️ Смена не найдена."
        return

    report_text = f"📋 **{shift.opened_at.strftime('%d.%m.%Y')} sana uchun batafsil hisobot**\n"
    report_text += f"👤 Haydovchi: {shift.driver.full_name if shift.driver else 'O\'chirilgan'}\n"
    report_text += "───────────────────\n"
    # f"📋 **Детальный отчет за {shift.opened_at.strftime('%d.%m.%Y')}**\n"
    # f"👤 Водитель: {shift.driver.full_name if shift.driver else 'Удален'}\n"

    total_sum = 0
    total_cost = 0 # Считаем себестоимость (закуп)

    if not deliveries:
        report_text += "_Yetkazib berishlar qayd etilmadi_\n" # "_Отгрузок не зафиксировано_\n"
    else:
        for d in deliveries:
            report_text += f"🏫 {d.kindergarten.name}\n"
            report_text += f"  ◦ {d.product.name}: {d.weight_fact} {d.product.unit} = {d.total_price_sadik:,} сум\n"
            total_sum += d.total_price_sadik
            total_cost += d.total_cost_zakup

    fuel = shift.fuel_expense or 0
    final_amount = total_sum - fuel # Сколько водитель должен сдать налички
    net_profit = total_sum - total_cost - fuel # Твоя чистая прибыль

    report_text += "───────────────────\n"
    report_text += f"⛽ Benzin: **{fuel:,} so'm**\n" # f"⛽ Бензин: **{fuel:,} сум**\n"
    report_text += f"💰 UMUMIY TUSHUM: **{total_sum:,} so'm**\n" # f"💰 ОБЩАЯ ВЫРУЧКА: **{total_sum:,} сум**\n"
    report_text += f"💵 **KASSA (HAYDOVCHI TOPSHIRADI): {final_amount:,} so'm**\n" # f"💵 **КАССА (СДАЕТ ВОДИТЕЛЬ): {final_amount:,} сум**\n"
    report_text += f"📈 **SOF FOYDA: {net_profit:,} so'm**" # f"📈 **ЧИСТАЯ ПРИБЫЛЬ: {net_profit:,} сум**"

    from keyboards.inline import get_admin_report_tools_kb
    await callback.message.edit_text(
        report_text,
        reply_markup=get_admin_report_tools_kb(shift.id, shift.user_id),
        parse_mode="Markdown"
    )
    await callback.answer()


# 2. Исправленное удаление
@router.callback_query(F.data.startswith("adm_del_rep:"))
async def admin_delete_report(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    # Ищем смену, чтобы узнать кому она принадлежала
    shift = await session.get(Shift, shift_id)
    if not shift:
        await callback.answer("Hisobot allaqachon o'chirildi.") # "Отчет уже удален."
        return

    user_id = shift.user_id

    # Удаляем
    await delete_shift_full(session, shift_id)
    await callback.answer("🚨 Hisobot butunlay o'chirildi!", show_alert=True) # "🚨 Отчет полностью удален!"

    # ВМЕСТО callback.data = ... (что вызывало ошибку)
    # Вызываем функцию напрямую и передаем ID водителя
    await admin_show_user_history(callback, session, user_id_override=user_id)


# Вставь это в handlers/admin.py

# 1. Вход в редактирование (из карточки отчета)
@router.callback_query(F.data.startswith("adm_edit_rep:"))
async def admin_edit_report_start(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    await unclose_shift(session, shift_id)  # Открываем смену
    await state.clear()
    await state.update_data(shift_id=shift_id)  # Якорим ID смены в стейте

    await callback.message.edit_text(
        "🛠 **TAHRIRLASH REJIMI (ADMIN)**\nNima qilishni xohlaysiz?",
        reply_markup=get_admin_edit_loop_kb(shift_id), # Исправил название функции
        parse_mode="Markdown"
    )
    # 🛠 **РЕЖИМ РЕДАКТИРОВАНИЯ (АДМИН)**\nЧто вы хотите сделать?


# 2. Добавление нового садика в чужой отчет
@router.callback_query(F.data.startswith("adm_add_kg_start:"))
async def admin_add_kg_start(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])
    await state.update_data(shift_id=shift_id)

    from database.requests import get_active_kindergartens
    kgs = await get_active_kindergartens(session)

    await state.set_state(DeliveryState.object_name) # Магия: админ теперь в стейте водителя

    await callback.message.edit_text(
        "🏫 **Hisobotga bog'cha qo'shish**\nObyektni tanlang:",
        reply_markup=get_kg_paging_kb(kgs, page=0),
        parse_mode="Markdown"
    )
    # 🏫 **Добавление садика в отчет**\nВыберите объект:
    await callback.answer()

# 3. Список садиков для удаления
@router.callback_query(F.data.startswith("adm_manage_shift:"))
async def admin_manage_shift_kgs(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])
    deliveries = await get_shift_deliveries(session, shift_id)

    if not deliveries:
        await callback.answer("Ushbu smena bo'sh.", show_alert=True)
        # В этой смене пусто.
        return

    kgs = {d.kindergarten.id: d.kindergarten.name for d in deliveries}

    await callback.message.edit_text(
        "🔍 **Bog'chalarni boshqarish:**\nHisobotdan BUTUNLAY o'chirish uchun bog'chani tanlang:",
        reply_markup=get_admin_manage_kgs_kb(kgs, shift_id)
    )
    # 🔍 **Управление садиками:**\nВыберите садик для ПОЛНОГО удаления из отчета:

# 4. Удаление (Фикс распаковки)
@router.callback_query(F.data.startswith("adm_del_kg:"))
async def admin_delete_kg_from_shift(callback: types.CallbackQuery, session: AsyncSession):
    data_parts = callback.data.split(":")
    shift_id = int(data_parts[1])
    kg_id = int(data_parts[2])

    await delete_kg_from_active_shift(session, shift_id, kg_id)
    await callback.answer("✅ Bog'cha o'chirildi", show_alert=True)
    # ✅ Садик удален
    await admin_manage_shift_kgs(callback, session)


# 5. Завершение (Фикс Frozen Instance)
@router.callback_query(F.data.startswith("adm_finish_edit:"))
async def admin_finish_edit(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    await session.execute(
        update(Shift).where(Shift.id == shift_id).values(is_closed=True)
    )
    await session.commit()
    await state.clear()

    await callback.answer("✅ Tuzatishlar saqlandi")
    # ✅ Правки сохранены

    # Прямой вызов функции просмотра с override
    await admin_view_single_report(callback, session, shift_id_override=shift_id)


# 1. Если админ хочет добавить ЕЩЕ товар в тот же садик
@router.callback_query(F.data.startswith("adm_more_prod_same_kg:"))
async def admin_add_more_product_same_kg(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    # Мы просто отправляем его на выбор товара, не меняя садик в стейте
    from database.requests import get_all_products
    products = await get_all_products(session)

    await state.set_state(DeliveryState.choosing_product)
    await callback.message.edit_text(
        "Ushbu bog'cha uchun keyingi mahsulotni tanlang:",
        reply_markup=get_products_paging_kb(products, page=0)
    )
    # Выберите следующий товар для этого садика:

# 2. Если админ закончил с этим садиком и хочет вернуться в ГЛАВНОЕ МЕНЮ правки
@router.callback_query(F.data.startswith("adm_finish_this_kg:"))
async def admin_finish_kg_and_return(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    # Можно тут вывести мини-итог по садику, как у водителя
    # Но главное — вернуть его в главное меню админ-правки
    await callback.message.edit_text(
        "✅ Bog'cha yozib olindi. Keyingi qadam nima?",
        reply_markup=get_admin_edit_loop_kb(shift_id)
    )
    # ✅ Садик записан. Что делаем дальше?

# 1. Перехват кнопки "Завершить этот садик"
@router.callback_query(F.data == "finish_this_kg")
async def intercept_finish_kg(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(session, callback.from_user.id)

    if not user.is_admin:
        raise SkipHandler()  # 🪄 ВОТ МАГИЯ! Передаем сигнал дальше в delivery.py

    # Если нажал админ — возвращаем его в админку
    data = await state.get_data()
    shift_id = data.get("shift_id")
    await callback.message.edit_text("Bog'cha yakunlandi. Tahrirlash menyusiga qaytilmoqda...",
                                     reply_markup=get_admin_edit_loop_kb(shift_id))
    # Садик завершен. Возвращаюсь в меню правки...

# 2. Перехват кнопки "Завершить смену"
@router.callback_query(F.data == "go_to_close_shift")
async def intercept_close_shift(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(session, callback.from_user.id)

    if not user.is_admin:
        raise SkipHandler()  # 🪄 Пропускаем водителя в delivery.py

    # Если админ нажал "Завершить смену" в процессе правки
    data = await state.get_data()
    shift_id = data.get("shift_id")

    await session.execute(update(Shift).where(Shift.id == shift_id).values(is_closed=True))
    await session.commit()
    await state.clear()

    await callback.answer("✅ Tuzatishlar saqlandi")
    # ✅ Правки сохранены
    await admin_view_single_report(callback, session, shift_id_override=shift_id)


@router.callback_query(F.data.startswith("adm_change_date:"))
async def admin_change_date_request(callback: types.CallbackQuery):
    shift_id = int(callback.data.split(":")[1])

    builder = InlineKeyboardBuilder()
    today = datetime.now().strftime("%d.%m")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m")

    builder.button(text=f"📅 Bugun ({today})", callback_data=f"adm_apply_date:today:{shift_id}")
    builder.button(text=f"📅 Kecha ({yesterday})", callback_data=f"adm_apply_date:yesterday:{shift_id}")
    builder.button(text="⬅️ Ortga", callback_data=f"adm_edit_rep:{shift_id}")  # Возврат в меню правки
    builder.adjust(1)

    await callback.message.edit_text(
        "Ushbu smena uchun yangi sanani tanlang:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    # Выберите новую дату для этой смены:


@router.callback_query(F.data.startswith("adm_apply_date:"))
async def admin_apply_date_fix(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    parts = callback.data.split(":")
    date_type = parts[1]
    shift_id = int(parts[2])

    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    new_date = now if date_type == "today" else now - timedelta(days=1)

    # Обновляем дату
    await update_shift_date(session, shift_id, new_date)
    await callback.answer(f"📅 Sana {new_date.strftime('%d.%m')} га ўзгартирилди", show_alert=True)
    # 📅 Дата изменена на ...
    # ВАЖНО: возвращаем админа в меню ПРАВОК, а не просто в просмотр
    # Чтобы он видел кнопку "Завершить правки"
    await callback.message.edit_text(
        f"✅ Sana **{new_date.strftime('%d.%m.%Y')}** га ўзгартирилди.\n\nKeyingi qadam nima?",
        reply_markup=get_admin_edit_loop_kb(shift_id),
        parse_mode="Markdown"
    )
    # ✅ Дата изменена на ... Что делаем дальше?

# 1. Админ нажал кнопку "Изменить бензин"
@router.callback_query(F.data.startswith("adm_change_fuel:"))
async def admin_change_fuel_start(callback: types.CallbackQuery, state: FSMContext):
    shift_id = int(callback.data.split(":")[1])

    # Сохраняем ID смены и переводим в режим ожидания ввода
    await state.update_data(shift_id=shift_id)
    await state.set_state(AdminEdit.waiting_shift_fuel)

    # Кнопка отмены, если админ передумал
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Bekor qilish", callback_data=f"adm_edit_rep:{shift_id}")
    # ❌ Отмена
    await callback.message.edit_text(
        "⛽ **Benzin xarajatini o'zgartirish**\n\nYangi summani raqamlarda kiriting (masalan: `50000`):",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    # ⛽ **Изменение расхода на бензин**\n\nВведите новую сумму цифрами...
    await callback.answer()


# 2. Админ ввел новую сумму бензина
@router.message(AdminEdit.waiting_shift_fuel)
async def admin_change_fuel_process(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        # Пробуем перевести текст в число
        new_fuel = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("⚠️ Xato! Summani faqat raqamlarda kiriting.")
        # ⚠️ Ошибка! Введите сумму только цифрами.
        return

    # Достаем ID смены из стейта
    data = await state.get_data()
    shift_id = data.get("shift_id")

    # Обновляем в базе
    await session.execute(
        update(Shift).where(Shift.id == shift_id).values(fuel_expense=new_fuel)
    )
    await session.commit()

    # Выходим из режима ввода (но оставляем shift_id, чтобы админ мог продолжить правки)
    await state.set_state(None)

    # Сообщаем об успехе и возвращаем кнопки редактирования
    from keyboards.inline import get_admin_edit_loop_kb
    await message.answer(
        f"✅ Benzin xarajati **{new_fuel:,} so'm**ga yangilandi.\n\nKeyingi qadam nima?",
        reply_markup=get_admin_edit_loop_kb(shift_id),
        parse_mode="Markdown"
    )
    # ✅ Расход на бензин обновлен на... Что делаем дальше?


# АНАЛИТИКА
@router.callback_query(F.data == "admin_stats")
async def admin_stats_main(callback: types.CallbackQuery, session: AsyncSession):


    # 1. Считаем количество записей в базе (твой старый код)
    users_count = await session.scalar(select(func.count(User.id)))
    products_count = await session.scalar(select(func.count(Product.id)))
    kg_count = await session.scalar(select(func.count(Kindergarten.id)))

    # 2. Формируем текст: Сначала общая стата, потом призыв выбрать период
    text = (
        "📊 **BAZANING UMUMIY STATISTIKASI**\n\n"
        f"👥 Foydalanuvchilar: **{users_count}**\n"
        f"📦 Mahsulot turlari: **{products_count}**\n"
        f"🏫 Bog'chalar: **{kg_count}**\n"
        "───────────────────\n"
        "📈 **MOLIYAVIY ANALITIKA**\n"
        "Tushum va sof foydani hisoblash uchun davrni tanlang:"
    )
    # text = (
    #         "📊 **ОБЩАЯ СТАТИСТИКА БАЗЫ**\n\n"
    #         f"👥 Пользователей: **{users_count}**\n"
    #         f"📦 Видов товаров: **{products_count}**\n"
    #         f"🏫 Садиков: **{kg_count}**\n"
    #         "───────────────────\n"
    #         "📈 **ФИНАНСОВАЯ АНАЛИТИКА**\n"
    #         "Выберите период для расчета выручки и чистой прибыли:"
    #     )
    # 📊 **ОБЩАЯ СТАТИСТИКА БАЗЫ** ... Выберите период для расчета...
    # 3. Выводим новые кнопки выбора периода
    await callback.message.edit_text(
        text,
        reply_markup=get_analytics_period_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()

# 2. Финансовый Дашборд (Резюме)
@router.callback_query(F.data.startswith("adm_stats_period:"))
async def admin_stats_dashboard(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    period = callback.data.split(":")[1]

    # 1. Если админ нажал "Произвольный период"
    if period == "custom":
        await state.set_state(AdminStatsState.waiting_custom_period)

        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Отмена", callback_data="admin_stats")

        await callback.message.edit_text(
            "🗓 **Ixtiyoriy davr tahlili**\n\n"
            "Ikki sanani chiziqcha orqali `KK.OO.YYYY - KK.OO.YYYY` formatida kiriting.\n\n"
            "Misol: `01.04.2026 - 15.04.2026`",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        # "🗓 **Анализ за произвольный период**\n\n"
        #             "Введите две даты через дефис в формате `ДД.ММ.ГГГГ - ДД.ММ.ГГГГ`.\n\n"
        #             "Пример: `01.04.2026 - 15.04.2026`",
        return

    now = datetime.now()

    # 2. Определяем границы времени
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        period_name = "BUGUN" # СЕГОДНЯ

    elif period == "yesterday":
        start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        period_name = "KECHA" # ВЧЕРА

    elif period == "month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        months = ["YANVAR", "FEVRAL", "MART", "APREL", "MAY", "IYUN", "IYUL", "AVGUST", "SENTYABR", "OKTYABR",
                  "NOYABR", "DEKABR"]
        period_name = f"{months[now.month - 1]} {now.year}"

    # 3. ЕСЛИ ЭТО КАСТОМНЫЙ ПЕРИОД (например: 20260401-20260415)
    elif "-" in period:
        start_str, end_str = period.split("-")
        start_date = datetime.strptime(start_str, "%Y%m%d").replace(hour=0, minute=0, second=0)
        end_date = datetime.strptime(end_str, "%Y%m%d").replace(hour=23, minute=59, second=59)
        period_name = f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"

    # Получаем расчеты из базы
    stats = await get_dashboard_stats(session, start_date, end_date)
    profitability = (stats["profit"] / stats["revenue"] * 100) if stats["revenue"] > 0 else 0

    text = (
        f"📊 **{period_name} UCHUN NATIJALAR**:\n\n"
        f"💰 Aylanma (Tushum): **{int(stats['revenue']):,} so'm**\n"
        f"📉 Mahsulot xarajatlari: **{int(stats['cost']):,} so'm**\n"
        f"⛽️ Benzin xarajatlari: **{int(stats['fuel']):,} so'm**\n"
        f"───────────────────\n"
        f"🏆 **SOF FOYDA: {int(stats['profit']):,} so'm**\n\n"
        f"📈 Biznes rentabelligi: **{profitability:.1f}%**"
    )
    # text = (
    #         f"📊 **ИТОГИ ЗА {period_name}**:\n\n"
    #         f"💰 Оборот (Выручка): **{int(stats['revenue']):,} сум**\n"
    #         f"📉 Затраты на товар: **{int(stats['cost']):,} сум**\n"
    #         f"⛽️ Затраты на бензин: **{int(stats['fuel']):,} сум**\n"
    #         f"───────────────────\n"
    #         f"🏆 **ЧИСТАЯ ПРИБЫЛЬ: {int(stats['profit']):,} сум**\n\n"
    #         f"📈 Рентабельность бизнеса: **{profitability:.1f}%**"
    #     )

    from keyboards.inline import get_dashboard_kb
    await callback.message.edit_text(text, reply_markup=get_dashboard_kb(period), parse_mode="Markdown")

@router.callback_query(F.data.startswith("adm_stats_drivers:"))
async def admin_stats_drivers_list(callback: types.CallbackQuery, session: AsyncSession):
    # Разбираем: adm_stats_drivers : период : страница
    parts = callback.data.split(":")
    period = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0

    # Повторяем логику дат (такую же, как в дашборде)
    now = datetime.now()
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0)
        end_date = now.replace(hour=23, minute=59, second=59)
    elif period == "yesterday":
        start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0)
        end_date = start_date.replace(hour=23, minute=59, second=59)
    elif period == "month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0)
        end_date = now.replace(hour=23, minute=59, second=59)
    # --- ДОБАВЬ ВОТ ЭТО ---
    elif "-" in period:
        start_str, end_str = period.split("-")
        start_date = datetime.strptime(start_str, "%Y%m%d").replace(hour=0, minute=0, second=0)
        end_date = datetime.strptime(end_str, "%Y%m%d").replace(hour=23, minute=59, second=59)

    # Получаем данные
    drivers_data = await get_drivers_performance(session, start_date, end_date)

    if not drivers_data:
        await callback.answer("Ushbu davr uchun haydovchilar bo'yicha ma'lumot topilmadi.", show_alert=True)
        # "За этот период данных по водителям нет."
        return

    await callback.message.edit_text(
        f"👥 **Haydovchilar samaradorligi**\n"
        f"Davr: {period.upper()}\n"
        f"(Xarid va benzin xarajatlari chegirilgandagi sof foyda)",
        reply_markup=get_drivers_stats_kb(drivers_data, period, page),
        parse_mode="Markdown"
    )
    # f"👥 **Эффективность водителей**\n"
    #         f"Период: {period.upper()}\n"
    #         f"(Чистая прибыль после вычета закупа и бензина)",


# @router.callback_query(F.data == "adm_stats_export_all:xlsx")
# async def admin_export_global_excel(callback: types.CallbackQuery, session: AsyncSession):
#     await callback.answer("⏳ Формирую детальный отчет с итогами...", show_alert=False)
#
#     raw_data = await get_all_deliveries_for_export(session)
#
#     if not raw_data:
#         await callback.answer("❌ Нет данных для экспорта", show_alert=True)
#         return
#
#     df = pd.DataFrame(raw_data)
#     df['Дата'] = pd.to_datetime(df['Дата']).dt.strftime('%d.%m.%Y %H:%M')
#
#     # --- УМНЫЙ РАСЧЕТ БЕНЗИНА ---
#     # 1. Если бензин не указан (None), ставим 0
#     df['Бензин_Смены'] = df['Бензин_Смены'].fillna(0).astype(float)
#
#     # 2. Считаем, сколько всего отгрузок было в каждой смене
#     shift_counts = df.groupby('shift_id')['shift_id'].transform('count')
#
#     # 3. Размазываем бензин поровну на все отгрузки этой смены
#     df['Бензин (доля)'] = df['Бензин_Смены'] / shift_counts
#
#     # 4. Считаем ЧИСТУЮ маржу: Выручка - Закуп - Бензин
#     df['Прибыль_Маржа'] = df['Выручка'] - df['Закуп_сумма'] - df['Бензин (доля)']
#
#     # Удаляем технические колонки (они не нужны бухгалтеру)
#     df = df.drop(columns=['shift_id', 'Бензин_Смены'])
#
#     # --- СВОДНЫЕ ТАБЛИЦЫ ---
#     kg_summary = df.groupby("Садик").agg({
#         "Выручка": "sum",
#         "Закуп_сумма": "sum",
#         "Бензин (доля)": "sum",  # Добавили бензин
#         "Прибыль_Маржа": "sum",
#         "Факт": "count"
#     }).rename(columns={"Факт": "Кол_во_отгрузок"}).reset_index()
#
#     prod_summary = df.groupby("Товар").agg({
#         "Факт": "sum",
#         "Выручка": "sum",
#         "Закуп_сумма": "sum",
#         "Бензин (доля)": "sum",  # Добавили бензин
#         "Прибыль_Маржа": "sum"
#     }).reset_index()
#
#     # --- ДОБАВЛЯЕМ СТРОКИ "ИТОГО:" ---
#     totals_log = pd.DataFrame([{
#         'Дата': 'ИТОГО:',
#         'План': df['План'].sum(),
#         'Факт': df['Факт'].sum(),
#         'Выручка': df['Выручка'].sum(),
#         'Закуп_сумма': df['Закуп_сумма'].sum(),
#         'Бензин (доля)': df['Бензин (доля)'].sum(),  # Итог по бензину
#         'Прибыль_Маржа': df['Прибыль_Маржа'].sum()
#     }])
#     df = pd.concat([df, totals_log], ignore_index=True)
#
#     totals_kg = pd.DataFrame([{
#         'Садик': 'ИТОГО:',
#         'Кол_во_отгрузок': kg_summary['Кол_во_отгрузок'].sum(),
#         'Выручка': kg_summary['Выручка'].sum(),
#         'Закуп_сумма': kg_summary['Закуп_сумма'].sum(),
#         'Бензин (доля)': kg_summary['Бензин (доля)'].sum(),
#         'Прибыль_Маржа': kg_summary['Прибыль_Маржа'].sum()
#     }])
#     kg_summary = pd.concat([kg_summary, totals_kg], ignore_index=True)
#
#     totals_prod = pd.DataFrame([{
#         'Товар': 'ИТОГО:',
#         'Факт': prod_summary['Факт'].sum(),
#         'Выручка': prod_summary['Выручка'].sum(),
#         'Закуп_сумма': prod_summary['Закуп_сумма'].sum(),
#         'Бензин (доля)': prod_summary['Бензин (доля)'].sum(),
#         'Прибыль_Маржа': prod_summary['Прибыль_Маржа'].sum()
#     }])
#     prod_summary = pd.concat([prod_summary, totals_prod], ignore_index=True)
#
#     # --- ЗАПИСЬ В EXCEL ---
#     output = BytesIO()
#     with pd.ExcelWriter(output, engine='openpyxl') as writer:
#         df.to_excel(writer, sheet_name="Общий лог", index=False)
#         kg_summary.to_excel(writer, sheet_name="Итоги по Садикам", index=False)
#         prod_summary.to_excel(writer, sheet_name="Итоги по Товарам", index=False)
#
#         # Расширяем колонки
#         for sheet_name in writer.sheets:
#             worksheet = writer.sheets[sheet_name]
#             for col in worksheet.columns:
#                 max_length = 0
#                 column_letter = col[0].column_letter
#                 for cell in col:
#                     try:
#                         if cell.value:
#                             max_length = max(max_length, len(str(cell.value)))
#                     except:
#                         pass
#                 worksheet.column_dimensions[column_letter].width = max_length + 2
#
#     output.seek(0)
#     file_content = output.getvalue()
#
#     document = BufferedInputFile(
#         file_content,
#         filename=f"Global_Report_{datetime.now().strftime('%d_%m_%Y')}.xlsx"
#     )
#
#     await callback.message.answer_document(
#         document,
#         caption="✅ Глобальный отчет сформирован.\n\n"
#                 "В файле 3 листа (с учетом бензина и итогами):\n"
#                 "1. Общий лог операций\n"
#                 "2. Итоги по каждому садику\n"
#                 "3. Итоги по видам товаров"
#     )


@router.message(AdminStatsState.waiting_custom_period, F.text)
async def admin_process_custom_dates(message: types.Message, state: FSMContext, session: AsyncSession):
    text = message.text.strip()

    try:
        # Пытаемся разбить текст на две даты
        start_str, end_str = text.split("-")

        # Проверяем правильность формата и сразу ставим правильное время (00:00 и 23:59)
        start_date = datetime.strptime(start_str.strip(), "%d.%m.%Y").replace(hour=0, minute=0, second=0)
        end_date = datetime.strptime(end_str.strip(), "%d.%m.%Y").replace(hour=23, minute=59, second=59)

        # Защита: дата начала не может быть позже даты конца
        if start_date > end_date:
            raise ValueError("Boshlanish sanasi tugash sanasidan katta")
            # "Дата начала больше даты конца"

    except ValueError:
        await message.answer(
            "❌ **Format xatosi!**\nIltimos, sanalarni худди намунадагидек киритинг:\n`01.04.2026 - 15.04.2026`",
            parse_mode="Markdown")
        # "❌ **Ошибка формата!**\nПожалуйста, введите даты строго как в примере:\n`01.04.2026 - 15.04.2026`",
        return

    # Выходим из состояния
    await state.clear()

    # Формируем компактную строку для callback_data (чтобы влезло в кнопку Telegram)
    period_code = f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"
    period_name = f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"

    # --- СЧИТАЕМ СТАТИСТИКУ ПРЯМО ЗДЕСЬ ---
    stats = await get_dashboard_stats(session, start_date, end_date)
    profitability = (stats["profit"] / stats["revenue"] * 100) if stats["revenue"] > 0 else 0

    report_text = (
        f"📊 **{period_name} UCHUN NATIJALAR**:\n\n"
        f"💰 Aylanma (Tushum): **{int(stats['revenue']):,} so'm**\n"
        f"📉 Mahsulot xarajatlari: **{int(stats['cost']):,} so'm**\n"
        f"⛽️ Benzin xarajatlari: **{int(stats['fuel']):,} so'm**\n"
        f"───────────────────\n"
        f"🏆 **SOF FOYDA: {int(stats['profit']):,} so'm**\n\n"
        f"📈 Biznes rentabelligi: **{profitability:.1f}%**"
    )
    # report_text = (
    #         f"📊 **ИТОГИ ЗА {period_name}**:\n\n"
    #         f"💰 Оборот (Выручка): **{int(stats['revenue']):,} сум**\n"
    #         f"📉 Затраты на товар: **{int(stats['cost']):,} сум**\n"
    #         f"⛽️ Затраты на бензин: **{int(stats['fuel']):,} сум**\n"
    #         f"───────────────────\n"
    #         f"🏆 **ЧИСТАЯ ПРИБЫЛЬ: {int(stats['profit']):,} сум**\n\n"
    #         f"📈 Рентабельность бизнеса: **{profitability:.1f}%**"
    #     )

    # Отправляем сообщение как обычный ответ на текст (через message.answer)
    from keyboards.inline import get_dashboard_kb
    await message.answer(report_text, reply_markup=get_dashboard_kb(period_code), parse_mode="Markdown")


# --- 1. УМНЫЙ ПАРСЕР ДАТ ---
def parse_dates_from_period(period: str):
    now = datetime.now()
    # Строго обнуляем микросекунды, чтобы не было смещений
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    if period == "today":
        return today_start, today_end

    elif period == "yesterday":
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = yesterday_start.replace(hour=23, minute=59, second=59, microsecond=999999)
        return yesterday_start, yesterday_end

    elif period == "month":
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return month_start, today_end

    elif "-" in period:
        try:
            start_str, end_str = period.split("-")
            start = datetime.strptime(start_str, "%Y%m%d").replace(hour=0, minute=0, second=0, microsecond=0)
            end = datetime.strptime(end_str, "%Y%m%d").replace(hour=23, minute=59, second=59, microsecond=999999)
            return start, end
        except:
            return today_start, today_end

    return today_start, today_end


# --- ЭКСПОРТ EXCEL ЗА ПЕРИОД ---
# @router.callback_query(F.data.startswith("adm_stats_dl_xlsx:"))
# async def admin_export_period_xlsx(callback: types.CallbackQuery, session: AsyncSession):
#     period = callback.data.split(":")[1]
#     start, end = parse_dates_from_period(period)
#
#     await callback.answer("Генерирую Excel...")
#
#     # Используем твою логику из Глобального отчета, но с фильтром по датам
#     # (Здесь нужно вызвать get_all_deliveries_for_export, но добавить фильтр start/end)
#     # Для краткости: логика идентична глобальному, просто в SQL запросе добавляешь WHERE по датам
#     pass

# --- 2. ГЕНЕРАТОР EXCEL ---
@router.callback_query(F.data.startswith("adm_stats_dl_xlsx:"))
@router.callback_query(F.data == "adm_stats_export_all:xlsx")
async def admin_export_universal_excel(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer("⏳ Batafsil hisobot tayyorlanyapti... Bir necha soniya vaqt oladi.", show_alert=False)
    # "⏳ Формирую детальный отчет... Это займет пару секунд."

    if "dl_xlsx" in callback.data:
        period = callback.data.split(":")[1]
        start_date, end_date = parse_dates_from_period(period)
        if start_date.date() == end_date.date():
            filename_prefix = f"Hisobot_{start_date.strftime('%d%m')}"
            # Report_
        else:
            filename_prefix = f"Hisobot_{start_date.strftime('%d%m')}-{end_date.strftime('%d%m')}"
            # Report_
    else:
        start_date, end_date = None, None
        filename_prefix = "Global_Hisobot" # _Report

    raw_data = await get_all_deliveries_for_export(session, start_date, end_date)

    if not raw_data:
        await callback.answer("❌ Ushbu davr uchun birorta ham yetkazib berish topilmadi.", show_alert=True)
        # "❌ За этот период нет ни одной отгрузки."
        return

    df = pd.DataFrame(raw_data)

    mapping = {
        'Дата': 'Sana',
        'Водитель': 'Haydovchi',
        'Садик': 'Bog\'cha',
        'Товар': 'Mahsulot',
        'Ед_изм': 'O\'lchov_birligi',
        'План': 'Reja',
        'Факт': 'Fakt',
        'Цена_Садик': 'Bog\'cha_narxi',
        'Цена_Закуп': 'Xarid_narxi',
        'Бензин_Смены': 'Smena_benzini',
        'Выручка': 'Tushum',
        'Закуп_сумма': 'Xarid_summasi'
    }
    df = df.rename(columns=mapping)

    df['Sana'] = pd.to_datetime(df['Sana']).dt.strftime('%d.%m.%Y %H:%M')
    df['Smena_benzini'] = df['Smena_benzini'].fillna(0).astype(float)

    shift_counts = df.groupby('shift_id')['shift_id'].transform('count')
    df['Benzin (ulushi)'] = df['Smena_benzini'] / shift_counts
    df['Foyda_Marja'] = df['Tushum'] - df['Xarid_summasi'] - df['Benzin (ulushi)']
    df = df.drop(columns=['shift_id', 'Smena_benzini'])

    kg_summary = df.groupby("Bog'cha").agg({
        "Tushum": "sum", "Xarid_summasi": "sum", "Benzin (ulushi)": "sum",
        "Foyda_Marja": "sum", "Fakt": "count"
    }).rename(columns={"Fakt": "Yetkazib_berishlar_soni"}).reset_index()

    prod_summary = df.groupby("Mahsulot").agg({
        "Fakt": "sum", "Tushum": "sum", "Xarid_summasi": "sum",
        "Benzin (ulushi)": "sum", "Foyda_Marja": "sum"
    }).reset_index()

    df = pd.concat([df, pd.DataFrame([{
        'Sana': 'JAMI:', 'Reja': df['Reja'].sum(), 'Fakt': df['Fakt'].sum(),
        'Tushum': df['Tushum'].sum(), 'Xarid_summasi': df['Xarid_summasi'].sum(),
        'Benzin (ulushi)': df['Benzin (ulushi)'].sum(), 'Foyda_Marja': df['Foyda_Marja'].sum()
    }])], ignore_index=True)

    kg_summary = pd.concat([kg_summary, pd.DataFrame([{
        'Bog\'cha': 'JAMI:', 'Yetkazib_berishlar_soni': kg_summary['Yetkazib_berishlar_soni'].sum(),
        'Tushum': kg_summary['Tushum'].sum(), 'Xarid_summasi': kg_summary['Xarid_summasi'].sum(),
        'Benzin (ulushi)': kg_summary['Benzin (ulushi)'].sum(), 'Foyda_Marja': kg_summary['Foyda_Marja'].sum()
    }])], ignore_index=True)

    prod_summary = pd.concat([prod_summary, pd.DataFrame([{
        'Mahsulot': 'JAMI:', 'Fakt': prod_summary['Fakt'].sum(),
        'Tushum': prod_summary['Tushum'].sum(), 'Xarid_summasi': prod_summary['Xarid_summasi'].sum(),
        'Benzin (ulushi)': prod_summary['Benzin (ulushi)'].sum(), 'Foyda_Marja': prod_summary['Foyda_Marja'].sum()
    }])], ignore_index=True)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Umumiy log", index=False) # "Общий лог"
        kg_summary.to_excel(writer, sheet_name="Bog'chalar bo'yicha", index=False) # "Итоги по Садикам"
        prod_summary.to_excel(writer, sheet_name="Mahsulotlar bo'yicha", index=False) # "Итоги по Товарам"

        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for col in worksheet.columns:
                max_length = 0
                for cell in col:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                worksheet.column_dimensions[col[0].column_letter].width = max_length + 2

    output.seek(0)
    document = BufferedInputFile(output.getvalue(), filename=f"{filename_prefix}.xlsx")

    await callback.message.answer_document(document, caption="✅ Excel-hisobot muvaffaqiyatli tayyorlandi.")
    # "✅ Excel-отчет успешно сформирован."

# df = pd.DataFrame(raw_data)
#     df['Дата'] = pd.to_datetime(df['Дата']).dt.strftime('%d.%m.%Y %H:%M')
#     df['Бензин_Смены'] = df['Бензин_Смены'].fillna(0).astype(float)
#
#     shift_counts = df.groupby('shift_id')['shift_id'].transform('count')
#     df['Бензин (доля)'] = df['Бензин_Смены'] / shift_counts
#     df['Прибыль_Маржа'] = df['Выручка'] - df['Закуп_сумма'] - df['Бензин (доля)']
#     df = df.drop(columns=['shift_id', 'Бензин_Смены'])
#
#     kg_summary = df.groupby("Садик").agg({
#         "Выручка": "sum", "Закуп_сумма": "sum", "Бензин (доля)": "sum",
#         "Прибыль_Маржа": "sum", "Факт": "count"
#     }).rename(columns={"Факт": "Кол_во_отгрузок"}).reset_index()
#
#     prod_summary = df.groupby("Товар").agg({
#         "Факт": "sum", "Выручка": "sum", "Закуп_сумма": "sum",
#         "Бензин (доля)": "sum", "Прибыль_Маржа": "sum"
#     }).reset_index()
#
#     df = pd.concat([df, pd.DataFrame([{
#         'Дата': 'ИТОГО:', 'План': df['План'].sum(), 'Факт': df['Факт'].sum(),
#         'Выручка': df['Выручка'].sum(), 'Закуп_сумма': df['Закуп_сумма'].sum(),
#         'Бензин (доля)': df['Бензин (доля)'].sum(), 'Прибыль_Маржа': df['Прибыль_Маржа'].sum()
#     }])], ignore_index=True)
#
#     kg_summary = pd.concat([kg_summary, pd.DataFrame([{
#         'Садик': 'ИТОГО:', 'Кол_во_отгрузок': kg_summary['Кол_во_отгрузок'].sum(),
#         'Выручка': kg_summary['Выручка'].sum(), 'Закуп_сумма': kg_summary['Закуп_сумма'].sum(),
#         'Бензин (доля)': kg_summary['Бензин (доля)'].sum(), 'Прибыль_Маржа': kg_summary['Прибыль_Маржа'].sum()
#     }])], ignore_index=True)
#
#     prod_summary = pd.concat([prod_summary, pd.DataFrame([{
#         'Товар': 'ИТОГО:', 'Факт': prod_summary['Факт'].sum(),
#         'Выручка': prod_summary['Выручка'].sum(), 'Закуп_сумма': prod_summary['Закуп_сумма'].sum(),
#         'Бензин (доля)': prod_summary['Бензин (доля)'].sum(), 'Прибыль_Маржа': prod_summary['Прибыль_Маржа'].sum()
#     }])], ignore_index=True)

# --- 3. ГЕНЕРАТОР PDF ---
@router.callback_query(F.data.startswith("adm_stats_dl_pdf:"))
@router.callback_query(F.data == "adm_stats_export_all:pdf")
async def admin_export_universal_pdf(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer("⏳ Batafsil PDF tayyorlanyapti (3 ta bo'lim)...", show_alert=False)
    # "⏳ Формирую детальный PDF (3 раздела)..."

    if "dl_pdf" in callback.data:
        period = callback.data.split(":")[1]
        start_date, end_date = parse_dates_from_period(period)

        if start_date.date() == end_date.date():
            title = f"{start_date.strftime('%d.%m.%Y')} SANA UCHUN HISOBOT"
            # ОТЧЕТ ЗА
            filename_prefix = f"Hisobot_{start_date.strftime('%d%m')}"
            # Report_
        else:
            title = f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')} DAVRI UCHUN HISOBOT"
            # ОТЧЕТ ЗА
            filename_prefix = f"Hisobot_{start_date.strftime('%d%m')}-{end_date.strftime('%d%m')}"
            # Report_
    else:
        start_date, end_date = None, None
        # ГЛОБАЛЬНЫЙ ОТЧЕТ (ВСЕ ВРЕМЯ)
        title = "UMUMIY HISOBOT (BARCHA VAQT UCHUN)"
        filename_prefix = "Umumiy_Hisobot" # Global_Report

    raw_data = await get_all_deliveries_for_export(session, start_date, end_date)
    if not raw_data:
        await callback.answer("❌ Ushbu davr uchun ma'lumot topilmadi.", show_alert=True)
        # "❌ За этот период нет данных.",
        return

    df = pd.DataFrame(raw_data)

    # Дополнил маппинг недостающими полями
    df = df.rename(columns={
        'Дата': 'Sana',
        'Водитель': 'Haydovchi',  # <--- Добавил
        'Садик': 'Bog\'cha',
        'Товар': 'Mahsulot',
        'Ед_изм': 'O\'lchov_birligi',  # <--- Добавил
        'План': 'Reja',
        'Факт': 'Fakt',
        'Цена_Садик': 'Bog\'cha_narxi',  # <--- ВОТ ЭТО БЫЛО НУЖНО
        'Цена_Закуп': 'Xarid_narxi',  # <--- И ЭТО ТОЖЕ
        'Бензин_Смены': 'Smena_benzini',
        'Выручка': 'Tushum',
        'Закуп_сумма': 'Xarid_summasi'
    })


    df['Sana'] = pd.to_datetime(df['Sana']).dt.strftime('%d.%m %H:%M')
    df['Smena_benzini'] = df['Smena_benzini'].fillna(0).astype(float)

    shift_counts = df.groupby('shift_id')['shift_id'].transform('count')
    df['Benzin (ulushi)'] = df['Smena_benzini'] / shift_counts
    df['Sof_foyda_marja'] = df['Tushum'] - df['Xarid_summasi'] - df['Benzin (ulushi)']
    df = df.drop(columns=['shift_id', 'Smena_benzini'])

    kg_summary = df.groupby("Bog'cha").agg({
        "Tushum": "sum", "Xarid_summasi": "sum", "Benzin (ulushi)": "sum",
        "Sof_foyda_marja": "sum", "Fakt": "count"
    }).rename(columns={"Fakt": "Soni"}).reset_index()

    prod_summary = df.groupby("Mahsulot").agg({
        "Fakt": "sum", "Tushum": "sum", "Xarid_summasi": "sum",
        "Benzin (ulushi)": "sum", "Sof_foyda_marja": "sum"
    }).reset_index()

    df = pd.concat([df, pd.DataFrame([{
        'Sana': 'JAMI:', 'Reja': df['Reja'].sum(), 'Fakt': df['Fakt'].sum(),
        'Tushum': df['Tushum'].sum(), 'Xarid_summasi': df['Xarid_summasi'].sum(),
        'Benzin (ulushi)': df['Benzin (ulushi)'].sum(), 'Sof_foyda_marja': df['Sof_foyda_marja'].sum()
    }])], ignore_index=True)

    kg_summary = pd.concat([kg_summary, pd.DataFrame([{
        'Bog\'cha': 'JAMI:', 'Soni': kg_summary['Soni'].sum(),
        'Tushum': kg_summary['Tushum'].sum(), 'Xarid_summasi': kg_summary['Xarid_summasi'].sum(),
        'Benzin (ulushi)': kg_summary['Benzin (ulushi)'].sum(), 'Sof_foyda_marja': kg_summary['Sof_foyda_marja'].sum()
    }])], ignore_index=True)

    prod_summary = pd.concat([prod_summary, pd.DataFrame([{
        'Mahsulot': 'JAMI:', 'Fakt': prod_summary['Fakt'].sum(),
        'Tushum': prod_summary['Tushum'].sum(), 'Xarid_summasi': prod_summary['Xarid_summasi'].sum(),
        'Benzin (ulushi)': prod_summary['Benzin (ulushi)'].sum(),
        'Sof_foyda_marja': prod_summary['Sof_foyda_marja'].sum()
    }])], ignore_index=True)

    pdf = FPDF(orientation="L")
    pdf.add_page()

    font_path = "Fonts/arial.ttf"
    if not os.path.exists(font_path):
        await callback.message.answer(f"❌ '{font_path}' shrifti topilmadi.")
        # f"❌ Шрифт '{font_path}' не найден."
        return
    pdf.add_font('MyArial', '', font_path, uni=True)

    def fmt(val, is_num=True, max_len=15):
        if pd.isna(val): return ""
        if is_num:
            try:
                return f"{int(float(val)):,}"
            except:
                return ""
        return str(val)[:max_len]

    pdf.set_font('MyArial', '', 14)
    pdf.cell(0, 10, title + " - 1-SAHIFA (UMUMIY LOG)", ln=True, align='C')
    pdf.ln(2)

    pdf.set_font('MyArial', '', 7)
    headers = [("Sana", 20), ("Haydovchi", 25), ("Bog'cha", 28), ("Mahsulot", 25),
               ("Birl.", 8), ("Reja", 10), ("Fakt", 10), ("Bog'.N", 18),
               ("Xar.N", 18), ("Tushum", 22), ("Xarid", 22), ("Benz.", 18), ("Marja", 24)]

    for h, w in headers:
        pdf.cell(w, 7, h, 1, align='C')
    pdf.ln()

    for _, row in df.iterrows():
        if pdf.get_y() > 185:
            pdf.add_page()
            for h, w in headers: pdf.cell(w, 7, h, 1, align='C')
            pdf.ln()

        pdf.cell(20, 6, fmt(row.get('Sana'), False, 11), 1)
        pdf.cell(25, 6, fmt(row.get('Haydovchi'), False), 1)
        pdf.cell(28, 6, fmt(row.get('Bog\'cha'), False), 1)
        pdf.cell(25, 6, fmt(row.get('Mahsulot'), False), 1)
        pdf.cell(8, 6, fmt(row.get('O\'lchov_birligi'), False), 1, align='C')
        pdf.cell(10, 6, fmt(row.get('Reja'), False), 1, align='C')
        pdf.cell(10, 6, fmt(row.get('Fakt'), False), 1, align='C')
        pdf.cell(18, 6, fmt(row.get('Bog\'cha_narxi')), 1, align='R')
        pdf.cell(18, 6, fmt(row.get('Xarid_narxi')), 1, align='R')
        pdf.cell(22, 6, fmt(row.get('Tushum')), 1, align='R')
        pdf.cell(22, 6, fmt(row.get('Xarid_summasi')), 1, align='R')
        pdf.cell(18, 6, fmt(row.get('Benzin (ulushi)')), 1, align='R')
        pdf.cell(24, 6, fmt(row.get('Sof_foyda_marja')), 1, align='R')
        pdf.ln()

    pdf.add_page()
    pdf.set_font('MyArial', '', 14)
    pdf.cell(0, 10, "2-SAHIFA: BOG'CHALAR BO'YICHA YAKUNLAR", ln=True, align='C')
    pdf.ln(5)

    pdf.set_font('MyArial', '', 10)
    kg_headers = [("Bog'cha", 60), ("Soni", 25), ("Tushum", 40), ("Xarid", 40), ("Benzin", 35), ("Marja", 40)]
    for h, w in kg_headers: pdf.cell(w, 8, h, 1, align='C')
    pdf.ln()

    for _, row in kg_summary.iterrows():
        pdf.cell(60, 8, fmt(row.get('Bog\'cha'), False, 30), 1)
        pdf.cell(25, 8, fmt(row.get('Soni'), False), 1, align='C')
        pdf.cell(40, 8, fmt(row.get('Tushum')), 1, align='R')
        pdf.cell(40, 8, fmt(row.get('Xarid_summasi')), 1, align='R')
        pdf.cell(35, 8, fmt(row.get('Benzin (ulushi)')), 1, align='R')
        pdf.cell(40, 8, fmt(row.get('Sof_foyda_marja')), 1, align='R')
        pdf.ln()

    pdf.add_page()
    pdf.set_font('MyArial', '', 14)
    pdf.cell(0, 10, "3-SAHIFA: MAHSULOTLAR BO'YICHA YAKUNLAR", ln=True, align='C')
    pdf.ln(5)

    pdf.set_font('MyArial', '', 10)
    prod_headers = [("Mahsulot", 60), ("Fakt", 25), ("Tushum", 40), ("Xarid", 40), ("Benzin", 35), ("Marja", 40)]
    for h, w in prod_headers: pdf.cell(w, 8, h, 1, align='C')
    pdf.ln()

    for _, row in prod_summary.iterrows():
        pdf.cell(60, 8, fmt(row.get('Mahsulot'), False, 30), 1)
        pdf.cell(25, 8, fmt(row.get('Fakt'), False), 1, align='C')
        pdf.cell(40, 8, fmt(row.get('Tushum')), 1, align='R')
        pdf.cell(40, 8, fmt(row.get('Xarid_summasi')), 1, align='R')
        pdf.cell(35, 8, fmt(row.get('Benzin (ulushi)')), 1, align='R')
        pdf.cell(40, 8, fmt(row.get('Sof_foyda_marja')), 1, align='R')
        pdf.ln()

    pdf_output = pdf.output()
    document = BufferedInputFile(pdf_output, filename=f"{filename_prefix}.pdf")
    # "✅ Детальный PDF-отчет сформирован (3 листа)."
    await callback.message.answer_document(document, caption="✅ Batafsil PDF-hisobot tayyorlandi (3 ta sahifa).")

# df = pd.DataFrame(raw_data)
#     df['Дата'] = pd.to_datetime(df['Дата']).dt.strftime('%d.%m %H:%M')
#     df['Бензин_Смены'] = df['Бензин_Смены'].fillna(0).astype(float)
#
#     shift_counts = df.groupby('shift_id')['shift_id'].transform('count')
#     df['Бензин (доля)'] = df['Бензин_Смены'] / shift_counts
#     df['Прибыль_Маржа'] = df['Выручка'] - df['Закуп_сумма'] - df['Бензин (доля)']
#     df = df.drop(columns=['shift_id', 'Бензин_Смены'])
#
#     kg_summary = df.groupby("Садик").agg({
#         "Выручка": "sum", "Закуп_сумма": "sum", "Бензин (доля)": "sum",
#         "Прибыль_Маржа": "sum", "Факт": "count"
#     }).rename(columns={"Факт": "Кол_во"}).reset_index()
#
#     prod_summary = df.groupby("Товар").agg({
#         "Факт": "sum", "Выручка": "sum", "Закуп_сумма": "sum",
#         "Бензин (доля)": "sum", "Прибыль_Маржа": "sum"
#     }).reset_index()
#
#     df = pd.concat([df, pd.DataFrame([{
#         'Дата': 'ИТОГО:', 'План': df['План'].sum(), 'Факт': df['Факт'].sum(),
#         'Выручка': df['Выручка'].sum(), 'Закуп_сумма': df['Закуп_сумма'].sum(),
#         'Бензин (доля)': df['Бензин (доля)'].sum(), 'Прибыль_Маржа': df['Прибыль_Маржа'].sum()
#     }])], ignore_index=True)
#
#     kg_summary = pd.concat([kg_summary, pd.DataFrame([{
#         'Садик': 'ИТОГО:', 'Кол_во': kg_summary['Кол_во'].sum(),
#         'Выручка': kg_summary['Выручка'].sum(), 'Закуп_сумма': kg_summary['Закуп_сумма'].sum(),
#         'Бензин (доля)': kg_summary['Бензин (доля)'].sum(), 'Прибыль_Маржа': kg_summary['Прибыль_Маржа'].sum()
#     }])], ignore_index=True)
#
#     prod_summary = pd.concat([prod_summary, pd.DataFrame([{
#         'Товар': 'ИТОГО:', 'Факт': prod_summary['Факт'].sum(),
#         'Выручка': prod_summary['Выручка'].sum(), 'Закуп_сумма': prod_summary['Закуп_сумма'].sum(),
#         'Бензин (доля)': prod_summary['Бензин (доля)'].sum(), 'Прибыль_Маржа': prod_summary['Прибыль_Маржа'].sum()
#     }])], ignore_index=True)
# pdf.set_font('MyArial', '', 14)
#     pdf.cell(0, 10, title + " - ЛИСТ 1 (ОБЩИЙ ЛОГ)", ln=True, align='C')
#     pdf.ln(2)
#
#     pdf.set_font('MyArial', '', 7)
#     headers = [("Дата", 20), ("Водитель", 25), ("Садик", 28), ("Товар", 25),
#                ("Ед", 8), ("План", 10), ("Факт", 10), ("Ц.Сад", 18),
#                ("Ц.Зак", 18), ("Выручка", 22), ("Закуп", 22), ("Бенз", 18), ("Маржа", 24)]
#
#     for h, w in headers:
#         pdf.cell(w, 7, h, 1, align='C')
#     pdf.ln()
#
#     for _, row in df.iterrows():
#         if pdf.get_y() > 185:
#             pdf.add_page()
#             for h, w in headers: pdf.cell(w, 7, h, 1, align='C')
#             pdf.ln()
#
#         pdf.cell(20, 6, fmt(row.get('Дата'), False, 11), 1)
#         pdf.cell(25, 6, fmt(row.get('Водитель'), False), 1)
#         pdf.cell(28, 6, fmt(row.get('Садик'), False), 1)
#         pdf.cell(25, 6, fmt(row.get('Товар'), False), 1)
#         pdf.cell(8, 6, fmt(row.get('Ед_изм'), False), 1, align='C')
#         pdf.cell(10, 6, fmt(row.get('План'), False), 1, align='C')
#         pdf.cell(10, 6, fmt(row.get('Факт'), False), 1, align='C')
#         pdf.cell(18, 6, fmt(row.get('Цена_Садик')), 1, align='R')
#         pdf.cell(18, 6, fmt(row.get('Цена_Закуп')), 1, align='R')
#         pdf.cell(22, 6, fmt(row.get('Выручка')), 1, align='R')
#         pdf.cell(22, 6, fmt(row.get('Закуп_сумма')), 1, align='R')
#         pdf.cell(18, 6, fmt(row.get('Бензин (доля)')), 1, align='R')
#         pdf.cell(24, 6, fmt(row.get('Прибыль_Маржа')), 1, align='R')
#         pdf.ln()
#
#     pdf.add_page()
#     pdf.set_font('MyArial', '', 14)
#     pdf.cell(0, 10, "ЛИСТ 2: ИТОГИ ПО САДИКАМ", ln=True, align='C')
#     pdf.ln(5)
#
#     pdf.set_font('MyArial', '', 10)
#     kg_headers = [("Садик", 60), ("Отгрузки", 25), ("Выручка", 40), ("Закуп", 40), ("Бензин", 35), ("Маржа", 40)]
#     for h, w in kg_headers: pdf.cell(w, 8, h, 1, align='C')
#     pdf.ln()
#
#     for _, row in kg_summary.iterrows():
#         pdf.cell(60, 8, fmt(row.get('Садик'), False, 30), 1)
#         pdf.cell(25, 8, fmt(row.get('Кол_во'), False), 1, align='C')
#         pdf.cell(40, 8, fmt(row.get('Выручка')), 1, align='R')
#         pdf.cell(40, 8, fmt(row.get('Закуп_сумма')), 1, align='R')
#         pdf.cell(35, 8, fmt(row.get('Бензин (доля)')), 1, align='R')
#         pdf.cell(40, 8, fmt(row.get('Прибыль_Маржа')), 1, align='R')
#         pdf.ln()
#
#     pdf.add_page()
#     pdf.set_font('MyArial', '', 14)
#     pdf.cell(0, 10, "ЛИСТ 3: ИТОГИ ПО ТОВАРАМ", ln=True, align='C')
#     pdf.ln(5)
#
#     pdf.set_font('MyArial', '', 10)
#     prod_headers = [("Товар", 60), ("Факт", 25), ("Выручка", 40), ("Закуп", 40), ("Бензин", 35), ("Маржа", 40)]
#     for h, w in prod_headers: pdf.cell(w, 8, h, 1, align='C')
#     pdf.ln()
#
#     for _, row in prod_summary.iterrows():
#         pdf.cell(60, 8, fmt(row.get('Товар'), False, 30), 1)
#         pdf.cell(25, 8, fmt(row.get('Факт'), False), 1, align='C')
#         pdf.cell(40, 8, fmt(row.get('Выручка')), 1, align='R')
#         pdf.cell(40, 8, fmt(row.get('Закуп_сумма')), 1, align='R')
#         pdf.cell(35, 8, fmt(row.get('Бензин (доля)')), 1, align='R')
#         pdf.cell(40, 8, fmt(row.get('Прибыль_Маржа')), 1, align='R')
#         pdf.ln()
#
#     pdf_output = pdf.output()
#     document = BufferedInputFile(pdf_output, filename=f"{filename_prefix}.pdf")
#
#     await callback.message.answer_document(document, caption="✅ Детальный PDF-отчет сформирован (3 листа).")