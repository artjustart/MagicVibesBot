"""
Клавіатури для бота Magic Vibes
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_menu() -> InlineKeyboardMarkup:
    """Головне меню бота"""
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(
        text="🪷  Групові практики",
        callback_data="practices_list"
    ))
    builder.row(InlineKeyboardButton(
        text="🐘  Закритий формат для груп",
        callback_data="closed_format"
    ))
    builder.row(InlineKeyboardButton(
        text="🧘‍♀️  Індивідуальна практика",
        callback_data="individual_session"
    ))
    builder.row(InlineKeyboardButton(
        text="🌀  Тримісячний курс",
        callback_data="three_month_course"
    ))
    builder.row(InlineKeyboardButton(
        text="📍  Локація",
        callback_data="locations"
    ))
    builder.row(InlineKeyboardButton(
        text="📝  Анкета учасника",
        callback_data="start_questionnaire"
    ))
    builder.row(InlineKeyboardButton(
        text="💳  Сплатити за реквізитами",
        callback_data="pay_by_requisites"
    ))
    builder.row(InlineKeyboardButton(
        text="🎧  Інструменти для саунд-хілінгу",
        callback_data="tools"
    ))
    builder.row(InlineKeyboardButton(
        text="💬  Питання адміністратору",
        callback_data="contact_manager"
    ))

    return builder.as_markup()


def get_back_to_main_menu() -> InlineKeyboardMarkup:
    """Кнопка повернення до головного меню"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="◀️  До головного меню",
        callback_data="main_menu"
    ))
    return builder.as_markup()


def get_practices_keyboard(practices: list) -> InlineKeyboardMarkup:
    """Список актуальних практик"""
    builder = InlineKeyboardBuilder()

    for practice in practices:
        builder.row(InlineKeyboardButton(
            text=f"✨  {practice.title}  •  {int(practice.price)} грн",
            callback_data=f"practice_{practice.id}"
        ))

    builder.row(InlineKeyboardButton(
        text="◀️  Назад",
        callback_data="main_menu"
    ))

    return builder.as_markup()


def get_practice_schedule_keyboard(schedules: list, practice_id: int) -> InlineKeyboardMarkup:
    """Розклад практики"""
    builder = InlineKeyboardBuilder()

    for schedule in schedules:
        date_str = schedule.datetime.strftime("%d.%m  •  %H:%M")
        slots_text = f"  •  залишилось {schedule.available_slots}" if schedule.available_slots else ""

        builder.row(InlineKeyboardButton(
            text=f"📅  {date_str}{slots_text}",
            callback_data=f"book_{schedule.id}"
        ))

    builder.row(InlineKeyboardButton(
        text="◀️  До списку практик",
        callback_data="practices_list"
    ))

    return builder.as_markup()


def get_booking_confirmation_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Підтвердження бронювання"""
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(
        text="✅  Підтвердити та сплатити",
        callback_data=f"confirm_booking_{booking_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="❌  Скасувати",
        callback_data=f"cancel_booking_{booking_id}"
    ))

    return builder.as_markup()


def get_payment_keyboard(payment_url: str, payment_id: int) -> InlineKeyboardMarkup:
    """Клавіатура оплати"""
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(
        text="💳  Перейти до оплати",
        url=payment_url
    ))
    builder.row(InlineKeyboardButton(
        text="✅  Я сплатив(ла)",
        callback_data=f"check_payment_{payment_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="◀️  До меню",
        callback_data="main_menu"
    ))

    return builder.as_markup()


def get_individual_session_keyboard() -> InlineKeyboardMarkup:
    """Клавіатура індивідуальної сесії"""
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(
        text="📅  Обрати дату й час",
        callback_data="individual_choose_datetime"
    ))
    builder.row(InlineKeyboardButton(
        text="💬  Написати менеджеру",
        callback_data="contact_manager"
    ))
    builder.row(InlineKeyboardButton(
        text="◀️  Назад",
        callback_data="main_menu"
    ))

    return builder.as_markup()


def get_courses_keyboard(courses: list) -> InlineKeyboardMarkup:
    """Список курсів"""
    builder = InlineKeyboardBuilder()

    for course in courses:
        builder.row(InlineKeyboardButton(
            text=f"🎓  {course.title}  •  {int(course.price)} грн",
            callback_data=f"course_{course.id}"
        ))

    builder.row(InlineKeyboardButton(
        text="◀️  Назад",
        callback_data="main_menu"
    ))

    return builder.as_markup()


def get_three_month_request_keyboard() -> InlineKeyboardMarkup:
    """Заявка на 3-місячне навчання (без оплати — менеджер сам зв'яжеться)."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="✨   ЗАЛИШИТИ ЗАЯВКУ   ✨",
        callback_data="request_three_month",
    ))
    builder.row(InlineKeyboardButton(
        text="◀️  До головного меню",
        callback_data="main_menu",
    ))
    return builder.as_markup()


def get_course_enrollment_keyboard(course_id: int) -> InlineKeyboardMarkup:
    """Запис на курс"""
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(
        text="✅  Записатися на курс",
        callback_data=f"enroll_course_{course_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="ℹ️  Детальніше",
        callback_data=f"course_details_{course_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="◀️  До головного меню",
        callback_data="main_menu"
    ))

    return builder.as_markup()


def get_tools_keyboard() -> InlineKeyboardMarkup:
    """Клавіатура розділу Інструменти"""
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(
        text="📖  Медитації",
        callback_data="tools_meditations"
    ))
    builder.row(InlineKeyboardButton(
        text="🎵  Аудіо-практики",
        callback_data="tools_audio"
    ))
    builder.row(InlineKeyboardButton(
        text="📝  Статті та матеріали",
        callback_data="tools_articles"
    ))
    builder.row(InlineKeyboardButton(
        text="◀️  Назад",
        callback_data="main_menu"
    ))

    return builder.as_markup()


def get_manager_contact_keyboard(managers: list) -> InlineKeyboardMarkup:
    """Контакти менеджерів"""
    builder = InlineKeyboardBuilder()

    for manager in managers:
        builder.row(InlineKeyboardButton(
            text=f"💬  Написати — {manager.name}",
            url=f"https://t.me/{manager.telegram_username}"
        ))

    builder.row(InlineKeyboardButton(
        text="◀️  Назад",
        callback_data="main_menu"
    ))

    return builder.as_markup()
