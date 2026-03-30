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

def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Добавить отгрузку")],
            [KeyboardButton(text="⛽ Заправить / Закрыть смену")],
            [KeyboardButton(text="📝 Изменить имя")]
        ],
        resize_keyboard=True
    )

def get_objects_kb():
    builder = ReplyKeyboardBuilder()

    for name in KINDERGARTENS:
        builder.button(text=name)

    builder.adjust(2)

    return builder.as_markup(resize_keyboard=True)
