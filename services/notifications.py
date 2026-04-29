"""
Сервис уведомлений админам Magic Vibes о новых заявках, оплатах и т.д.
"""
import logging
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Booking, Practice, PracticeSchedule, User, Payment,
    CourseEnrollment, Course, ClosedFormatRequest, Questionnaire,
)

logger = logging.getLogger(__name__)


def _client_block(user: User) -> str:
    """Красиво відображаємо контакти клієнта."""
    name = user.full_name or "(без імені)"
    handle = f"@{user.username}" if user.username else f"<a href='tg://user?id={user.telegram_id}'>відкрити чат</a>"
    phone_line = f"\n📞  {user.phone}" if user.phone else ""
    email_line = f"\n📧  {user.email}" if user.email else ""
    return f"👤  <b>{name}</b>\n💬  {handle}{phone_line}{email_line}"


def _booking_admin_kb(booking_id: int, user_telegram_id: Optional[int]) -> InlineKeyboardMarkup:
    """Кнопки для адміна по бронюванню."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"admin_confirm_booking_{booking_id}"),
        InlineKeyboardButton(text="❌ Скасувати", callback_data=f"admin_cancel_booking_{booking_id}"),
    )
    kb.row(InlineKeyboardButton(
        text="🔁 Змінити статус / деталі",
        callback_data=f"admin_open_booking_{booking_id}",
    ))
    if user_telegram_id:
        kb.row(InlineKeyboardButton(
            text="💬 Написати клієнту",
            url=f"tg://user?id={user_telegram_id}",
        ))
    return kb.as_markup()


def _course_request_admin_kb(enrollment_id: int, user_telegram_id: Optional[int]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Опрацьовано", callback_data=f"admin_course_done_{enrollment_id}"),
    )
    if user_telegram_id:
        kb.row(InlineKeyboardButton(
            text="💬 Написати клієнту",
            url=f"tg://user?id={user_telegram_id}",
        ))
    return kb.as_markup()


async def _send_to_admins(bot: Bot, admin_ids: list[int], text: str, kb: Optional[InlineKeyboardMarkup] = None):
    for admin_id in admin_ids:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=kb,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"Failed to notify admin {admin_id}: {e}")


async def notify_new_booking(bot: Bot, admin_ids: list[int], session: AsyncSession, booking_id: int):
    """Нова заявка на групову практику."""
    booking = await session.get(Booking, booking_id)
    if not booking:
        return
    practice = await session.get(Practice, booking.practice_id)
    schedule = await session.get(PracticeSchedule, booking.schedule_id)
    user = await session.get(User, booking.user_id)
    if not (practice and schedule and user):
        return

    date_str = schedule.datetime.strftime("%d.%m.%Y о %H:%M")
    text = (
        "🆕 <b>НОВА ЗАЯВКА НА ПРАКТИКУ</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"🪷  <b>Практика:</b>  {practice.title}\n"
        f"📅  <b>Дата:</b>  {date_str}\n"
        f"💰  <b>Сума:</b>  {int(practice.price)} грн\n"
        f"⏳  <b>Статус:</b>  очікує оплати\n\n"
        f"{_client_block(user)}"
    )
    await _send_to_admins(bot, admin_ids, text, _booking_admin_kb(booking.id, user.telegram_id))


async def notify_new_individual_request(bot: Bot, admin_ids: list[int], session: AsyncSession, booking_id: int):
    """Нова заявка на індивідуальну сесію."""
    booking = await session.get(Booking, booking_id)
    if not booking:
        return
    practice = await session.get(Practice, booking.practice_id)
    schedule = await session.get(PracticeSchedule, booking.schedule_id)
    user = await session.get(User, booking.user_id)
    if not (practice and schedule and user):
        return

    date_str = schedule.datetime.strftime("%d.%m.%Y о %H:%M")
    text = (
        "🆕 <b>НОВА ЗАЯВКА — ІНДИВІДУАЛЬНА СЕСІЯ</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"🧘‍♀️  <b>Послуга:</b>  {practice.title}\n"
        f"📅  <b>Бажаний час:</b>  {date_str}\n"
        f"💰  <b>Сума:</b>  {int(practice.price)} грн\n"
        f"⏳  <b>Статус:</b>  потребує підтвердження часу\n\n"
        f"{_client_block(user)}\n"
    )
    if booking.notes:
        text += f"\n📝  <b>Запит:</b>\n<i>{booking.notes}</i>"

    await _send_to_admins(bot, admin_ids, text, _booking_admin_kb(booking.id, user.telegram_id))


async def notify_new_course_request(bot: Bot, admin_ids: list[int], session: AsyncSession, enrollment_id: int):
    """Нова заявка на 3-місячне навчання (без оплати — менеджер сам контактує)."""
    enrollment = await session.get(CourseEnrollment, enrollment_id)
    if not enrollment:
        return
    course = await session.get(Course, enrollment.course_id)
    user = await session.get(User, enrollment.user_id)
    if not (course and user):
        return

    text = (
        "🆕 <b>НОВА ЗАЯВКА НА КУРС</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"📚  <b>Курс:</b>  {course.title}\n"
        f"⏱  <b>Тривалість:</b>  {course.duration_days} днів\n"
        f"💰  <b>Вартість:</b>  {int(course.price)} грн\n"
        f"⏳  <b>Статус:</b>  потребує контакту з клієнтом\n\n"
        f"{_client_block(user)}"
    )
    await _send_to_admins(bot, admin_ids, text, _course_request_admin_kb(enrollment.id, user.telegram_id))


async def notify_payment_success(bot: Bot, admin_ids: list[int], session: AsyncSession, payment_id: int):
    """Успішна оплата."""
    payment = await session.get(Payment, payment_id)
    if not payment:
        return
    user = await session.get(User, payment.user_id)
    if not user:
        return

    detail = ""
    if payment.booking_id:
        booking = await session.get(Booking, payment.booking_id)
        if booking:
            practice = await session.get(Practice, booking.practice_id)
            schedule = await session.get(PracticeSchedule, booking.schedule_id)
            if practice and schedule:
                detail = (
                    f"🪷  <b>Практика:</b>  {practice.title}\n"
                    f"📅  <b>Дата:</b>  {schedule.datetime.strftime('%d.%m.%Y о %H:%M')}\n"
                )
    elif payment.course_enrollment_id:
        enrollment = await session.get(CourseEnrollment, payment.course_enrollment_id)
        if enrollment:
            course = await session.get(Course, enrollment.course_id)
            if course:
                detail = f"📚  <b>Курс:</b>  {course.title}\n"

    text = (
        "💰 <b>ОПЛАТА УСПІШНА</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"{detail}"
        f"💳  <b>Сума:</b>  {int(payment.amount)} {payment.currency}\n\n"
        f"{_client_block(user)}"
    )
    await _send_to_admins(bot, admin_ids, text)


async def notify_new_closed_format_request(
    bot: Bot, admin_ids: list[int], session: AsyncSession, request_id: int,
):
    """Нова заявка на закритий формат."""
    request = await session.get(ClosedFormatRequest, request_id)
    if not request:
        return
    user = await session.get(User, request.user_id)
    if not user:
        return

    notes_block = f"\n\n📝  <b>Коментар:</b>\n<i>{request.notes}</i>" if request.notes else ""
    phone_block = f"\n📞  <b>Телефон:</b>  {request.contact_phone}" if request.contact_phone else ""

    text = (
        "🐘 <b>НОВА ЗАЯВКА — ЗАКРИТИЙ ФОРМАТ</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"📅  <b>Бажана дата:</b>  {request.requested_date_text}\n"
        f"👥  <b>Розмір групи:</b>  {request.group_size}{phone_block}\n\n"
        f"{_client_block(user)}"
        f"{notes_block}\n\n"
        f"/closed_{request.id} — відкрити заявку"
    )

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="🔁  Змінити статус",
        callback_data=f"admin_closed_open_{request.id}",
    ))
    if user.telegram_id:
        kb.row(InlineKeyboardButton(
            text="💬  Написати клієнту",
            url=f"tg://user?id={user.telegram_id}",
        ))

    await _send_to_admins(bot, admin_ids, text, kb.as_markup())


async def notify_anketa_filled(
    bot: Bot, admin_ids: list[int], session: AsyncSession, questionnaire_id: int,
):
    """Клієнт заповнив анкету учасника."""
    q = await session.get(Questionnaire, questionnaire_id)
    if not q:
        return
    user = await session.get(User, q.user_id)
    if not user:
        return

    text = (
        "📝 <b>АНКЕТА ЗАПОВНЕНА</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"{_client_block(user)}\n\n"
        f"/anketa_{q.id} — переглянути всі відповіді"
    )

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="👀  Подивитись відповіді",
        callback_data=f"admin_anketa_{q.id}",
    ))
    if user.telegram_id:
        kb.row(InlineKeyboardButton(
            text="💬  Написати клієнту",
            url=f"tg://user?id={user.telegram_id}",
        ))

    await _send_to_admins(bot, admin_ids, text, kb.as_markup())
