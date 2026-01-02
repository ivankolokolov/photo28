"""FSM состояния бота."""
from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    """Состояния процесса оформления заказа."""
    
    # Выбор формата
    selecting_format = State()
    
    # Загрузка фото
    uploading_photos = State()
    
    # Просмотр и редактирование заказа
    reviewing_order = State()
    
    # Удаление фото
    deleting_photos = State()
    
    # Выбор доставки
    selecting_delivery = State()
    
    # Ввод данных доставки (Озон)
    entering_ozon_delivery = State()
    
    # Ввод данных доставки (Курьер)
    entering_courier_delivery = State()
    
    # Ввод промокода
    entering_promocode = State()
    
    # Ожидание квитанции оплаты
    waiting_payment_receipt = State()


class MyOrdersStates(StatesGroup):
    """Состояния просмотра заказов."""
    
    viewing_orders = State()
    viewing_order_details = State()

