"""
Адмін-панель Magic Vibes — доступна лише користувачам з ADMIN_IDS.
"""
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command, BaseFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database.models import (
    Booking, Practice, PracticeSchedule, User, Payment,
    BookingStatus, PaymentStatus, CourseEnrollment, Course,
)


class IsAdmin(BaseFilter):
    """Фільтр: пропускає лише адмінів з config.tg_bot.admin_ids."""

    async def __call__(self, event, config) -> bool:
        user_id = event.from_user.id if event.from_user else None
        return user_id is not None and user_id in config.tg_bot.admin_ids


router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ────────────────────── Головне адмін-меню ──────────────────────

def admin_main_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📋  Заявки сьогодні", callback_data="admin_today"))
    kb.row(InlineKeyboardButton(text="📅  Найближчі практики", callback_data="admin_upcoming"))
    kb.row(InlineKeyboardButton(text="👥  Клієнти", callback_data="admin_clients"))
    kb.row(InlineKeyboardButton(text="💳  Платежі", callback_data="admin_payments"))
    kb.row(InlineKeyboardButton(text="📊  Статистика", callback_data="admin_stats"))
    kb.row(InlineKeyboardButton(text="❌  Закрити", callback_data="admin_close"))
    return kb.as_markup()


def admin_back_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️  До адмін-меню", callback_data="admin_menu"))
    return kb.as_markup()


ADMIN_HEADER = (
    "🛠 <b>АДМІН-ПАНЕЛЬ</b>\n"
    "━━━━━━━━━━━━━━━━━\n"
    "Оберіть розділ для роботи 👇"
)


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    await message.answer(ADMIN_HEADER, reply_markup=admin_main_kb(), parse_mode="HTML")


