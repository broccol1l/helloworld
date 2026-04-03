from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from aiogram.types import Message
from database.requests import get_user_shifts, delete_shift_full, get_shift_by_id, get_shift_deliveries, unclose_shift, delete_kg_from_active_shift

# Импортируем твои модели, стейты и клавиатуры
from database.models import User, Product, Kindergarten, Shift, Delivery
from utils.states import AdminState, AdminEdit, KGState
from keyboards.inline import (admin_main_kb, get_products_list_kb, get_product_card_kb,
                              get_cancel_kb, get_units_kb, get_kg_list_kb,
                              get_kg_card_kb, get_user_card_kb, get_users_list_kb,
                              get_admin_user_history_kb, get_admin_report_tools_kb,
                              get_admin_edit_menu_kb, get_admin_manage_kgs_kb)
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


@router.callback_query(F.data == "admin_stats")
async def admin_stats_view(callback: types.CallbackQuery, session: AsyncSession):
    # Просто считаем количество всего в базе
    from sqlalchemy import func

    users_count = await session.scalar(select(func.count(User.id)))
    products_count = await session.scalar(select(func.count(Product.id)))
    kg_count = await session.scalar(select(func.count(Kindergarten.id)))

    text = (
        "📊 **Общая статистика бота**\n\n"
        f"👥 Пользователей в базе: {users_count}\n"
        f"📦 Видов товаров: {products_count}\n"
        f"🏫 Садиков (объектов): {kg_count}\n\n"
        "📈 Подробные отчеты будут доступны после первых отгрузок!"
    )

    await callback.message.edit_text(text, reply_markup=admin_main_kb(), parse_mode="Markdown")
    await callback.answer()


