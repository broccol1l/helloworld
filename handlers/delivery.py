from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, func
from sqlalchemy.orm import selectinload
from database.models import User
from datetime import datetime, timedelta
from keyboards import inline  # Твои новые инлайны


from database import requests
from database.models import Product, Kindergarten, Delivery, Shift
from utils.states import DeliveryState
from keyboards.reply import main_menu_kb
from keyboards.inline import (
    get_kg_paging_kb, KGOrderCallback,
    get_products_paging_kb, ProductCallback, get_loop_kb
)

router = Router()


async def show_kindergartens(message: types.Message, state: FSMContext, session: AsyncSession):
    # Вызываем функцию, которая у тебя точно есть в requests.py
    from database.requests import get_active_kindergartens
    kgs = await get_active_kindergartens(session)

    # Устанавливаем твой реальный стейт "Выбор садика"
    await state.set_state(DeliveryState.object_name)

    # Отправляем список садиков
    await message.answer(
        "Выберите садик для начала отгрузки:",
        reply_markup=get_kg_paging_kb(kgs, page=0)
    )


@router.message(F.text == "📦 Добавить отгрузку")
async def start_delivery_with_date(message: types.Message, state: FSMContext, session: AsyncSession):
    user = await requests.get_user(session, message.from_user.id)
    shift = await requests.get_active_shift(session, user.id)

    if shift:
        # ОБЯЗАТЕЛЬНО сохраняем id смены в стейт, если она уже открыта
        await state.update_data(shift_id=shift.id)
        await show_kindergartens(message, state, session)
    else:
        await message.answer(
            "За какой день вводим отгрузки?",
            reply_markup=inline.get_date_selection_kb()
        )

