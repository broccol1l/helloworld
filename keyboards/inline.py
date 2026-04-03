import math
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton
from database.models import Product
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


def get_reports_paging_kb(shifts, page: int = 0, limit: int = 5):
    builder = InlineKeyboardBuilder()

    for shift in shifts:
        # ИСПОЛЬЗУЕМ opened_at, так как именно её мы правим кнопкой "Исправить дату"
        date_str = shift.opened_at.strftime("%d.%m.%Y")

        # Если total_sum у тебя считается в запросе, оставляем как есть
        builder.button(
            text=f"📅 {date_str} | {shift.total_sum:,} сум",
            callback_data=f"view_rep:{shift.id}"
        )

    builder.adjust(1)
    # ... остальной код навигации без изменений ...
    return builder.as_markup()


# --- КЛАВИАТУРА ДЕТАЛЕЙ ОТЧЕТА ---
def get_report_details_kb(shift_id: int):
    builder = InlineKeyboardBuilder()

    # РЯД 1: Кнопки выгрузки (добавили новые)
    builder.button(text="📗 Excel", callback_data=f"export_xlsx:{shift_id}")
    builder.button(text="📄 PDF", callback_data=f"export_pdf:{shift_id}")

    # РЯД 2: ТВОЙ ОРИГИНАЛЬНЫЙ ТЕКСТ (ничего не меняем)
    builder.button(text="✏️ Редактировать (добавить/удалить)", callback_data=f"edit_rep:{shift_id}")

    # РЯД 3: Удаление и Назад
    builder.button(text="🗑 Удалить отчет", callback_data=f"del_rep:{shift_id}")
    builder.button(text="⬅️ Назад к списку", callback_data="rep_page:0")

    # Сетка: 2 кнопки (экспорт), 1 кнопка (редакт), 2 кнопки (удалить/назад)
    builder.adjust(2, 1, 2)
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


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def admin_main_kb():
    buttons = [
        [InlineKeyboardButton(text="📦 Товары и Цены", callback_data="admin_products")],
        [InlineKeyboardButton(text="🏫 Садики (Объекты)", callback_data="admin_kindergartens")],
        [InlineKeyboardButton(text="👥 Водители и Отчеты", callback_data="admin_drivers")],
        [InlineKeyboardButton(text="📊 Общая Аналитика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="⬅️ Выйти в меню водителя", callback_data="admin_exit")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ADMIN
def get_products_list_kb(products: list[Product], page: int = 0):
    builder = InlineKeyboardBuilder()
    limit = 6  # Сколько товаров на одной странице
    start = page * limit
    end = start + limit

    # Берем срез товаров для текущей страницы
    for product in products[start:end]:
        # Текст кнопки: Название (Цена садика / Цена закупа)
        btn_text = f"{product.name} ({int(product.price_sadik)}/{int(product.price_zakup)})"
        builder.row(InlineKeyboardButton(text=btn_text, callback_data=f"adm_prod_view:{product.id}"))

    # Кнопки навигации (назад/вперед)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"adm_prod_page:{page - 1}"))

    if end < len(products):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"adm_prod_page:{page + 1}"))

    if nav_buttons:
        builder.row(*nav_buttons)

    # Функциональные кнопки
    builder.row(InlineKeyboardButton(text="➕ Добавить товар", callback_data="adm_prod_add"))
    builder.row(InlineKeyboardButton(text="🏠 В начало", callback_data="admin_home"))

    return builder.as_markup()


def get_product_card_kb(product_id: int):
    builder = InlineKeyboardBuilder()

    # Кнопки редактирования (привязываем ID товара к callback_data)
    builder.row(InlineKeyboardButton(text="💰 Цена садика", callback_data=f"adm_prod_edit:p_sadik:{product_id}"))
    builder.row(InlineKeyboardButton(text="📉 Цена закупа", callback_data=f"adm_prod_edit:p_zakup:{product_id}"))
    builder.row(InlineKeyboardButton(text="✏️ Название", callback_data=f"adm_prod_edit:name:{product_id}"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить товар", callback_data=f"adm_prod_delete:{product_id}"))

    # Кнопка возврата в общий список
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_products"))

    return builder.as_markup()

def get_cancel_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel_edit"))
    return builder.as_markup()

def get_units_kb():
    builder = InlineKeyboardBuilder()
    for unit in ["кг", "литр", "шт"]:
        builder.button(text=unit, callback_data=f"unit_set:{unit}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel_edit"))
    return builder.as_markup()


# --- КЛАВИАТУРЫ ДЛЯ САДИКОВ ---

def get_kg_list_kb(kg_list: list, page: int = 0):
    builder = InlineKeyboardBuilder()
    limit = 6
    start = page * limit
    end = start + limit

    # Садики
    for kg in kg_list[start:end]:
        builder.row(InlineKeyboardButton(text=f"🏫 {kg.name}", callback_data=f"adm_kg_view:{kg.id}"))

    # Ряд навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"adm_kg_page:{page - 1}"))
    if end < len(kg_list):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"adm_kg_page:{page + 1}"))

    if nav_buttons:
        builder.row(*nav_buttons)

    # Управление (всегда отдельными рядами снизу)
    builder.row(InlineKeyboardButton(text="➕ Добавить садик", callback_data="adm_kg_add"))
    builder.row(InlineKeyboardButton(text="🏠 В начало", callback_data="admin_home"))

    return builder.as_markup()


