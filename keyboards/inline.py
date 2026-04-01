import math
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
# --- ФАБРИКИ КНОПОК ---

class KGOrderCallback(CallbackData, prefix="kg"):
    action: str  # "select" или "nav"
    kg_id: int   # Теперь храним ID из базы
    page: int    # Номер страницы для навигации

class ProductCallback(CallbackData, prefix="prod"):
    action: str
    prod_id: int # ID товара из базы
    page: int


# --- КЛАВИАТУРА САДИКОВ ---

def get_kg_paging_kb(kg_list, page: int = 0):
    """
    kg_list: список объектов Kindergarten из базы
    """
    builder = InlineKeyboardBuilder()
    items_per_page = 6

    start = page * items_per_page
    end = start + items_per_page
    current_items = kg_list[start:end]

    for kg in current_items:
        builder.button(
            text=kg.name,
            callback_data=KGOrderCallback(action="select", kg_id=kg.id, page=page)
        )

    builder.adjust(1)

    if len(kg_list) > items_per_page:
        nav_row = []
        total_pages = math.ceil(len(kg_list) / items_per_page)

        # Назад
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="⬅️", callback_data=KGOrderCallback(action="nav", kg_id=0, page=page - 1).pack()))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="none"))

        # Страница
        nav_row.append(InlineKeyboardButton(text=f"{page + 1} / {total_pages}", callback_data="none"))

        # Вперед
        if end < len(kg_list):
            nav_row.append(InlineKeyboardButton(
                text="➡️", callback_data=KGOrderCallback(action="nav", kg_id=0, page=page + 1).pack()))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="none"))

        builder.row(*nav_row)

    return builder.as_markup()


# --- КЛАВИАТУРА ТОВАРОВ ---

def get_products_paging_kb(products_list, page: int = 0):
    """
    products_list: список объектов Product из базы
    """
    builder = InlineKeyboardBuilder()
    items_per_page = 10 # Товаров можно побольше на экран

    start = page * items_per_page
    end = start + items_per_page
    current_items = products_list[start:end]

    for prod in current_items:
        builder.button(
            text=f"{prod.name} ({prod.unit})", # Сразу пишем кг или шт
            callback_data=ProductCallback(action="select", prod_id=prod.id, page=page)
        )

    builder.adjust(1)

    if len(products_list) > items_per_page:
        nav_row = []
        total_pages = math.ceil(len(products_list) / items_per_page)

        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="⬅️", callback_data=ProductCallback(action="nav", prod_id=0, page=page - 1).pack()))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="none"))

        nav_row.append(InlineKeyboardButton(text=f"{page + 1} / {total_pages}", callback_data="none"))

        if end < len(products_list):
            nav_row.append(InlineKeyboardButton(
                text="➡️", callback_data=ProductCallback(action="nav", prod_id=0, page=page + 1).pack()))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="none"))

        builder.row(*nav_row)

    return builder.as_markup()


# --- КЛАВИАТУРА ЦИКЛА ---

def get_loop_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить еще товар", callback_data="add_more_prod")
    builder.button(text="✅ Завершить этот садик", callback_data="finish_this_kg")

    # НОВАЯ КНОПКА:
    builder.button(text="🗓 Исправить дату смены", callback_data="change_shift_date_start")

    builder.button(text="🔍 Просмотр / Удалить садик", callback_data="manage_current_shift")
    builder.button(text="🏁 Завершить смену", callback_data="go_to_close_shift")
    builder.adjust(1)
    return builder.as_markup()

# --- КЛАВИАТУРА АРХИВА (СПИСОК СМЕН) ---
def get_reports_paging_kb(shifts, page: int = 0, limit: int = 5):
    builder = InlineKeyboardBuilder()

    for shift in shifts:
        # shift.closed_at и shift.total_sum приходят из базы
        date_str = shift.closed_at.strftime("%d.%m.%Y")
        builder.button(
            text=f"📅 {date_str} | {shift.total_sum:,} сум",
            callback_data=f"view_rep:{shift.id}"
        )

    builder.adjust(1)

    # Навигация
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Раньше", callback_data=f"rep_page:{page - 1}"))
    if len(shifts) == limit:
        nav_row.append(InlineKeyboardButton(text="Далее ➡️", callback_data=f"rep_page:{page + 1}"))

    if nav_row:
        builder.row(*nav_row)

    return builder.as_markup()


# --- КЛАВИАТУРА ДЕТАЛЕЙ ОТЧЕТА ---
def get_report_details_kb(shift_id: int):
    builder = InlineKeyboardBuilder()

    # НОВАЯ КНОПКА
    builder.button(text="✏️ Редактировать (добавить/удалить)", callback_data=f"edit_rep:{shift_id}")

    builder.button(text="🗑 Удалить отчет", callback_data=f"del_rep:{shift_id}")
    builder.button(text="⬅️ Назад к списку", callback_data="rep_page:0")
    builder.adjust(1)
    return builder.as_markup()


# --- ВЫБОР ДАТЫ ПРИ СТАРТЕ ---
def get_date_selection_kb():
    builder = InlineKeyboardBuilder()
    today = datetime.now().strftime("%d.%m")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m")

    builder.button(text=f"📅 Сегодня ({today})", callback_data="set_date:today")
    builder.button(text=f"📅 Вчера ({yesterday})", callback_data="set_date:yesterday")
    builder.adjust(1)
    return builder.as_markup()


# --- УПРАВЛЕНИЕ ТЕКУЩЕЙ СМЕНОЙ (УДАЛЕНИЕ САДИКА) ---
def get_manage_current_kb(kgs_dict):
    builder = InlineKeyboardBuilder()
    for kg_id, kg_name in kgs_dict.items():
        builder.button(text=f"❌ Удалить {kg_name}", callback_data=f"del_kg_curr:{kg_id}")

    builder.button(text="⬅️ Назад", callback_data="back_to_loop")
    builder.adjust(1)
    return builder.as_markup()