@router.callback_query(F.data.startswith("set_date:"))
async def set_shift_date(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    date_type = callback.data.split(":")[1]
    target_date = datetime.now() if date_type == "today" else datetime.now() - timedelta(days=1)
    user = await requests.get_user(session, callback.from_user.id)

    # Создаем смену и получаем её объект
    shift = await requests.create_shift_with_date(session, user.id, target_date)
    # Сохраняем id новой смены в стейт
    await state.update_data(shift_id=shift.id)

    await callback.message.edit_text(f"✅ Смена открыта на {target_date.strftime('%d.%m.%Y')}")
    await show_kindergartens(callback.message, state, session)

# 2. Обработка выбора садика
@router.callback_query(KGOrderCallback.filter(), DeliveryState.object_name)
async def delivery_object_chosen(callback: types.CallbackQuery, callback_data: KGOrderCallback,
                                 state: FSMContext, session: AsyncSession):
    if callback_data.action == "nav":
        kgs = await requests.get_active_kindergartens(session)
        await callback.message.edit_reply_markup(
            reply_markup=get_kg_paging_kb(kgs, page=callback_data.page)
        )
        await callback.answer()
        return

    kg = await session.get(Kindergarten, callback_data.kg_id)
    await state.update_data(kindergarten_id=kg.id, kg_name=kg.name)

    products = await requests.get_all_products(session)
    await state.set_state(DeliveryState.choosing_product)

    await callback.message.edit_text(
        f"🏢 Объект: <b>{kg.name}</b>\nТеперь выберите товар:",
        reply_markup=get_products_paging_kb(products),
        parse_mode="HTML"
    )
    await callback.answer()


# 3. Обработка выбора товара
@router.callback_query(ProductCallback.filter(), DeliveryState.choosing_product)
async def product_chosen(callback: types.CallbackQuery, callback_data: ProductCallback,
                         state: FSMContext, session: AsyncSession):
    if callback_data.action == "nav":
        products = await requests.get_all_products(session)
        await callback.message.edit_reply_markup(
            reply_markup=get_products_paging_kb(products, page=callback_data.page)
        )
        await callback.answer()
        return

    product = await session.get(Product, callback_data.prod_id)
    await state.update_data(product_id=product.id, prod_name=product.name, unit=product.unit)

    await state.set_state(DeliveryState.weight_plan)
    await callback.message.edit_text(
        f"📦 Товар: <b>{product.name}</b>\nВведите план (в {product.unit}):",
        parse_mode="HTML"
    )
    await callback.answer()


# 4. Ввод ПЛАНА
@router.message(DeliveryState.weight_plan)
async def delivery_plan_chosen(message: types.Message, state: FSMContext):
    data = await state.get_data()
    unit = data.get('unit')
    try:
        weight = float(message.text.replace(',', '.'))
        await state.update_data(weight_plan=weight)
        await state.set_state(DeliveryState.weight_fact)
        await message.answer(f"План {weight} {unit} принят.\nВведите <b>фактический вес/кол-во</b>:")
    except ValueError:
        await message.answer(f"Ошибка! Введите число ({unit}). Пример: 15.5")


# 5. Ввод ФАКТА и сохранение в базу (Snapshot)
# 5. Ввод ФАКТА и сохранение в базу (Snapshot)
@router.message(DeliveryState.weight_fact, F.text, ~F.text.contains("Завершить"))
async def delivery_fact_chosen(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    unit = data.get('unit', 'кг')
    try:
        weight_fact = float(message.text.replace(',', '.'))
        if weight_fact > data['weight_plan']:
            await message.answer(f"❌ Факт не может быть больше плана ({data['weight_plan']} {unit}). Введите заново:")
            return

        # Сохраняем отгрузку
        delivery = await requests.add_delivery(
            session, data['shift_id'], data['product_id'],
            data['kindergarten_id'], data['weight_plan'], weight_fact
        )

        # --- ВОТ ЭТО ДОБАВЬ ---
        # Очищаем стейт, чтобы нижнее меню (Мои отчеты и т.д.) снова работало
        # Но сохраняем shift_id и kindergarten_id в памяти на случай,
        # если юзер нажмет инлайновую кнопку "Добавить еще товар"
        await state.set_state(None)
        # ----------------------

        await message.answer(
            f"✅ Сохранено: {data['prod_name']}\n"
            f"Сумма: <b>{delivery.total_price_sadik:,} сум</b>\n\n"
            "Добавить ещё товар в этот садик?",
            reply_markup=get_loop_kb(),
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer(f"Ошибка! Введите число ({unit}).")


@router.callback_query(F.data == "add_more_prod")
async def add_more_product(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()

    # ПРОВЕРКА: Если садик потерялся (например, при редактировании)
    if 'kindergarten_id' not in data:
        await callback.answer("Сначала выберите садик")
        await show_kindergartens(callback.message, state, session)
        return

    # Если садик на месте, просто показываем товары как обычно
    await state.set_state(DeliveryState.choosing_product)
    from database.requests import get_all_products
    products = await get_all_products(session)
    await callback.message.edit_text(
        "Выберите товар:",
        reply_markup=get_products_paging_kb(products, page=0)
    )


@router.callback_query(F.data == "finish_this_kg")
async def finish_kg(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    # 1. Берем данные для финального отчета по садику
    data = await state.get_data()
    shift_id = data.get('shift_id')
    kg_id = data.get('kindergarten_id')
    kg_name = data.get('kg_name')

    # 2. Собираем все позиции, что водитель ввел за этот заезд
    query = select(Delivery).where(
        Delivery.shift_id == shift_id,
        Delivery.kindergarten_id == kg_id
    ).options(selectinload(Delivery.product))

    result = await session.execute(query)
    deliveries = result.scalars().all()

    if not deliveries:
        await callback.message.answer("В этот садик ничего не было отгружено.", reply_markup=main_menu_kb())
    else:
        report = f"🏁 <b>Итог по объекту: {kg_name}</b>\n\n"
        total_kg_sum = 0
        for d in deliveries:
            report += f"🔹 {d.product.name}: {d.weight_fact} {d.product.unit} — <b>{d.total_price_sadik:,} сум</b>\n"
            total_kg_sum += d.total_price_sadik

        report += f"\n💰 <b>Итого к оплате: {total_kg_sum:,} сум</b>"
        await callback.message.answer(report, reply_markup=main_menu_kb(), parse_mode="HTML")

    # 3. Полная очистка стейта только в самом конце
    await state.clear()
    await callback.answer()


from keyboards.reply import main_menu_kb  # убедись, что импорт есть

@router.message(F.text == "🏁 Завершить смену")
async def close_shift_button_handler(message: types.Message, state: FSMContext, session: AsyncSession):
    await close_shift_start(message, state, session)


# 1. Начало закрытия смены (обработка и кнопки, и инлайна)
@router.message(F.text == "🏁 Завершить смену")
async def close_shift_start(message: types.Message, state: FSMContext, session: AsyncSession,
                            manual_user_id: int = None):
    # Если manual_user_id передан (из инлайна), берем его. Иначе из сообщения.
    tg_id = manual_user_id if manual_user_id else message.from_user.id

    user = await requests.get_user(session, tg_id)
    # Ищем активную смену
    shift = await requests.get_active_shift(session, user.id)

    if not shift:
        await message.answer("У вас нет открытых смен.")
        return

    await state.update_data(shift_id=shift.id)
    await state.set_state(DeliveryState.waiting_fuel)

    # Создаем временную кнопку для быстрого ввода 0
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="0 (не заправлялся)")]],
        resize_keyboard=True
    )

    await message.answer(
        "Введите сумму расхода на бензин за сегодня (сум).\n"
        "Если расходов не было, введите 0 или нажмите кнопку ниже:",
        reply_markup=kb
    )


@router.message(DeliveryState.waiting_fuel)
async def close_shift_done(message: types.Message, state: FSMContext, session: AsyncSession):
    fuel_text = message.text.split(' ')[0]

    try:
        fuel_amount = float(fuel_text.replace(',', '.'))
        data = await state.get_data()
        shift_id = data.get('shift_id')

        deliveries = await requests.get_shift_deliveries(session, shift_id)
        user = await requests.get_user(session, message.from_user.id)

        if not deliveries:
            await requests.close_shift(session, shift_id, fuel_amount)
            await state.clear()
            await message.answer("🏁 Смена закрыта. Отгрузок сегодня не было.", reply_markup=main_menu_kb(user.is_admin))
            return

        report = "📝 <b>ИТОГ ВАШЕЙ СМЕНЫ:</b>\n\n"
        kg_data = {}
        total_shift_sum = 0

        for d in deliveries:
            kg_name = d.kindergarten.name
            if kg_name not in kg_data:
                kg_data[kg_name] = {"items": [], "total": 0}

            price = d.total_price_sadik
            kg_data[kg_name]["items"].append(
                f"  ◦ {d.product.name}: {d.weight_fact} {d.product.unit} — <b>{price:,} сум</b>")
            kg_data[kg_name]["total"] += price
            total_shift_sum += price

        for name, info in kg_data.items():
            report += f"🏫 <b>{name}</b>\n"
            report += "\n".join(info["items"]) + "\n"
            report += f"   🏷 Итого: <b>{info['total']:,} сум</b>\n\n"

        # --- ВОТ ТУТ МЕНЯЕМ ВЫВОД ---
        # Считаем чистую сумму прямо здесь для текста
        final_net_amount = total_shift_sum - fuel_amount

        report += f"💰 Общая выручка: {total_shift_sum:,} сум\n"
        report += f"⛽ Бензин: -{fuel_amount:,} сум\n"
        report += "───────────────────\n"
        report += f"💵 <b>ИТОГО К ВЫДАЧЕ: {final_net_amount:,} сум</b>\n\n"  # Теперь водитель видит разницу
        report += "🏁 Смена закрыта. Хорошего отдыха!"
        # ----------------------------

        await requests.close_shift(session, shift_id, fuel_amount)
        await state.clear()

        await message.answer(report, reply_markup=main_menu_kb(user.is_admin), parse_mode="HTML")

    except ValueError:
        await message.answer("Ошибка! Введите сумму расхода цифрами (например: 50000) или 0.")
# Показываем садики, которые уже ввел водитель в этой смене
@router.callback_query(F.data == "manage_current_shift")
async def manage_current(callback: types.CallbackQuery, session: AsyncSession):
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_or_create_shift(session, user.id)
    deliveries = await requests.get_shift_deliveries(session, shift.id)

    if not deliveries:
        await callback.answer("В этой смене еще нет записей.", show_alert=True)
        return

    kgs = {d.kindergarten.id: d.kindergarten.name for d in deliveries}

    builder = InlineKeyboardBuilder()
    for kg_id, kg_name in kgs.items():
        builder.button(text=f"❌ Удалить {kg_name}", callback_data=f"del_kg_curr:{kg_id}")
    builder.button(text="⬅️ Назад", callback_data="back_to_loop")  # Сделай хендлер для возврата к кнопкам петли
    builder.adjust(1)

    await callback.message.edit_text("Выберите садик для удаления:", reply_markup=builder.as_markup())


# Удаление садика
@router.callback_query(F.data.startswith("del_kg_curr:"))
async def delete_kg_curr(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_or_create_shift(session, user.id)
    await requests.delete_kg_from_active_shift(session, shift.id, kg_id)
    await callback.answer("Садик удален!", show_alert=True)
    await manage_current(callback, session)  # Обновляем список


# 1. Кнопка "Назад" в основную петлю (исправляем твою ошибку)
@router.callback_query(F.data == "back_to_loop")
async def back_to_loop_handler(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Данные сохранены. Что делаем дальше?",
        reply_markup=get_loop_kb()  # Твоя функция с 4-мя кнопками
    )


# 2. Список садиков (Первый уровень просмотра)
@router.callback_query(F.data == "manage_current_shift")
async def manage_current(callback: types.CallbackQuery, session: AsyncSession):
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_or_create_shift(session, user.id)
    deliveries = await requests.get_shift_deliveries(session, shift.id)

    if not deliveries:
        await callback.answer("В этой смене пока пусто", show_alert=True)
        return

    # Группируем садики
    kgs = {d.kindergarten.id: d.kindergarten.name for d in deliveries}

    builder = InlineKeyboardBuilder()
    for kg_id, kg_name in kgs.items():
        builder.button(text=f"🏫 {kg_name}", callback_data=f"view_kg_det:{kg_id}")

    builder.button(text="⬅️ Назад", callback_data="back_to_loop")
    builder.adjust(1)

    await callback.message.edit_text(
        "🔍 **Просмотр текущей смены:**\nВыберите садик, чтобы увидеть детали или удалить его.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# 3. Детали конкретного садика (Второй уровень просмотра)
@router.callback_query(F.data.startswith("view_kg_det:"))
async def view_kg_details(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_or_create_shift(session, user.id)

    # Получаем товары только этого садика
    items = await requests.get_kg_deliveries_in_shift(session, shift.id, kg_id)

    if not items:
        await callback.answer("Данные не найдены")
        return

    kg_name = items[0].kindergarten.name
    res_text = f"🏫 **Садик: {kg_name}**\n\n"
    kg_total = 0

    for row in items:
        res_text += f"• {row.product.name}: {row.weight_fact} {row.product.unit} — {row.total_price_sadik:,} сум\n"
        kg_total += row.total_price_sadik

    res_text += f"\n💰 **Итого по садику: {kg_total:,} сум**"

    builder = InlineKeyboardBuilder()
    # Кнопка удаления именно этого садика
    builder.button(text="🗑 Удалить этот садик", callback_data=f"del_kg_curr:{kg_id}")
    builder.button(text="⬅️ Назад к списку", callback_data="manage_current_shift")
    builder.adjust(1)

    await callback.message.edit_text(res_text, reply_markup=builder.as_markup(), parse_mode="Markdown")


# 4. Само удаление (уже исправленное с kindergarten_id)
@router.callback_query(F.data.startswith("del_kg_curr:"))
async def delete_kg_curr(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_or_create_shift(session, user.id)

    # Твоя исправленная колонка kindergarten_id
    await requests.delete_kg_from_active_shift(session, shift.id, kg_id)

    await callback.answer("Садик полностью удален из смены", show_alert=True)
    # Возвращаем водителя к списку оставшихся садиков
    await manage_current(callback, session)


# 1. Список садиков в текущей смене
@router.callback_query(F.data == "manage_current_shift")
async def manage_current(callback: types.CallbackQuery, session: AsyncSession):
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_active_shift(session, user.id)
    deliveries = await requests.get_shift_deliveries(session, shift.id)

    if not deliveries:
        await callback.answer("В этой смене пока нет записей.", show_alert=True)
        return

    # Собираем словарь садиков {id: имя}
    kgs = {d.kindergarten.id: d.kindergarten.name for d in deliveries}

    # Вызываем твой инлайн из inline.py
    await callback.message.edit_text(
        "🔍 **Просмотр текущей смены:**\nВыберите садик для деталей или удаления.",
        reply_markup=inline.get_manage_current_kb(kgs),
        parse_mode="Markdown"
    )


# 2. Детали садика и кнопка "Удалить"
@router.callback_query(F.data.startswith("view_kg_det:"))
async def view_kg_details(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_active_shift(session, user.id)

    # Получаем товары этого садика (функцию добавь в requests.py)
    items = await requests.get_kg_deliveries_in_shift(session, shift.id, kg_id)

    kg_name = items[0].kindergarten.name
    res_text = f"🏫 **Садик: {kg_name}**\n\n"
    kg_total = 0
    for row in items:
        res_text += f"• {row.product.name}: {row.weight_fact} {row.product.unit} — {row.total_price_sadik:,} сум\n"
        kg_total += row.total_price_sadik

    res_text += f"\n💰 **Итого: {kg_total:,} сум**"

    # Вызываем клавиатуру удаления
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить этот садик", callback_data=f"del_kg_curr:{kg_id}")
    builder.button(text="⬅️ Назад", callback_data="manage_current_shift")
    builder.adjust(1)

    await callback.message.edit_text(res_text, reply_markup=builder.as_markup(), parse_mode="Markdown")


# 3. Само удаление
@router.callback_query(F.data.startswith("del_kg_curr:"))
async def delete_kg_curr(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_active_shift(session, user.id)

    await requests.delete_kg_from_active_shift(session, shift.id, kg_id)
    await callback.answer("Садик удален!", show_alert=True)
    await manage_current(callback, session)  # Возвращаем к списку


# 4. Возврат в петлю (кнопка Назад)
@router.callback_query(F.data == "back_to_loop")
async def back_to_loop(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Что делаем дальше?",
        reply_markup=get_loop_kb()  # Твоя функция из inline.py
    )


# Обработка инлайн-кнопки "Завершить смену" из петли
@router.callback_query(F.data == "go_to_close_shift")
async def inline_close_shift(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    # Передаем callback.from_user.id явно, чтобы не было ошибки NoneType
    await close_shift_start(callback.message, state, session, manual_user_id=callback.from_user.id)
    await callback.answer()


# Этот хендлер мы уже создавали, просто добавим возврат в петлю в конце
@router.callback_query(F.data.startswith("update_date_to:"))
async def finalize_update_date(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    date_type = callback.data.split(":")[1]
    new_date = datetime.now() if date_type == "today" else datetime.now() - timedelta(days=1)

    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_active_shift(session, user.id)

    # Обновляем в базе
    await requests.update_shift_date(session, shift.id, new_date)

    await callback.answer(f"Дата изменена на {new_date.strftime('%d.%m')}", show_alert=True)

    # Возвращаем его к кнопкам "петли"
    await callback.message.edit_text(
        f"✅ Дата всей смены изменена на **{new_date.strftime('%d.%m.%Y')}**.\n"
        f"Все введенные товары сохранены под этим числом.\n\n"
        f"Что делаем дальше?",
        reply_markup=get_loop_kb(),  # Та самая клавиатура с новой кнопкой
        parse_mode="Markdown"
    )


# 1. Показываем выбор даты
@router.callback_query(F.data == "change_shift_date_start")
async def change_date_request(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    today = datetime.now().strftime("%d.%m")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m")

    builder.button(text=f"📅 Сегодня ({today})", callback_data="apply_new_date:today")
    builder.button(text=f"📅 Вчера ({yesterday})", callback_data="apply_new_date:yesterday")
    builder.button(text="⬅️ Назад", callback_data="back_to_loop")
    builder.adjust(1)

    await callback.message.edit_text(
        "Вы ошиблись датой? Выберите правильную дату для этой смены.\n"
        "**Все введенные садики сохранятся!**",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# 2. Применяем новую дату
@router.callback_query(F.data.startswith("apply_new_date:"))
async def apply_date_fix(callback: types.CallbackQuery, session: AsyncSession):
    date_type = callback.data.split(":")[1]

    # Делаем дату "чистой" (00:00:00)
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    new_date = now if date_type == "today" else now - timedelta(days=1)

    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_active_shift(session, user.id)

    if shift:
        await requests.update_shift_date(session, shift.id, new_date)
        await callback.answer(f"Дата изменена на {new_date.strftime('%d.%m')}", show_alert=True)

        await callback.message.edit_text(
            f"✅ Дата всей смены изменена на **{new_date.strftime('%d.%m.%Y')}**.\n"
            "Все данные успешно перенесены.\n\n"
            "Что делаем дальше?",
            reply_markup=get_loop_kb(),
            parse_mode="Markdown"
        )
    else:
        await callback.answer("Ошибка: Активная смена не найдена", show_alert=True)