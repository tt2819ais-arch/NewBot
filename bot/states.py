from aiogram.dispatcher.filters.state import State, StatesGroup

class AgentForm(StatesGroup):
    waiting_for_data = State()

class SessionForm(StatesGroup):
    waiting_for_target = State()
