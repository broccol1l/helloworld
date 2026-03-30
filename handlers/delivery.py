from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from database import requests
from utils.states import DeliveryState
from keyboards.reply import get_objects_kb, main_menu_kb

from keyboards.inline import get_kg_paging_kb, KGOrderCallback
from utils.constants import KINDERGARTENS

router = Router()

@router.message(F.text == "📦 Добавить отгрузку")
async def start_delivery(message: types.Message, state: FSMContext, session: AsyncSession):
    user = await requests.get_user(session, message.from_user.id)
    shift = await requests.get_or_create_shift(session, user.id)

    await state.update_data(shift_id=shift.id)
    await state.set_state(DeliveryState.object_name)
    await message.answer(
        "Выберите объект (садик) из списка ниже:",
        reply_markup=get_kg_paging_kb()
    )

@router.callback_query(KGOrderCallback.filter(), DeliveryState.object_name)
async def delivery_object_chosen(callback: types.CallbackQuery, callback_data: KGOrderCallback,
                                 state: FSMContext):
    if callback_data.action == "none":
        await callback.answer()  # Просто убираем часики, ничего не делаем
        return
    if callback_data.action == "nav":
        await callback.message.edit_reply_markup(
            reply_markup=get_kg_paging_kb(page=callback_data.value)
        )
    elif callback_data.action == "select":
        target_name = KINDERGARTENS[callback_data.value]
        await state.update_data(object_name=target_name)
        await state.set_state(DeliveryState.weight_plan)
        await callback.message.edit_text(
            f"✅ Выбран объект: <b>{target_name}</b>\n\nВведите вес по плану (кг):",
            parse_mode="HTML"  # Поменяли тут
        )
    await callback.answer()

@router.message(DeliveryState.weight_plan)
async def delivery_plan_chosen(message: types.Message, state: FSMContext):
    clean_text = message.text.replace(',', '.')
    try:
        weight = float(clean_text)
        await state.update_data(weight_plan=weight )

        await state.set_state(DeliveryState.weight_fact)
        await message.answer(
            f"План: <b>{weight} кг. принято.</b>\n"
            "Теперь введите <b>фактический вес</b> (кг), который принял садик:",
            parse_mode="HTML"  # И тут
        )
    except ValueError:
        await message.answer("Ошибка! Пожалуйста, введите вес цифрами (например: 15.5 или 10)")


@router.message(DeliveryState.weight_fact)
async def delivery_fact_chosen(message: types.Message, state: FSMContext, session: AsyncSession):
    clean_text = message.text.replace(',', '.')

    try:
        weight_fact = float(clean_text)

        # 1. Достаем план из памяти FSM
        data = await state.get_data()
        weight_plan = data.get("weight_plan")

        # 2. ПРОВЕРКА: Бизнес-логика (Факт не может быть больше Плана)
        if weight_fact > weight_plan:
            await message.answer(
                f"❌ **Ошибка!** Факт ({weight_fact} кг) не может быть больше плана ({weight_plan} кг).\n"
                f"Проверьте накладную и введите корректный вес:",
                parse_mode="Markdown"
            )
            return  # Останавливаем выполнение, ждем новый ввод

        # 3. Если проверка прошла — сохраняем
        shift_id = data.get("shift_id")
        obj_name = data.get("object_name")

        delivery = await requests.add_delivery(
            session, shift_id, obj_name, weight_plan, weight_fact
        )

        await state.clear()

        # Красивый отчет (теперь без минусов, так как мы их запретили)
        report = (
            f"✅ <b>Отгрузка сохранена!</b>\n\n"
            f"🏢 Объект: <b>{obj_name}</b>\n"
            f"📉 План: {weight_plan} кг\n"
            f"📈 Факт: {weight_fact} кг\n"
            f"❗ Разница: {delivery.diff}\n"
            f"💰 Сумма: <b>{delivery.total_price:,} сум</b>"
        )

        await message.answer(report, reply_markup=main_menu_kb(), parse_mode="HTML")

    except ValueError:
        await message.answer("Ошибка! Введите фактический вес цифрами.")