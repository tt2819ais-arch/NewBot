from aiogram.dispatcher.filters.state import State, StatesGroup

class AgentForm(StatesGroup):
    waiting_for_data = State()

class SessionStates(StatesGroup):
    setting_target = State()