@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(callback: CallbackQuery):
    try:
        await callback.message.edit_text(ADMIN_HEADER, reply_markup=admin_main_kb(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(ADMIN_HEADER, reply_markup=admin_main_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_close")
async def cb_admin_close(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("Закрито")


# ────────────────────── 📋 Заявки сьогодні ──────────────────────

@router.callback_query(F.data == "admin_today")
async def cb_admin_today(callback: CallbackQuery, session: AsyncSession):
    """Усі бронювання за останні 24 год."""
    since = datetime.utcnow() - timedelta(hours=24)
    result = await session.execute(
        select(Booking).where(Booking.created_at >= since).order_by(Booking.created_at.desc())
    )
    bookings = result.scalars().all()

    lines = ["📋 <b>ЗАЯВКИ ЗА ОСТАННІ 24 ГОД</b>", "━━━━━━━━━━━━━━━━━", ""]

    if not bookings:
        lines.append("<i>За останні 24 години заявок не надходило.</i>")
    else:
        for b in bookings:
            practice = await session.get(Practice, b.practice_id)
            schedule = await session.get(PracticeSchedule, b.schedule_id)
            user = await session.get(User, b.user_id)

            status_emoji = {
                BookingStatus.PENDING: "⏳",
                BookingStatus.CONFIRMED: "✅",
                BookingStatus.CANCELLED: "❌",
                BookingStatus.COMPLETED: "🏁",
            }.get(b.status, "•")

            handle = f"@{user.username}" if user and user.username else (user.full_name if user else "?")
            date_str = schedule.datetime.strftime("%d.%m %H:%M") if schedule else "—"
            created = b.created_at.strftime("%d.%m %H:%M") if b.created_at else "—"

            lines.append(
                f"{status_emoji} <b>#{b.id}</b>  •  {practice.title if practice else '?'}\n"
                f"   👤 {handle}  •  📅 {date_str}\n"
                f"   <i>створено {created}</i>"
            )
            lines.append("")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=admin_back_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────── 📅 Найближчі практики ──────────────────────

@router.callback_query(F.data == "admin_upcoming")
async def cb_admin_upcoming(callback: CallbackQuery, session: AsyncSession):
    """Найближчі заняття + кількість записів на кожне."""
    now = datetime.utcnow()
    result = await session.execute(
        select(PracticeSchedule)
        .where(PracticeSchedule.datetime >= now)
        .order_by(PracticeSchedule.datetime)
        .limit(10)
    )
    schedules = result.scalars().all()

    lines = ["📅 <b>НАЙБЛИЖЧІ ЗАНЯТТЯ (ТОП-10)</b>", "━━━━━━━━━━━━━━━━━", ""]

    if not schedules:
        lines.append("<i>Розклад порожній.</i>")
    else:
        for s in schedules:
            practice = await session.get(Practice, s.practice_id)
            # Скільки реальних записів (PENDING + CONFIRMED)
            count_result = await session.execute(
                select(func.count()).select_from(Booking).where(
                    Booking.schedule_id == s.id,
                    Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
                )
            )
            booked_count = count_result.scalar() or 0
            total_slots = (practice.max_participants or s.available_slots + booked_count) if practice else "?"

            lines.append(
                f"📅  <b>{s.datetime.strftime('%d.%m.%Y %H:%M')}</b>\n"
                f"   🪷 {practice.title if practice else '?'}\n"
                f"   👥 Записано: <b>{booked_count}</b> / {total_slots}\n"
                f"   /sched_{s.id} — деталі"
            )
            lines.append("")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=admin_back_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(F.text.regexp(r"^/sched_\d+"))
async def show_schedule_details(message: Message, session: AsyncSession):
    """Показати хто записаний на конкретне заняття: /sched_<id>"""
    try:
        schedule_id = int(message.text.split("_", 1)[1].split()[0])
    except Exception:
        await message.answer("Невірний формат. Використовуйте /sched_<id>")
        return

    schedule = await session.get(PracticeSchedule, schedule_id)
    if not schedule:
        await message.answer("Заняття не знайдено")
        return

    practice = await session.get(Practice, schedule.practice_id)
    result = await session.execute(
        select(Booking).where(
            Booking.schedule_id == schedule_id,
            Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
        ).order_by(Booking.created_at)
    )
    bookings = result.scalars().all()

    lines = [
        f"📅 <b>{practice.title if practice else '?'}</b>",
        f"<b>{schedule.datetime.strftime('%d.%m.%Y %H:%M')}</b>",
        "━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not bookings:
        lines.append("<i>Поки що ніхто не записаний.</i>")
    else:
        for b in bookings:
            user = await session.get(User, b.user_id)
            status_emoji = "✅" if b.status == BookingStatus.CONFIRMED else "⏳"
            handle = f"@{user.username}" if user and user.username else (user.full_name if user else "?")
            lines.append(f"{status_emoji} {handle}  •  заявка #{b.id}")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=admin_back_kb())


# ────────────────────── 👥 Клієнти ──────────────────────

@router.callback_query(F.data == "admin_clients")
async def cb_admin_clients(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(User).order_by(User.created_at.desc()).limit(30)
    )
    users = result.scalars().all()

    total_result = await session.execute(select(func.count()).select_from(User))
    total = total_result.scalar() or 0

    lines = [
        f"👥 <b>КЛІЄНТИ</b>  (всього: {total})",
        "━━━━━━━━━━━━━━━━━",
        "Останні 30:",
        "",
    ]

    if not users:
        lines.append("<i>Користувачів ще немає.</i>")
    else:
        for u in users:
            handle = f"@{u.username}" if u.username else "—"
            created = u.created_at.strftime("%d.%m") if u.created_at else "—"
            lines.append(f"• {u.full_name or '(без імені)'}  •  {handle}  •  <i>{created}</i>")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=admin_back_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────── 💳 Платежі ──────────────────────

@router.callback_query(F.data == "admin_payments")
async def cb_admin_payments(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(Payment).order_by(Payment.created_at.desc()).limit(20)
    )
    payments = result.scalars().all()

    lines = ["💳 <b>ОСТАННІ ПЛАТЕЖІ</b>", "━━━━━━━━━━━━━━━━━", ""]

    if not payments:
        lines.append("<i>Платежів ще немає.</i>")
    else:
        for p in payments:
            user = await session.get(User, p.user_id)
            handle = f"@{user.username}" if user and user.username else (user.full_name if user else "?")
            status_emoji = {
                PaymentStatus.SUCCESS: "✅",
                PaymentStatus.PENDING: "⏳",
                PaymentStatus.FAILED: "❌",
                PaymentStatus.REFUNDED: "↩️",
            }.get(p.status, "•")
            created = p.created_at.strftime("%d.%m %H:%M") if p.created_at else "—"
            lines.append(
                f"{status_emoji} <b>#{p.id}</b>  •  {int(p.amount)} {p.currency}  •  {handle}  •  <i>{created}</i>"
            )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=admin_back_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────── 📊 Статистика ──────────────────────

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery, session: AsyncSession):
    week_ago = datetime.utcnow() - timedelta(days=7)
    month_ago = datetime.utcnow() - timedelta(days=30)

    users_total = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
    users_week = (await session.execute(
        select(func.count()).select_from(User).where(User.created_at >= week_ago)
    )).scalar() or 0

    bookings_week = (await session.execute(
        select(func.count()).select_from(Booking).where(Booking.created_at >= week_ago)
    )).scalar() or 0
    bookings_confirmed_week = (await session.execute(
        select(func.count()).select_from(Booking).where(
            Booking.created_at >= week_ago,
            Booking.status == BookingStatus.CONFIRMED,
        )
    )).scalar() or 0

    revenue_month = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.SUCCESS,
            Payment.created_at >= month_ago,
        )
    )).scalar() or 0

    text = (
        "📊 <b>СТАТИСТИКА</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "<b>Клієнти:</b>\n"
        f"   • всього: <b>{users_total}</b>\n"
        f"   • нових за 7 днів: <b>+{users_week}</b>\n\n"
        "<b>Бронювання за 7 днів:</b>\n"
        f"   • створено: <b>{bookings_week}</b>\n"
        f"   • підтверджено: <b>{bookings_confirmed_week}</b>\n\n"
        "<b>Виручка за 30 днів:</b>\n"
        f"   💰  <b>{int(revenue_month)} грн</b>"
    )

    await callback.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode="HTML")
    await callback.answer()


