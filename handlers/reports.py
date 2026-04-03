from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.fsm.context import FSMContext  # ДОБАВЬ ЭТУ СТРОКУ

# Импортируем твои модули
from database import requests
from keyboards import inline  # Импорт твоих новых функций из inline.py
from utils.states import DeliveryState # И ЭТУ (нужна для редактирования)


from aiogram.types import FSInputFile
from utils.exporters import create_shift_excel, create_shift_pdf


router = Router()


# 1. Список отчетов (Архив)
@router.message(F.text == "📊 Мои отчеты")
@router.callback_query(F.data.startswith("rep_page:"))
async def show_my_reports(event: types.Message | types.CallbackQuery, session: AsyncSession):
    # --- ИСПРАВЛЕННЫЙ БЛОК ОПРЕДЕЛЕНИЯ СТРАНИЦЫ ---
    # По умолчанию всегда 0-я страница
    page = 0

    # Если это колбэк и он пришел именно от кнопок пагинации (rep_page:),
    # тогда вынимаем номер страницы. В остальных случаях (удаление/текст) будет 0.
    if isinstance(event, types.CallbackQuery) and event.data.startswith("rep_page:"):
        try:
            page = int(event.data.split(":")[1])
        except (ValueError, IndexError):
            page = 0
    # -----------------------------------------------

    limit = 5
    offset = page * limit
    user_id = event.from_user.id

    # 2. Запрос в базу
    # Убедись, что в requests.get_user_shifts добавлен Shift.opened_at, как мы делали ранее!
    shifts = await requests.get_user_shifts(session, user_id, limit, offset)

    # 3. КРИТИЧЕСКИЙ МОМЕНТ:
    # Если мы удалили последний отчет на 2-й странице, shifts будет пустым.
    # В этом случае откатываемся на 0-ю страницу.
    if not shifts and page > 0:
        page = 0
        offset = 0
        shifts = await requests.get_user_shifts(session, user_id, limit, offset)

    # Если отчетов вообще нет в базе (даже на 0 странице)
    if not shifts:
        text = "У вас пока нет закрытых отчетов."
        if isinstance(event, types.CallbackQuery):
            await event.message.edit_text(text)
            await event.answer()
        else:
            await event.answer(text)
        return

    # 4. Получаем клавиатуру
    kb = inline.get_reports_paging_kb(shifts, page=page, limit=limit)

    text = f"📂 **Ваш архив отчетов (стр. {page + 1}):**\nВыберите нужную дату."

    if isinstance(event, types.CallbackQuery):
        # Используем try/except на случай, если сообщение идентично
        try:
            await event.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        except Exception:
            pass
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode="Markdown")


# 2. Просмотр конкретного отчета (Детализация)
@router.callback_query(F.data.startswith("view_rep:"))
async def view_single_report(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    # Получаем данные смены
    shift = await requests.get_shift_by_id(session, shift_id)
    # Получаем все отгрузки этой смены
    deliveries = await requests.get_shift_deliveries(session, shift_id)

    if not deliveries or not shift:
        await callback.answer("Данные не найдены.", show_alert=True)
        return

    report_text = f"📋 **Отчет за {shift.opened_at.strftime('%d.%m.%Y')}**\n\n"
    total_sum = 0
    for d in deliveries:
        report_text += (
            f"🏫 {d.kindergarten.name}\n"
            f"  ◦ {d.product.name}: {d.weight_fact} {d.product.unit} = {d.total_price_sadik:,} сум\n"
        )
        total_sum += d.total_price_sadik

    # --- ВОТ ТУТ ГЛАВНОЕ ИЗМЕНЕНИЕ ---
    fuel = shift.fuel_expense or 0  # Берем бензин (если там NULL, то 0)
    final_amount = total_sum - fuel  # Вычитаем из общей суммы товаров бензин

    report_text += f"\n⛽ Бензин: **{fuel:,} сум**"
    report_text += f"\n💰 **ОБЩАЯ ВЫРУЧКА: {total_sum:,} сум**"
    report_text += f"\n💵 **ИТОГО К ВЫДАЧЕ: {final_amount:,} сум**"  # Выводим чистый итог
    # ---------------------------------

    kb = inline.get_report_details_kb(shift_id)
    await callback.message.edit_text(report_text, reply_markup=kb, parse_mode="Markdown")

# 3. Жесткое удаление отчета
@router.callback_query(F.data.startswith("del_rep:"))
async def delete_report_final(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])
    await requests.delete_shift_full(session, shift_id)
    await callback.answer("🚨 Отчет полностью удален!", show_alert=True)

    # Теперь при этом вызове show_my_reports увидит префикс "del_rep",
    # поймет, что это не пагинация, и просто откроет первую страницу.
    await show_my_reports(callback, session)


