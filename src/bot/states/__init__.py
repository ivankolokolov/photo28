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
    
    # Редактирование кропа
    editing_crop = State()
    
    # Выбор доставки
    selecting_delivery = State()
    
    # Ввод данных доставки (ОЗОН) — пошагово
    entering_ozon_phone = State()
    entering_ozon_city = State()
    
    # Ввод данных доставки (Курьер) — пошагово
    entering_courier_phone = State()
    entering_courier_address = State()
    entering_courier_name = State()
    entering_courier_datetime = State()
    
    # Ввод данных самовывоза — пошагово
    entering_pickup_phone = State()
    entering_pickup_name = State()
    
    # Ввод промокода
    entering_promocode = State()
    
    # Ожидание квитанции оплаты
    waiting_payment_receipt = State()


class MyOrdersStates(StatesGroup):
    """Состояния просмотра заказов."""
    
    viewing_orders = State()
    viewing_order_details = State()

