from aiogram.fsm.state import State, StatesGroup

class Register(StatesGroup):
    name = State()
    phone = State()

class EditName(StatesGroup):
    name = State()

class DeliveryState(StatesGroup):
    object_name = State()
    weight_plan = State()
    weight_fact = State()