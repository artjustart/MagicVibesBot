"""
Клавиатуры для бота Magic Vibes
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_menu() -> InlineKeyboardMarkup:
    """Главное меню бота"""
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(
        text="📅 Актуальные практики",
        callback_data="practices_list"
    ))
    builder.row(InlineKeyboardButton(
        text="🧘‍♀️ Индивидуальная сессия",
        callback_data="individual_session"
    ))
    builder.row(InlineKeyboardButton(
        text="🎓 Стартовый онлайн-курс",
        callback_data="starter_course"
    ))
    builder.row(InlineKeyboardButton(
        text="📚 Обучение 3 месяца",
        callback_data="three_month_course"
    ))
    builder.row(InlineKeyboardButton(
        text="🛠 Инструменты",
        callback_data="tools"
    ))
    builder.row(InlineKeyboardButton(
        text="💬 Связаться с менеджером",
        callback_data="contact_manager"
    ))
    
    return builder.as_markup()

def get_back_to_main_menu() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="◀️ Вернуться в главное меню",
        callback_data="main_menu"
    ))
    return builder.as_markup()

def get_practices_keyboard(practices: list) -> InlineKeyboardMarkup:
    """Клавиатура со списком актуальных практик"""
    builder = InlineKeyboardBuilder()
    
    for practice in practices:
        builder.row(InlineKeyboardButton(
            text=f"{practice.title} - {practice.price} грн",
            callback_data=f"practice_{practice.id}"
        ))
    
    builder.row(InlineKeyboardButton(
        text="◀️ Назад",
        callback_data="main_menu"
    ))
    
    return builder.as_markup()

def get_practice_schedule_keyboard(schedules: list, practice_id: int) -> InlineKeyboardMarkup:
    """Клавиатура с расписанием практики"""
    builder = InlineKeyboardBuilder()
    
    for schedule in schedules:
        date_str = schedule.datetime.strftime("%d.%m в %H:%M")
        available_text = f"(Осталось мест: {schedule.available_slots})" if schedule.available_slots else ""
        
        builder.row(InlineKeyboardButton(
            text=f"{date_str} {available_text}",
            callback_data=f"book_{schedule.id}"
        ))
    
    builder.row(InlineKeyboardButton(
        text="◀️ К списку практик",
        callback_data="practices_list"
    ))
    
    return builder.as_markup()

def get_booking_confirmation_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения бронирования"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="✅ Подтвердить и оплатить",
            callback_data=f"confirm_booking_{booking_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Отменить",
            callback_data=f"cancel_booking_{booking_id}"
        )
    )
    
    return builder.as_markup()

def get_payment_keyboard(payment_url: str, payment_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для оплаты"""
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(
        text="💳 Оплатить",
        url=payment_url
    ))
    builder.row(InlineKeyboardButton(
        text="✅ Я оплатил(а)",
        callback_data=f"check_payment_{payment_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="◀️ Вернуться в меню",
        callback_data="main_menu"
    ))
    
    return builder.as_markup()

def get_individual_session_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для индивидуальной сессии"""
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(
        text="📅 Выбрать дату и время",
        callback_data="individual_choose_datetime"
    ))
    builder.row(InlineKeyboardButton(
        text="💬 Написать менеджеру",
        callback_data="contact_manager"
    ))
    builder.row(InlineKeyboardButton(
        text="◀️ Назад",
        callback_data="main_menu"
    ))
    
    return builder.as_markup()

def get_courses_keyboard(courses: list) -> InlineKeyboardMarkup:
    """Клавиатура со списком курсов"""
    builder = InlineKeyboardBuilder()
    
    for course in courses:
        builder.row(InlineKeyboardButton(
            text=f"{course.title} - {course.price} грн",
            callback_data=f"course_{course.id}"
        ))
    
    builder.row(InlineKeyboardButton(
        text="◀️ Назад",
        callback_data="main_menu"
    ))
    
    return builder.as_markup()

def get_course_enrollment_keyboard(course_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для записи на курс"""
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(
        text="✅ Записаться на курс",
        callback_data=f"enroll_course_{course_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="ℹ️ Подробнее",
        callback_data=f"course_details_{course_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="◀️ Назад к курсам",
        callback_data="main_menu"
    ))
    
    return builder.as_markup()

def get_tools_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура раздела Инструменты"""
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(
        text="📖 Медитации",
        callback_data="tools_meditations"
    ))
    builder.row(InlineKeyboardButton(
        text="🎵 Аудио-практики",
        callback_data="tools_audio"
    ))
    builder.row(InlineKeyboardButton(
        text="📝 Статьи и материалы",
        callback_data="tools_articles"
    ))
    builder.row(InlineKeyboardButton(
        text="◀️ Назад",
        callback_data="main_menu"
    ))
    
    return builder.as_markup()

def get_manager_contact_keyboard(managers: list) -> InlineKeyboardMarkup:
    """Клавиатура с контактами менеджеров"""
    builder = InlineKeyboardBuilder()
    
    for manager in managers:
        builder.row(InlineKeyboardButton(
            text=f"💬 {manager.name}",
            url=f"https://t.me/{manager.telegram_username}"
        ))
    
    builder.row(InlineKeyboardButton(
        text="◀️ Назад",
        callback_data="main_menu"
    ))
    
    return builder.as_markup()
