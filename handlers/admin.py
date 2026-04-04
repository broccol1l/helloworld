from datetime import datetime, timedelta

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
                               get_drivers_performance, get_all_deliveries_for_export)

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

@router.message(F.text == "⚙️ Админ-панель")
@router.message(Command("admin"))
async def admin_mode_entry(message: types.Message, session: AsyncSession):
    # Проверка на админа (на всякий случай)
    result = await session.execute(select(User).where(User.id == message.from_user.id))
    user = result.scalar_one_or_none()

    if user and user.is_admin:
        await message.answer(
            "🛡 **Панель управления (Admin Mode)**\nВыберите нужный раздел:",
            reply_markup=admin_main_kb(),  # Главное Inline-меню
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ У вас нет прав доступа к этому разделу.")


# --- ВЫХОД ИЗ АДМИНКИ ---

@router.callback_query(F.data == "admin_exit")
async def exit_admin_mode(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()  # Сброс всех ожиданий ввода

    # Редактируем старое сообщение, чтобы кнопки не висели
    await callback.message.edit_text("✅ Вы вышли из режима админа. Теперь вам доступно меню водителя.")

    # Отправляем новое сообщение с кнопками водителя
    await callback.message.answer(
        "🚚 Вы вернулись в рабочее меню:",
        reply_markup=main_menu_kb(is_admin=True)  # Показываем кнопку админки внизу
    )
    await callback.answer()


# --- КНОПКА "В НАЧАЛО" (Универсальная) ---

@router.callback_query(F.data == "admin_home")
async def back_to_admin_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🛡 **Панель управления (Admin Mode)**\nВыберите нужный раздел:",
        reply_markup=admin_main_kb(),
        parse_mode="Markdown"
    )
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
        await callback.message.edit_text("❌ Товар не найден в базе.")
        return

    # 4. Формируем текст
    text = (
        f"📦 **Карточка товара:**\n\n"
        f"📝 **Название:** {product.name}\n"
        f"📏 **Ед. измерения:** {product.unit}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"💰 **Цена садика:** {int(product.price_sadik)} сум\n"
        f"📉 **Цена закупа:** {int(product.price_zakup)} сум\n"
        f"📈 **Маржа:** {int(product.price_sadik - product.price_zakup)} сум\n"
    )

    # 5. Редактируем сообщение
    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_product_card_kb(product_id),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Ошибка при выводе карточки: {e}")


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
    await callback.answer("Действие отменено")




# --- ДОБАВЛЕНИЕ ТОВАРА ---

@router.callback_query(F.data == "adm_prod_add")
async def admin_product_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.waiting_product_name)
    await callback.message.edit_text(
        "📝 **Шаг 1: Название**\nВведите название товара (например: *Сметана 20%*):",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()


# 1. Получаем название -> спрашиваем Единицу Измерения
@router.message(AdminState.waiting_product_name)
async def admin_product_add_name(message: types.Message, state: FSMContext):
    await state.update_data(new_name=message.text)
    await state.set_state(AdminState.waiting_product_unit)  # Переходим к единицам

    await message.answer(
        f"✅ Название: {message.text}\n\n**Шаг 2:** Выберите единицу измерения:",
        reply_markup=get_units_kb(),
        parse_mode="Markdown"
    )


# 2. Получаем Единицу (через callback) -> спрашиваем Цену Садика
@router.callback_query(F.data.startswith("unit_set:"))
async def admin_product_add_unit(callback: types.CallbackQuery, state: FSMContext):
    unit = callback.data.split(":")[1]
    await state.update_data(new_unit=unit)

    await state.set_state(AdminState.waiting_p_sadik_add)
    await callback.message.edit_text(
        f"✅ Единица измерения: {unit}\n\n**Шаг 3:** Введите **ЦЕНУ САДИКА** (число):",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()

# 3. Получаем Цену Садика -> спрашиваем Цену Закупа
@router.message(AdminState.waiting_p_sadik_add)
async def admin_product_add_p_sadik(message: types.Message, state: FSMContext):
    # Очищаем текст от пробелов и меняем запятую на точку
    clean_text = message.text.replace(" ", "").replace(",", ".")

    # Проверяем, число ли это (разрешаем одну точку)
    if not clean_text.replace(".", "", 1).isdigit():
        await message.answer("❌ Введите корректное число (например: 100 000 или 105.5):", reply_markup=get_cancel_kb())
        return

    await state.update_data(new_p_sadik=float(clean_text))  # Используем clean_text!
    await state.set_state(AdminState.waiting_p_zakup_add)
    await message.answer("💰 **Шаг 4:** Введите **ЦЕНУ ЗАКУПА** (число):", reply_markup=get_cancel_kb())



# 4. Финал: сохранение в базу
@router.message(AdminState.waiting_p_zakup_add)
async def admin_product_add_finish(message: types.Message, state: FSMContext, session: AsyncSession):
    clean_text = message.text.replace(" ", "").replace(",", ".")

    if not clean_text.replace(".", "", 1).isdigit():
        await message.answer("❌ Введите число!", reply_markup=get_cancel_kb())
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
        f"🎉 **Товар успешно добавлен!**\n\n"
        f"📦 {new_product.name}\n"
        f"📏 Ед. изм.: {new_product.unit}\n"
        f"💰 Цена садика: {int(new_product.price_sadik)} сум\n"
        f"📉 Цена закупа: {int(new_product.price_zakup)} сум",
        reply_markup=admin_main_kb(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("adm_prod_delete:"))
async def delete_product(callback: types.CallbackQuery, session: AsyncSession):
    product_id = int(callback.data.split(":")[1])
    product = await session.get(Product, product_id)

    if product:
        product.is_active = False  # Soft delete
        await session.commit()
        await callback.answer(f"🗑 Товар '{product.name}' удален")
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
            "📦 Список товаров пуст.",
            reply_markup=get_products_list_kb([], page)
        )
    else:
        await callback.message.edit_text(
            f"📦 **Список товаров (Страница {page + 1})**\nНажмите на товар для редактирования:",
            reply_markup=get_products_list_kb(products, page),
            parse_mode="Markdown"
        )
    await callback.answer()


# --- РЕДАКТИРОВАНИЕ ЦЕНЫ (НАЧАЛО) ---

@router.callback_query(F.data.startswith("adm_prod_edit:"))
async def admin_product_edit_start(callback: types.CallbackQuery, state: FSMContext):
    _, field, product_id = callback.data.split(":")
    product_id = int(product_id)

    await state.update_data(edit_product_id=product_id, edit_field=field)

    if field == "p_sadik":
        await callback.message.answer("💰 Введите новую **ЦЕНУ САДИКА**:", reply_markup=get_cancel_kb())
        await state.set_state(AdminEdit.waiting_p_sadik_edit)
    elif field == "p_zakup":
        await callback.message.answer("📉 Введите новую **ЦЕНУ ЗАКУПА**:", reply_markup=get_cancel_kb())
        await state.set_state(AdminEdit.waiting_p_zakup_edit)
    # --- ВОТ ЭТОГО КУСКА НЕ ХВАТАЛО ---
    elif field == "name":
        await callback.message.answer("✏️ Введите новое **НАЗВАНИЕ** товара:", reply_markup=get_cancel_kb())
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
        await message.answer("❌ Ошибка! Введите корректное число (например: 105000):", reply_markup=get_cancel_kb())
        return

    new_price = float(clean_text)

    # 2. Достаем данные из памяти
    data = await state.get_data()
    product_id = data.get("edit_product_id")
    field = data.get("edit_field")

    # 3. Ищем продукт в базе
    product = await session.get(Product, product_id)
    if not product:
        await message.answer("❌ Ошибка: товар не найден.")
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
        f"✅ Цена товара **{product.name}** успешно обновлена!\n\n"
        f"💰 Цена садика: {int(product.price_sadik)} сум\n"
        f"📉 Цена закупа: {int(product.price_zakup)} сум\n"
        f"📈 Маржа: {int(product.price_sadik - product.price_zakup)} сум"
    )

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
            f"✅ Название изменено!\nБыло: {old_name}\nСтало: **{product.name}**",
            reply_markup=get_product_card_kb(product.id),
            parse_mode="Markdown"
        )