# ────────────────────── Дії над бронюваннями (з push-уведомлень) ──────────────────────

@router.callback_query(F.data.startswith("admin_confirm_booking_"))
async def cb_admin_confirm_booking(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    booking_id = int(callback.data.replace("admin_confirm_booking_", ""))
    booking = await session.get(Booking, booking_id)
    if not booking:
        await callback.answer("Бронювання не знайдено", show_alert=True)
        return

    booking.status = BookingStatus.CONFIRMED
    await session.commit()

    # Сповіщаємо клієнта
    user = await session.get(User, booking.user_id)
    practice = await session.get(Practice, booking.practice_id)
    schedule = await session.get(PracticeSchedule, booking.schedule_id)

    if user and practice and schedule:
        try:
            date_str = schedule.datetime.strftime("%d.%m.%Y о %H:%M")
            await bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    "✅ <b>Вашу заявку підтверджено!</b>\n\n"
                    f"🪷  <b>{practice.title}</b>\n"
                    f"📅  {date_str}\n"
                    f"📍  Київ, вул. Рейтарська, 13\n\n"
                    "Чекаємо на вас 🤍"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

    # Оновити повідомлення адміна
    try:
        await callback.message.edit_text(
            callback.message.html_text + "\n\n✅ <b>Підтверджено</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer("Підтверджено")


@router.callback_query(F.data.startswith("admin_cancel_booking_"))
async def cb_admin_cancel_booking(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    booking_id = int(callback.data.replace("admin_cancel_booking_", ""))
    booking = await session.get(Booking, booking_id)
    if not booking:
        await callback.answer("Бронювання не знайдено", show_alert=True)
        return

    booking.status = BookingStatus.CANCELLED
    schedule = await session.get(PracticeSchedule, booking.schedule_id)
    if schedule:
        schedule.available_slots += 1
        schedule.is_available = True
    await session.commit()

    user = await session.get(User, booking.user_id)
    practice = await session.get(Practice, booking.practice_id)

    if user and practice:
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    "❌ <b>Вашу заявку скасовано</b>\n\n"
                    f"🪷  {practice.title}\n\n"
                    "Якщо це помилка — звʼяжіться з менеджером 💬"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

    try:
        await callback.message.edit_text(
            callback.message.html_text + "\n\n❌ <b>Скасовано</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer("Скасовано")


@router.callback_query(F.data.startswith("admin_course_done_"))
async def cb_admin_course_done(callback: CallbackQuery, session: AsyncSession):
    enrollment_id = int(callback.data.replace("admin_course_done_", ""))
    enrollment = await session.get(CourseEnrollment, enrollment_id)
    if not enrollment:
        await callback.answer("Заявку не знайдено", show_alert=True)
        return
    enrollment.is_active = True
    await session.commit()

    try:
        await callback.message.edit_text(
            callback.message.html_text + "\n\n✅ <b>Опрацьовано</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer("Позначено як опрацьовано")
