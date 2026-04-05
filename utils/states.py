from aiogram.fsm.state import State, StatesGroup

class Register(StatesGroup):
    name = State()
    phone = State()

class EditName(StatesGroup):
    name = State()

class DeliveryState(StatesGroup):
    object_name = State()       # Выбор садика
    choosing_product = State()  # Выбор товара из 70 позиций
    weight_plan = State()       # Ввод плана (кг или шт)
    weight_fact = State()       # Ввод факта (кг или шт)
    waiting_fuel = State()  # Новый стейт для бензина
    waiting_other_amount = State()  # Ввод суммы доп. расходов # НА СЕРВАК
    waiting_other_comment = State()  # Ввод комментария (обед, ремонт и т.д.) # НА СЕРВАК


# --- ТОВАРЫ: ДОБАВЛЕНИЕ ---
class AdminState(StatesGroup):
    waiting_product_name = State()
    waiting_product_unit = State()  # Новый шаг для КГ/ЛИТР/ШТ
    waiting_p_sadik_add = State()
    waiting_p_zakup_add = State()

    # Рассылка (оставляем тут)
    waiting_broadcast_text = State()


# --- ТОВАРЫ: РЕДАКТИРОВАНИЕ ---
class AdminEdit(StatesGroup):
    waiting_p_sadik_edit = State()
    waiting_p_zakup_edit = State()
    waiting_name_edit = State()
    waiting_shift_fuel = State()

    waiting_shift_other_exp = State()  # Ожидание суммы # НА СЕРВАК
    waiting_shift_other_comment = State()  # Ожидание комментария # НА СЕРВАК

# --- САДИКИ ---
class KGState(StatesGroup):
    waiting_kg_name = State()      # Для добавления
    waiting_kg_edit_name = State() # Для изменения названия


class AdminStatsState(StatesGroup):
    waiting_custom_period = State()