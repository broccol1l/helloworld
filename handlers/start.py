from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from database import requests
from utils.states import Register, EditName
from keyboards.reply import get_register_kb, main_menu_kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext, session: AsyncSession):
    user = await requests.get_user(session, message.from_user.id)

    if user:
        await message.answer(f"С возвращением, {user.full_name}!", reply_markup=main_menu_kb())
    else:
        await message.answer("Привет! Вы не зарегистрированы в системе.\nВведите ваше Имя и Фамилию:")
        await state.set_state(Register.name)


@router.message(Register.name)
async def reg_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Теперь отправьте свой номер телефона", reply_markup=get_register_kb())
    await state.set_state(Register.phone)


@router.message(Register.phone, F.contact)
async def reg_phone(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()

    # Вытаскиваем номер телефона из присланного контакта
    user_phone = message.contact.phone_number

    # Передаем и имя, и телефон в базу
    await requests.add_user(
        session=session,
        tg_id=message.from_user.id,
        full_name=data["name"],
        phone=user_phone
    )

    await state.clear()
    await message.answer(
        f"Регистрация завершена!\nИмя: {data['name']}\nТел: {user_phone}",
        reply_markup=main_menu_kb()
    )


# Хендлер нажатия на кнопку "Изменить имя"
@router.message(F.text == "📝 Изменить имя")
async def edit_name_start(message: types.Message, state: FSMContext):
    await message.answer("Введите ваше новое Имя и Фамилию:")
    await state.set_state(EditName.name)


# Хендлер получения нового имени
@router.message(EditName.name)
async def edit_name_finish(message: types.Message, state: FSMContext, session: AsyncSession):
    new_name = message.text

    # Обновляем имя в базе (используем существующий requests или прямо здесь)
    # Предположим, у тебя в requests.py есть функция update_user_name или сделаем через update
    from sqlalchemy import update
    from database.models import User

    await session.execute(
        update(User).where(User.id == message.from_user.id).values(full_name=new_name)
    )
    await session.commit()

    await state.clear()
    await message.answer(f"✅ Готово! Теперь я буду называть вас: **{new_name}**",
                         reply_markup=main_menu_kb(),
                         parse_mode="Markdown")