# Пример того, как теперь выглядит хендлер истории в admin.py
@router.callback_query(F.data.startswith("adm_history:"))
@router.callback_query(F.data.startswith("adm_rep_page:"))
async def admin_show_user_history(callback: types.CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    user_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0

    limit = 5
    offset = page * limit
    shifts = await get_user_shifts(session, user_id, limit, offset)

    if not shifts and page == 0:
        await callback.answer("У этого водителя нет отчетов.", show_alert=True)
        return

    # ВЫЗЫВАЕМ ЧИСТУЮ ФУНКЦИЮ ИЗ inline.py
    await callback.message.edit_text(
        f"📂 **История отчетов (стр. {page + 1})**",
        reply_markup=get_admin_user_history_kb(shifts, user_id, page),
        parse_mode="Markdown"
    )


# 1. Просмотр деталей конкретного отчета из истории
@router.callback_query(F.data.startswith("adm_view_rep:"))
async def admin_view_single_report(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    # 1. Загружаем смену СРАЗУ с водителем (используем select вместо session.get)
    result_shift = await session.execute(
        select(Shift)
        .where(Shift.id == shift_id)
        .options(selectinload(Shift.driver))  # Магия здесь: подгружаем водителя
    )
    shift = result_shift.scalar_one_or_none()

    # 2. Загружаем отгрузки СРАЗУ с товарами и садиками
    result_deliveries = await session.execute(
        select(Delivery)
        .where(Delivery.shift_id == shift_id)
        .options(
            selectinload(Delivery.product),  # Подгружаем товар
            selectinload(Delivery.kindergarten)  # Подгружаем садик
        )
    )
    deliveries = result_deliveries.scalars().all()

    if not shift:
        await callback.answer("⚠️ Смена не найдена.", show_alert=True)
        return

    # Теперь shift.driver.full_name сработает, потому что данные уже в памяти!
    report_text = f"📋 **Детальный отчет за {shift.opened_at.strftime('%d.%m.%Y')}**\n"
    report_text += f"👤 Водитель: {shift.driver.full_name if shift.driver else 'Удален'}\n"
    report_text += "───────────────────\n"

    total_sum = 0
    if not deliveries:
        report_text += "_Отгрузок не зафиксировано_\n"
    else:
        for d in deliveries:
            report_text += f"🏫 {d.kindergarten.name}\n"
            report_text += f"  ◦ {d.product.name}: {d.weight_fact} {d.product.unit} = {d.total_price_sadik:,} сум\n"
            total_sum += d.total_price_sadik

    fuel = shift.fuel_expense or 0
    final_amount = total_sum - fuel

    report_text += "───────────────────\n"
    report_text += f"⛽ Бензин: **{fuel:,} сум**\n"
    report_text += f"💰 ОБЩАЯ ВЫРУЧКА: **{total_sum:,} сум**\n"
    report_text += f"💵 **ИТОГО К ВЫДАЧЕ: {final_amount:,} сум**"

    await callback.message.edit_text(
        report_text,
        reply_markup=get_admin_report_tools_kb(shift.id, shift.user_id),
        parse_mode="Markdown"
    )
    await callback.answer()


# 2. Удаление отчета (если админ нажал "Удалить")
@router.callback_query(F.data.startswith("adm_del_rep:"))
async def admin_delete_report(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    # Сначала узнаем ID юзера, чтобы вернуться в его историю после удаления
    shift = await session.get(Shift, shift_id)
    user_id = shift.user_id if shift else None

    # Удаляем (используем твой готовый метод из requests)
    await delete_shift_full(session, shift_id)
    await callback.answer("🚨 Отчет полностью удален!", show_alert=True)

    # Возвращаемся к списку отчетов этого водителя
    if user_id:
        # Имитируем нажатие на "История", чтобы обновить список
        callback.data = f"adm_history:{user_id}"
        await admin_show_user_history(callback, session)


# Вставь это в handlers/admin.py

# 1. Вход в режим редактирования (исправляем твой прошлый хендлер)
@router.callback_query(F.data.startswith("adm_edit_rep:"))
async def admin_edit_report_start(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    # Открываем смену в базе
    await unclose_shift(session, shift_id)

    await callback.message.edit_text(
        "🛠 **РЕЖИМ РЕДАКТИРОВАНИЯ (АДМИН)**\nВыберите действие:",
        reply_markup=get_admin_edit_menu_kb(shift_id),
        parse_mode="Markdown"
    )


# 2. Просмотр садиков для удаления
@router.callback_query(F.data.startswith("adm_manage_shift:"))
async def admin_manage_shift_kgs(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    # Получаем отгрузки этой смены
    deliveries = await get_shift_deliveries(session, shift_id)

    if not deliveries:
        await callback.answer("В этой смене пусто.", show_alert=True)
        return

    # Собираем уникальные садики
    kgs = {d.kindergarten.id: d.kindergarten.name for d in deliveries}

    await callback.message.edit_text(
        "Вы можете полностью удалить садик из этого отчета:",
        reply_markup=get_admin_manage_kgs_kb(kgs, shift_id)
    )


# 3. Само удаление садика админом
@router.callback_query(F.data.startswith("adm_del_kg:"))
async def admin_delete_kg_from_shift(callback: types.CallbackQuery, session: AsyncSession):
    # Исправленная строка (теперь 3 части: префикс, id смены, id садика)
    data_parts = callback.data.split(":")
    shift_id = int(data_parts[1])
    kg_id = int(data_parts[2])

    # Вызываем твой метод удаления
    await delete_kg_from_active_shift(session, shift_id, kg_id)
    await callback.answer("✅ Садик удален из отчета", show_alert=True)

    # Обновляем меню выбора садиков
    await admin_manage_shift_kgs(callback, session)


# 4. Завершение правок
@router.callback_query(F.data.startswith("adm_finish_edit:"))
async def admin_finish_edit(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    # Закрываем смену обратно (если нужно)
    # Можно просто вызвать просмотр отчета
    callback.data = f"adm_view_rep:{shift_id}"
    await admin_view_single_report(callback, session)