# --- РАЗДЕЛ: САДИКИ ---

@router.callback_query(F.data == "admin_kindergartens")
@router.callback_query(F.data.startswith("adm_kg_page:"))
async def admin_kg_list(callback: types.CallbackQuery, session: AsyncSession):
    page = int(callback.data.split(":")[1]) if ":" in callback.data else 0

    result = await session.execute(
        select(Kindergarten).where(Kindergarten.is_active == True).order_by(Kindergarten.name))
    kg_list = list(result.scalars().all())

    await callback.message.edit_text(
        f"🏫 **Список садиков (Страница {page + 1})**:",
        reply_markup=get_kg_list_kb(kg_list, page),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_kg_view:"))
async def admin_kg_view(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    kg = await session.get(Kindergarten, kg_id)

    if not kg:
        await callback.answer("❌ Садик не найден")
        return

    await callback.message.edit_text(
        f"🏫 **Объект:** {kg.name}\n\nЗдесь можно изменить название или удалить объект из активного списка.",
        reply_markup=get_kg_card_kb(kg_id),
        parse_mode="Markdown"
    )
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
        f"🏫 **Список садиков (Страница {page + 1})**:",
        reply_markup=get_kg_list_kb(kg_list, page),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_kg_view:"))
async def admin_kg_view(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    kg = await session.get(Kindergarten, kg_id)

    if not kg:
        await callback.answer("❌ Садик не найден")
        return

    await callback.message.edit_text(
        f"🏫 **Объект:** {kg.name}\n\nЗдесь можно изменить название или удалить объект из активного списка.",
        reply_markup=get_kg_card_kb(kg_id),
        parse_mode="Markdown"
    )
    await callback.answer()


# --- ДОБАВЛЕНИЕ САДИКА ---

@router.callback_query(F.data == "adm_kg_add")
async def admin_kg_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(KGState.waiting_kg_name)  # Используем твой стейт
    await callback.message.edit_text(
        "📝 Введите название нового садика (например: *Садик №52*):",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(KGState.waiting_kg_name)
async def admin_kg_add_finish(message: types.Message, state: FSMContext, session: AsyncSession):
    new_kg = Kindergarten(name=message.text, is_active=True)
    session.add(new_kg)

    try:
        await session.commit()
        await state.clear()
        await message.answer(f"✅ Садик **{new_kg.name}** успешно добавлен!", reply_markup=admin_main_kb())
    except Exception:
        await session.rollback()
        await message.answer("❌ Ошибка: садик с таким названием уже существует.")


@router.callback_query(F.data.startswith("adm_kg_delete:"))
async def admin_kg_delete(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    kg = await session.get(Kindergarten, kg_id)

    if kg:
        kg.is_active = False  # Просто скрываем
        await session.commit()
        await callback.answer(f"🗑 {kg.name} удален")
        await admin_kg_list(callback, session)  # Возвращаемся к списку


@router.callback_query(F.data.startswith("adm_kg_edit:"))
async def admin_kg_edit_start(callback: types.CallbackQuery, state: FSMContext):
    kg_id = int(callback.data.split(":")[1])

    # Сохраняем ID садика в память, чтобы знать, чье имя менять
    await state.update_data(edit_kg_id=kg_id)
    await state.set_state(KGState.waiting_kg_edit_name)

    await callback.message.answer(
        "✏️ Введите **новое название** для этого садика:",
        reply_markup=get_cancel_kb()  # Используем нашу кнопку отмены
    )
    await callback.answer()


@router.message(KGState.waiting_kg_edit_name)
async def admin_kg_edit_save(message: types.Message, state: FSMContext, session: AsyncSession):
    # Достаем ID из памяти
    data = await state.get_data()
    kg_id = data.get("edit_kg_id")

    # Ищем садик в базе
    kg = await session.get(Kindergarten, kg_id)

    if not kg:
        await message.answer("❌ Ошибка: садик не найден.")
        await state.clear()
        return

    old_name = kg.name
    kg.name = message.text  # Обновляем имя

    await session.commit()  # Фиксируем в БД
    await state.clear()  # Очищаем состояние

    await message.answer(
        f"✅ Название успешно изменено!\n\n"
        f"Было: *{old_name}*\n"
        f"Стало: **{kg.name}**",
        reply_markup=get_kg_card_kb(kg.id),  # Возвращаем кнопки управления этим садиком
        parse_mode="Markdown"
    )


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
        f"👥 **Управление пользователями (Стр. {page + 1})**\n\n"
        f"🛡️ — Админ\n🚚 — Водитель\n🚫 — Заблокирован",
        reply_markup=get_users_list_kb(users, page),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_user_view:"))
async def admin_user_view(callback: types.CallbackQuery, session: AsyncSession):
    # ПРОВЕРЬ ЭТУ СТРОКУ! Должно быть [-1]
    user_id = int(callback.data.split(":")[-1])

    user = await session.get(User, user_id)

    if not user:
        await callback.message.edit_text("❌ Пользователь не найден в базе.")
        return

    role = "Администратор 🛡️" if user.is_admin else "Водитель 🚚"
    status = "Заблокирован 🚫" if user.is_blocked else "Работает ✅"

    text = (
        f"👤 **Карточка пользователя**\n\n"
        f"🆔 ID: `{user.id}`\n"
        f"📝 Имя: {user.full_name or 'Не указано'}\n"
        f"📞 Тел: {user.phone or 'Не привязан'}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"🎭 Роль: {role}\n"
        f"📊 Статус: {status}"
    )

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
        await callback.answer("❌ Нельзя менять права самому себе!", show_alert=True)
        return

    user = await session.get(User, user_id)
    if not user:
        await callback.answer("Пользователь не найден")
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

    await callback.answer(f"✅ Статус обновлен")

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
            "У этого водителя больше нет отчетов.",
            # Возвращаем кнопку в карточку юзера
            reply_markup=get_user_card_kb(user_id, False, False)
        )
        return

    await callback.message.edit_text(
        f"📂 **История отчетов (стр. {page + 1})**",
        reply_markup=get_admin_user_history_kb(shifts, user_id, page),
        parse_mode="Markdown"
    )


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
        await callback.answer("⚠️ Смена не найдена.", show_alert=True)
        return

    report_text = f"📋 **Детальный отчет за {shift.opened_at.strftime('%d.%m.%Y')}**\n"
    report_text += f"👤 Водитель: {shift.driver.full_name if shift.driver else 'Удален'}\n"
    report_text += "───────────────────\n"

    total_sum = 0
    total_cost = 0 # Считаем себестоимость (закуп)

    if not deliveries:
        report_text += "_Отгрузок не зафиксировано_\n"
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
    report_text += f"⛽ Бензин: **{fuel:,} сум**\n"
    report_text += f"💰 ОБЩАЯ ВЫРУЧКА: **{total_sum:,} сум**\n"
    report_text += f"💵 **КАССА (СДАЕТ ВОДИТЕЛЬ): {final_amount:,} сум**\n"
    report_text += f"📈 **ЧИСТАЯ ПРИБЫЛЬ: {net_profit:,} сум**"

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
        await callback.answer("Отчет уже удален.")
        return

    user_id = shift.user_id

    # Удаляем
    await delete_shift_full(session, shift_id)
    await callback.answer("🚨 Отчет полностью удален!", show_alert=True)

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
        "🛠 **РЕЖИМ РЕДАКТИРОВАНИЯ (АДМИН)**\nЧто вы хотите сделать?",
        reply_markup=get_admin_edit_loop_kb(shift_id), # Исправил название функции
        parse_mode="Markdown"
    )


# 2. Добавление нового садика в чужой отчет
@router.callback_query(F.data.startswith("adm_add_kg_start:"))
async def admin_add_kg_start(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])
    await state.update_data(shift_id=shift_id)

    from database.requests import get_active_kindergartens
    kgs = await get_active_kindergartens(session)

    await state.set_state(DeliveryState.object_name) # Магия: админ теперь в стейте водителя

    await callback.message.edit_text(
        "🏫 **Добавление садика в отчет**\nВыберите объект:",
        reply_markup=get_kg_paging_kb(kgs, page=0),
        parse_mode="Markdown"
    )
    await callback.answer()

# 3. Список садиков для удаления
@router.callback_query(F.data.startswith("adm_manage_shift:"))
async def admin_manage_shift_kgs(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])
    deliveries = await get_shift_deliveries(session, shift_id)

    if not deliveries:
        await callback.answer("В этой смене пусто.", show_alert=True)
        return

    kgs = {d.kindergarten.id: d.kindergarten.name for d in deliveries}

    await callback.message.edit_text(
        "🔍 **Управление садиками:**\nВыберите садик для ПОЛНОГО удаления из отчета:",
        reply_markup=get_admin_manage_kgs_kb(kgs, shift_id)
    )


# 4. Удаление (Фикс распаковки)
@router.callback_query(F.data.startswith("adm_del_kg:"))
async def admin_delete_kg_from_shift(callback: types.CallbackQuery, session: AsyncSession):
    data_parts = callback.data.split(":")
    shift_id = int(data_parts[1])
    kg_id = int(data_parts[2])

    await delete_kg_from_active_shift(session, shift_id, kg_id)
    await callback.answer("✅ Садик удален", show_alert=True)

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

    await callback.answer("✅ Правки сохранены")

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
        "Выберите следующий товар для этого садика:",
        reply_markup=get_products_paging_kb(products, page=0)
    )


