from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from utils.constants import KINDERGARTENS


def get_register_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить контакт", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_kb(is_admin: bool = False):
    buttons = [
        [KeyboardButton(text="📦 Добавить отгрузку")],
        [KeyboardButton(text="📊 Мои отчеты"), KeyboardButton(text="🏁 Завершить смену")],
        [KeyboardButton(text="📝 Изменить имя")]
    ]

    if is_admin:
        buttons.append([KeyboardButton(text="⚙️ Админ-панель")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )

def get_objects_kb():
    builder = ReplyKeyboardBuilder()

    for name in KINDERGARTENS:
        builder.button(text=name)

    builder.adjust(2)

    return builder.as_markup(resize_keyboard=True)
