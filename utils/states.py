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