@router.callback_query(F.data.startswith("edit_rep:"))
async def edit_old_report(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    active_shift = await requests.get_active_shift(session, user_id)
    if active_shift and active_shift.id != shift_id:
        await callback.answer("⚠️ Сначала завершите текущую смену!", show_alert=True)
        return

    await requests.unclose_shift(session, shift_id)

    # Очищаем старый стейт и записываем только ID смены
    await state.clear()
    await state.update_data(shift_id=shift_id)

    # Вместо get_loop_kb создаем специальное меню для начала правки
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить товары в садик", callback_data="edit_start_add")
    builder.button(text="🔍 Просмотр / Удалить садики", callback_data="manage_current_shift")
    builder.button(text="🗓 Исправить дату смены", callback_data="change_shift_date_start")
    builder.button(text="🏁 Завершить правки", callback_data="go_to_close_shift")
    builder.adjust(1)

    await callback.message.edit_text(
        "🛠 **Режим редактирования отчета**\n\n"
        "Выберите, что вы хотите сделать:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await callback.answer()


# Добавь этот маленький хендлер рядом в reports.py
@router.callback_query(F.data == "edit_start_add")
async def edit_start_add(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    from handlers.delivery import show_kindergartens
    await show_kindergartens(callback.message, state, session)


@router.callback_query(F.data.startswith("export_xlsx:"))
async def handle_export_xlsx(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])
    shift = await requests.get_shift_full_details(session, shift_id)

    if not shift or not shift.deliveries:
        await callback.answer("Данные не найдены", show_alert=True)
        return

    await callback.answer("⏳ Генерирую Excel...")

    # Проверяем админа
    user = await requests.get_user(session, callback.from_user.id)

    # Передаем user.is_admin в генератор
    path = create_shift_excel(shift, is_admin=user.is_admin)
    document = FSInputFile(path)

    await callback.message.answer_document(
        document,
        caption=f"📗 Excel-отчет за {shift.opened_at.strftime('%d.%m.%Y')}"
    )


@router.callback_query(F.data.startswith("export_pdf:"))
async def handle_export_pdf(callback: types.CallbackQuery, session: AsyncSession):
    # 1. Вытаскиваем ID смены из колбэка
    shift_id = int(callback.data.split(":")[1])

    # 2. Получаем полные данные смены (водитель, товары, садики)
    shift = await requests.get_shift_full_details(session, shift_id)

    if not shift or not shift.deliveries:
        await callback.answer("Данные для этого отчета не найдены.", show_alert=True)
        return

    # Уведомляем пользователя, что процесс пошел (чтобы он не тыкал кнопку дважды)
    await callback.answer("⏳ Генерирую PDF-файл...")

    # 3. Проверяем права пользователя (админ видит прибыль, водитель — нет)
    user = await requests.get_user(session, callback.from_user.id)

    try:
        # 4. Вызываем генератор PDF из utils/exporters.py
        # Передаем is_admin=True/False, чтобы отчет был правильного типа
        pdf_path = create_shift_pdf(shift, is_admin=user.is_admin)

        # 5. Подготавливаем файл для отправки
        document = FSInputFile(pdf_path)

        # 6. Отправляем PDF пользователю
        await callback.message.answer_document(
            document=document,
            caption=f"📄 PDF-отчет за {shift.opened_at.strftime('%d.%m.%Y')}\nВодитель: {shift.driver.full_name}"
        )

    except Exception as e:
        # Если что-то пошло не так (например, не нашелся шрифт), сообщаем об ошибке
        await callback.message.answer(f"❌ Ошибка при создании PDF: {e}")
        print(f"Ошибка PDF: {e}")  # Для отладки в консоли