import math
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.constants import KINDERGARTENS

class KGOrderCallback(CallbackData, prefix="kg"):
    action: str  # "select" (выбор) или "nav" (навигация)
    value: int   # Индекс садика ИЛИ номер страницы


def get_kg_paging_kb(page: int = 0):
    builder = InlineKeyboardBuilder()
    items_per_page = 6  # Сколько садиков помещается на один "экран" телефона

    # 1. Режем список на куски (слайсинг)
    start = page * items_per_page
    end = start + items_per_page
    current_items = KINDERGARTENS[start:end]

    # 2. Создаем кнопки садиков
    for i, name in enumerate(current_items):
        real_index = start + i
        builder.button(
            text=name,  # Тут будет полное название садика
            callback_data=KGOrderCallback(action="select", value=real_index)
        )

    # 3. ВЫТЯГИВАЕМ В ШИРИНУ: Каждая кнопка на отдельной строке
    builder.adjust(1)

    # 4. ЛОГИКА ВИДИМОСТИ:
    # Если всех садиков меньше, чем лимит на страницу,
    # то навигация (стр. 1, стрелочки) ВООБЩЕ НЕ НУЖНА.
    if len(KINDERGARTENS) <= items_per_page:
        return builder.as_markup()

    # 5. Если садиков реально много (больше 6), добавляем кнопки управления
    nav_row = []
    total_pages = math.ceil(len(KINDERGARTENS) / items_per_page)

    # Кнопка Назад (или пустая заглушка для симметрии)
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️", callback_data=KGOrderCallback(action="nav", value=page - 1).pack()))
    else:
        nav_row.append(InlineKeyboardButton(text=" ", callback_data="none"))  # Пустое место

    # Кнопка с номером страницы (не нажимается)
    nav_row.append(InlineKeyboardButton(text=f"{page + 1} / {total_pages}", callback_data="none"))

    # Кнопка Вперед
    if end < len(KINDERGARTENS):
        nav_row.append(
            InlineKeyboardButton(text="➡️", callback_data=KGOrderCallback(action="nav", value=page + 1).pack()))
    else:
        nav_row.append(InlineKeyboardButton(text=" ", callback_data="none"))

    builder.row(*nav_row)

    return builder.as_markup()