# 2. Если админ закончил с этим садиком и хочет вернуться в ГЛАВНОЕ МЕНЮ правки
@router.callback_query(F.data.startswith("adm_finish_this_kg:"))
async def admin_finish_kg_and_return(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    # Можно тут вывести мини-итог по садику, как у водителя
    # Но главное — вернуть его в главное меню админ-правки
    await callback.message.edit_text(
        "✅ Садик записан. Что делаем дальше?",
        reply_markup=get_admin_edit_loop_kb(shift_id)
    )


# 1. Перехват кнопки "Завершить этот садик"
@router.callback_query(F.data == "finish_this_kg")
async def intercept_finish_kg(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(session, callback.from_user.id)

    if not user.is_admin:
        raise SkipHandler()  # 🪄 ВОТ МАГИЯ! Передаем сигнал дальше в delivery.py

    # Если нажал админ — возвращаем его в админку
    data = await state.get_data()
    shift_id = data.get("shift_id")
    await callback.message.edit_text("Садик завершен. Возвращаюсь в меню правки...",
                                     reply_markup=get_admin_edit_loop_kb(shift_id))


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

    await callback.answer("✅ Правки сохранены")
    await admin_view_single_report(callback, session, shift_id_override=shift_id)


@router.callback_query(F.data.startswith("adm_change_date:"))
async def admin_change_date_request(callback: types.CallbackQuery):
    shift_id = int(callback.data.split(":")[1])

    builder = InlineKeyboardBuilder()
    today = datetime.now().strftime("%d.%m")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m")

    builder.button(text=f"📅 Сегодня ({today})", callback_data=f"adm_apply_date:today:{shift_id}")
    builder.button(text=f"📅 Вчера ({yesterday})", callback_data=f"adm_apply_date:yesterday:{shift_id}")
    builder.button(text="⬅️ Назад", callback_data=f"adm_edit_rep:{shift_id}")  # Возврат в меню правки
    builder.adjust(1)

    await callback.message.edit_text(
        "Выберите новую дату для этой смены:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("adm_apply_date:"))
async def admin_apply_date_fix(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    parts = callback.data.split(":")
    date_type = parts[1]
    shift_id = int(parts[2])

    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    new_date = now if date_type == "today" else now - timedelta(days=1)

    # Обновляем дату
    await update_shift_date(session, shift_id, new_date)
    await callback.answer(f"📅 Дата изменена на {new_date.strftime('%d.%m')}", show_alert=True)

    # ВАЖНО: возвращаем админа в меню ПРАВОК, а не просто в просмотр
    # Чтобы он видел кнопку "Завершить правки"
    await callback.message.edit_text(
        f"✅ Дата изменена на **{new_date.strftime('%d.%m.%Y')}**.\n\nЧто делаем дальше?",
        reply_markup=get_admin_edit_loop_kb(shift_id),
        parse_mode="Markdown"
    )

# 1. Админ нажал кнопку "Изменить бензин"
@router.callback_query(F.data.startswith("adm_change_fuel:"))
async def admin_change_fuel_start(callback: types.CallbackQuery, state: FSMContext):
    shift_id = int(callback.data.split(":")[1])

    # Сохраняем ID смены и переводим в режим ожидания ввода
    await state.update_data(shift_id=shift_id)
    await state.set_state(AdminEdit.waiting_shift_fuel)

    # Кнопка отмены, если админ передумал
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data=f"adm_edit_rep:{shift_id}")

    await callback.message.edit_text(
        "⛽ **Изменение расхода на бензин**\n\nВведите новую сумму цифрами (например: `50000`):",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await callback.answer()


# 2. Админ ввел новую сумму бензина
@router.message(AdminEdit.waiting_shift_fuel)
async def admin_change_fuel_process(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        # Пробуем перевести текст в число
        new_fuel = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("⚠️ Ошибка! Введите сумму только цифрами.")
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
        f"✅ Расход на бензин обновлен на **{new_fuel:,} сум**.\n\nЧто делаем дальше?",
        reply_markup=get_admin_edit_loop_kb(shift_id),
        parse_mode="Markdown"
    )


# АНАЛИТИКА
@router.callback_query(F.data == "admin_stats")
async def admin_stats_main(callback: types.CallbackQuery, session: AsyncSession):


    # 1. Считаем количество записей в базе (твой старый код)
    users_count = await session.scalar(select(func.count(User.id)))
    products_count = await session.scalar(select(func.count(Product.id)))
    kg_count = await session.scalar(select(func.count(Kindergarten.id)))

    # 2. Формируем текст: Сначала общая стата, потом призыв выбрать период
    text = (
        "📊 **ОБЩАЯ СТАТИСТИКА БАЗЫ**\n\n"
        f"👥 Пользователей: **{users_count}**\n"
        f"📦 Видов товаров: **{products_count}**\n"
        f"🏫 Садиков: **{kg_count}**\n"
        "───────────────────\n"
        "📈 **ФИНАНСОВАЯ АНАЛИТИКА**\n"
        "Выберите период для расчета выручки и чистой прибыли:"
    )

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
            "🗓 **Анализ за произвольный период**\n\n"
            "Введите две даты через дефис в формате `ДД.ММ.ГГГГ - ДД.ММ.ГГГГ`.\n\n"
            "Пример: `01.04.2026 - 15.04.2026`",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        return

    now = datetime.now()

    # 2. Определяем границы времени
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        period_name = "СЕГОДНЯ"

    elif period == "yesterday":
        start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        period_name = "ВЧЕРА"

    elif period == "month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        months = ["ЯНВАРЬ", "ФЕВРАЛЬ", "МАРТ", "АПРЕЛЬ", "МАЙ", "ИЮНЬ", "ИЮЛЬ", "АВГУСТ", "СЕНТЯБРЬ", "ОКТЯБРЬ",
                  "НОЯБРЬ", "ДЕКАБРЬ"]
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
        f"📊 **ИТОГИ ЗА {period_name}**:\n\n"
        f"💰 Оборот (Выручка): **{int(stats['revenue']):,} сум**\n"
        f"📉 Затраты на товар: **{int(stats['cost']):,} сум**\n"
        f"⛽️ Затраты на бензин: **{int(stats['fuel']):,} сум**\n"
        f"───────────────────\n"
        f"🏆 **ЧИСТАЯ ПРИБЫЛЬ: {int(stats['profit']):,} сум**\n\n"
        f"📈 Рентабельность бизнеса: **{profitability:.1f}%**"
    )

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
        await callback.answer("За этот период данных по водителям нет.", show_alert=True)
        return

    await callback.message.edit_text(
        f"👥 **Эффективность водителей**\n"
        f"Период: {period.upper()}\n"
        f"(Чистая прибыль после вычета закупа и бензина)",
        reply_markup=get_drivers_stats_kb(drivers_data, period, page),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "adm_stats_export_all:xlsx")
async def admin_export_global_excel(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer("⏳ Формирую детальный отчет с итогами...", show_alert=False)

    raw_data = await get_all_deliveries_for_export(session)

    if not raw_data:
        await callback.answer("❌ Нет данных для экспорта", show_alert=True)
        return

    df = pd.DataFrame(raw_data)
    df['Дата'] = pd.to_datetime(df['Дата']).dt.strftime('%d.%m.%Y %H:%M')

    # --- УМНЫЙ РАСЧЕТ БЕНЗИНА ---
    # 1. Если бензин не указан (None), ставим 0
    df['Бензин_Смены'] = df['Бензин_Смены'].fillna(0).astype(float)

    # 2. Считаем, сколько всего отгрузок было в каждой смене
    shift_counts = df.groupby('shift_id')['shift_id'].transform('count')

    # 3. Размазываем бензин поровну на все отгрузки этой смены
    df['Бензин (доля)'] = df['Бензин_Смены'] / shift_counts

    # 4. Считаем ЧИСТУЮ маржу: Выручка - Закуп - Бензин
    df['Прибыль_Маржа'] = df['Выручка'] - df['Закуп_сумма'] - df['Бензин (доля)']

    # Удаляем технические колонки (они не нужны бухгалтеру)
    df = df.drop(columns=['shift_id', 'Бензин_Смены'])

    # --- СВОДНЫЕ ТАБЛИЦЫ ---
    kg_summary = df.groupby("Садик").agg({
        "Выручка": "sum",
        "Закуп_сумма": "sum",
        "Бензин (доля)": "sum",  # Добавили бензин
        "Прибыль_Маржа": "sum",
        "Факт": "count"
    }).rename(columns={"Факт": "Кол_во_отгрузок"}).reset_index()

    prod_summary = df.groupby("Товар").agg({
        "Факт": "sum",
        "Выручка": "sum",
        "Закуп_сумма": "sum",
        "Бензин (доля)": "sum",  # Добавили бензин
        "Прибыль_Маржа": "sum"
    }).reset_index()

    # --- ДОБАВЛЯЕМ СТРОКИ "ИТОГО:" ---
    totals_log = pd.DataFrame([{
        'Дата': 'ИТОГО:',
        'План': df['План'].sum(),
        'Факт': df['Факт'].sum(),
        'Выручка': df['Выручка'].sum(),
        'Закуп_сумма': df['Закуп_сумма'].sum(),
        'Бензин (доля)': df['Бензин (доля)'].sum(),  # Итог по бензину
        'Прибыль_Маржа': df['Прибыль_Маржа'].sum()
    }])
    df = pd.concat([df, totals_log], ignore_index=True)

    totals_kg = pd.DataFrame([{
        'Садик': 'ИТОГО:',
        'Кол_во_отгрузок': kg_summary['Кол_во_отгрузок'].sum(),
        'Выручка': kg_summary['Выручка'].sum(),
        'Закуп_сумма': kg_summary['Закуп_сумма'].sum(),
        'Бензин (доля)': kg_summary['Бензин (доля)'].sum(),
        'Прибыль_Маржа': kg_summary['Прибыль_Маржа'].sum()
    }])
    kg_summary = pd.concat([kg_summary, totals_kg], ignore_index=True)

    totals_prod = pd.DataFrame([{
        'Товар': 'ИТОГО:',
        'Факт': prod_summary['Факт'].sum(),
        'Выручка': prod_summary['Выручка'].sum(),
        'Закуп_сумма': prod_summary['Закуп_сумма'].sum(),
        'Бензин (доля)': prod_summary['Бензин (доля)'].sum(),
        'Прибыль_Маржа': prod_summary['Прибыль_Маржа'].sum()
    }])
    prod_summary = pd.concat([prod_summary, totals_prod], ignore_index=True)

    # --- ЗАПИСЬ В EXCEL ---
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Общий лог", index=False)
        kg_summary.to_excel(writer, sheet_name="Итоги по Садикам", index=False)
        prod_summary.to_excel(writer, sheet_name="Итоги по Товарам", index=False)

        # Расширяем колонки
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for col in worksheet.columns:
                max_length = 0
                column_letter = col[0].column_letter
                for cell in col:
                    try:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    except:
                        pass
                worksheet.column_dimensions[column_letter].width = max_length + 2

    output.seek(0)
    file_content = output.getvalue()

    document = BufferedInputFile(
        file_content,
        filename=f"Global_Report_{datetime.now().strftime('%d_%m_%Y')}.xlsx"
    )

    await callback.message.answer_document(
        document,
        caption="✅ Глобальный отчет сформирован.\n\n"
                "В файле 3 листа (с учетом бензина и итогами):\n"
                "1. Общий лог операций\n"
                "2. Итоги по каждому садику\n"
                "3. Итоги по видам товаров"
    )


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
            raise ValueError("Дата начала больше даты конца")

    except ValueError:
        await message.answer(
            "❌ **Ошибка формата!**\nПожалуйста, введите даты строго как в примере:\n`01.04.2026 - 15.04.2026`",
            parse_mode="Markdown")
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
        f"📊 **ИТОГИ ЗА {period_name}**:\n\n"
        f"💰 Оборот (Выручка): **{int(stats['revenue']):,} сум**\n"
        f"📉 Затраты на товар: **{int(stats['cost']):,} сум**\n"
        f"⛽️ Затраты на бензин: **{int(stats['fuel']):,} сум**\n"
        f"───────────────────\n"
        f"🏆 **ЧИСТАЯ ПРИБЫЛЬ: {int(stats['profit']):,} сум**\n\n"
        f"📈 Рентабельность бизнеса: **{profitability:.1f}%**"
    )

    # Отправляем сообщение как обычный ответ на текст (через message.answer)
    from keyboards.inline import get_dashboard_kb
    await message.answer(report_text, reply_markup=get_dashboard_kb(period_code), parse_mode="Markdown")