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

    await requests.add_user(
        session=session,
        tg_id=message.from_user.id,
        full_name=data["name"],
        phone_number=message.contact.phone_number
    )
    await state.clear()
    await message.answer("Регистрация завершена", reply_markup=main_menu_kb())

@router.message(Register.phone)
async def reg_phone_error(message: types.Message):
    await message.answer("Пожалуйста, используйте кнопку **«📱 Отправить контакт»**.\n\n"
        "Мы принимаем номер только через кнопку, чтобы данные были верными.",
        reply_markup=get_register_kb(),
        parse_mode="Markdown")

@router.message(F.text == "📝 Изменить имя")
async def edit_name_start(message: types.Message, state: FSMContext):
    await message.answer("Введите новое Имя и Фамилию:")
    await state.set_state(EditName.name)

@router.message(EditName.name)
async def edit_name_done(message: types.Message, state: FSMContext, session: AsyncSession):
    await requests.update_user_name(session, message.from_user.id, message.text)
    await state.clear()
    await message.answer(f"Готово! Вы изменили имя на {message.text}",
                         reply_markup=main_menu_kb())