def get_kg_card_kb(kg_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"adm_kg_edit:{kg_id}"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить садик", callback_data=f"adm_kg_delete:{kg_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_kindergartens"))
    return builder.as_markup()


# --- КЛАВИАТУРЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ---

def get_users_list_kb(users: list, page: int = 0):
    builder = InlineKeyboardBuilder()
    limit = 6
    start = page * limit
    end = start + limit

    for user in users[start:end]:
        # Статус на основе твоих полей
        if user.is_admin:
            status = "🛡️"
        elif user.is_blocked:
            status = "🚫"
        else:
            status = "🚚"

        name = user.full_name or f"ID: {user.id}"
        builder.row(InlineKeyboardButton(
            text=f"{status} {name}",
            callback_data=f"adm_user_view:{user.id}")
        )

    # Пагинация (оставляем как была)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"adm_user_page:{page - 1}"))
    if end < len(users):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"adm_user_page:{page + 1}"))

    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(InlineKeyboardButton(text="🏠 В начало", callback_data="admin_home"))
    return builder.as_markup()


def get_user_card_kb(user_id: int, is_admin: bool, is_blocked: bool):
    builder = InlineKeyboardBuilder()

    # Кнопки смены прав (Админ / Не админ)
    if is_admin:
        builder.row(InlineKeyboardButton(text="👤 Снять права админа", callback_data=f"adm_user_set:demote:{user_id}"))
    else:
        builder.row(InlineKeyboardButton(text="🛡️ Сделать админом", callback_data=f"adm_user_set:promote:{user_id}"))

    # Кнопки блокировки (Бан / Разбан)
    if is_blocked:
        builder.row(InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"adm_user_set:unblock:{user_id}"))
    else:
        builder.row(InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"adm_user_set:block:{user_id}"))

    builder.row(InlineKeyboardButton(text="⬅️ К списку пользователей", callback_data="admin_drivers"))
    builder.row(InlineKeyboardButton(text="📂 История отчетов", callback_data=f"adm_history:{user_id}"))
    return builder.as_markup()


# Клавиатура со списком дат (смен) водителя для АДМИНА
def get_admin_user_history_kb(shifts, user_id: int, page: int = 0, limit: int = 5):
    builder = InlineKeyboardBuilder()

    for shift in shifts:
        date_str = shift.opened_at.strftime("%d.%m.%Y")
        # Текст: Дата | Сумма (чтобы админ сразу видел масштаб)
        builder.button(
            text=f"📅 {date_str} | {shift.total_sum:,} сум",
            callback_data=f"adm_view_rep:{shift.id}"
        )

    builder.adjust(1)

    # Навигация (если смен много)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"adm_rep_page:{user_id}:{page - 1}"))
    if len(shifts) == limit:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"adm_rep_page:{user_id}:{page + 1}"))

    if nav_buttons:
        builder.row(*nav_buttons)

    # Кнопка возврата именно в карточку этого юзера
    builder.row(InlineKeyboardButton(text="⬅️ Назад в карточку", callback_data=f"adm_user_view:{user_id}"))

    return builder.as_markup()


# Кнопки управления конкретным отчетом для АДМИНА
def get_admin_report_tools_kb(shift_id: int, user_id: int):
    builder = InlineKeyboardBuilder()

    # Функционал как у водителя, но с админскими префиксами если нужно,
    # или используем те же, если логика общая
    builder.row(InlineKeyboardButton(text="✏️ Редактировать (Открыть смену)", callback_data=f"adm_edit_rep:{shift_id}"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить отчет полностью", callback_data=f"adm_del_rep:{shift_id}"))

    # Экспорт (можно заюзать твои текущие хендлеры)
    builder.row(
        InlineKeyboardButton(text="📗 Excel", callback_data=f"export_xlsx:{shift_id}"),
        InlineKeyboardButton(text="📄 PDF", callback_data=f"export_pdf:{shift_id}")
    )

    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку дат", callback_data=f"adm_history:{user_id}"))

    return builder.as_markup()


# Добавь это в keyboards/inline.py

def get_admin_edit_menu_kb(shift_id: int):
    builder = InlineKeyboardBuilder()
    # Обрати внимание на префиксы adm_
    builder.button(text="➕ Добавить товары", callback_data=f"adm_add_start:{shift_id}")
    builder.button(text="🔍 Просмотр / Удалить садики", callback_data=f"adm_manage_shift:{shift_id}")
    builder.button(text="🏁 Завершить правки", callback_data=f"adm_finish_edit:{shift_id}")
    builder.adjust(1)
    return builder.as_markup()


# Список садиков для удаления (для админа)
def get_admin_manage_kgs_kb(kgs_dict, shift_id: int):
    builder = InlineKeyboardBuilder()
    for kg_id, kg_name in kgs_dict.items():
        # Специфический колбэк для админа
        builder.button(text=f"❌ Удалить {kg_name}", callback_data=f"adm_del_kg:{shift_id}:{kg_id}")

    builder.button(text="⬅️ Назад", callback_data=f"adm_view_rep:{shift_id}")
    builder.adjust(1)
    return builder.as_markup()