"""
Адмін-панель Magic Vibes — доступна лише користувачам з ADMIN_IDS.
"""
import asyncio
import gzip
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    BufferedInputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete as sa_delete

import json

from database.models import (
    Booking, Practice, PracticeSchedule, User, Payment,
    BookingStatus, PaymentStatus, PracticeType, CourseEnrollment, Course,
    Location, ClosedFormatRequest, ClosedFormatStatus, Questionnaire,
)
from content.texts import ANKETA_QUESTIONS


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
    kb.row(InlineKeyboardButton(text="🪷  Керування практиками", callback_data="admin_practices"))
    kb.row(InlineKeyboardButton(text="🐘  Закриті заявки", callback_data="admin_closed"))
    kb.row(InlineKeyboardButton(text="📝  Анкети", callback_data="admin_anketas"))
    kb.row(InlineKeyboardButton(text="📍  Локації та відео", callback_data="admin_locations"))
    kb.row(InlineKeyboardButton(text="👥  Клієнти", callback_data="admin_clients"))
    kb.row(InlineKeyboardButton(text="💳  Платежі", callback_data="admin_payments"))
    kb.row(InlineKeyboardButton(text="📊  Статистика", callback_data="admin_stats"))
    kb.row(InlineKeyboardButton(text="❌  Закрити", callback_data="admin_close"))
    return kb.as_markup()


# FSM-стани для майстрів створення/редагування
class AdminStates(StatesGroup):
    new_practice_title = State()
    new_practice_description = State()
    new_practice_price = State()
    new_practice_duration = State()
    new_practice_max = State()

    edit_field_value = State()  # очікуємо нове значення для поля
    add_schedule_datetime = State()
    location_upload_video = State()  # очікуємо відео для локації


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


BACKUPS_DIR = Path("/opt/magic_vibes_bot/backups")


@router.message(Command("backup"))
async def cmd_backup(message: Message, config):
    """Команда /backup — дамп БД через pg_dump, зберегти на VPS і надіслати .sql.gz."""
    await message.answer("⏳ Створюю бекап...")

    db = config.db
    cmd = [
        "pg_dump",
        "-h", db.host,
        "-p", str(db.port),
        "-U", db.user,
        "-d", db.name,
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
    ]
    env = {**os.environ, "PGPASSWORD": db.password}

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()
    except FileNotFoundError:
        await message.answer(
            "❌ <b>pg_dump не знайдено</b>\n\n"
            "Встановіть на VPS: <code>apt install -y postgresql-client</code>",
            parse_mode="HTML",
        )
        return

    if proc.returncode != 0:
        err = (stderr or b"").decode("utf-8", errors="replace")[:1500]
        await message.answer(
            f"❌ <b>pg_dump failed</b> (rc={proc.returncode})\n\n<pre>{err}</pre>",
            parse_mode="HTML",
        )
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"magic_vibes_bot_{timestamp}.sql.gz"
    compressed = gzip.compress(stdout, compresslevel=6)

    # Зберігаємо локальну копію на VPS
    try:
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        local_path = BACKUPS_DIR / filename
        local_path.write_bytes(compressed)
        local_note = f"\n📂  Збережено на VPS:\n<code>{local_path}</code>"
    except Exception as e:
        local_note = f"\n⚠️  Не вдалось зберегти на VPS: {e}"

    raw_kb = f"{len(stdout) / 1024:.1f}"
    gz_kb = f"{len(compressed) / 1024:.1f}"

    caption = (
        "💾 <b>Бекап БД Magic Vibes</b>\n"
        f"🕒  {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
        f"📦  SQL: {raw_kb} КБ → стиснуто: {gz_kb} КБ"
        f"{local_note}\n\n"
        "<i>Збережіть файл локально — це повний дамп бази,\n"
        "який можна відновити через psql.</i>"
    )

    await message.bot.send_document(
        chat_id=message.from_user.id,
        document=BufferedInputFile(compressed, filename=filename),
        caption=caption,
        parse_mode="HTML",
    )


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


# ────────────────────── Зміна статусу бронювання ──────────────────────

STATUS_CYCLE = [
    (BookingStatus.PENDING, "⏳ Очікує оплати"),
    (BookingStatus.CONFIRMED, "✅ Підтверджено"),
    (BookingStatus.COMPLETED, "🏁 Завершено"),
    (BookingStatus.CANCELLED, "❌ Скасовано"),
]


@router.callback_query(F.data.startswith("admin_setstatus_"))
async def cb_admin_set_status(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Встановлення статусу бронювання: admin_setstatus_<booking_id>_<status>"""
    try:
        _, _, booking_id_s, status_s = callback.data.split("_", 3)
        booking_id = int(booking_id_s)
        new_status = BookingStatus(status_s)
    except Exception:
        await callback.answer("Невірна команда", show_alert=True)
        return

    booking = await session.get(Booking, booking_id)
    if not booking:
        await callback.answer("Бронювання не знайдено", show_alert=True)
        return

    old_status = booking.status
    booking.status = new_status

    # Якщо скасовуємо — повертаємо місце; якщо було скасовано і відновлюємо — забираємо
    schedule = await session.get(PracticeSchedule, booking.schedule_id)
    if schedule:
        if old_status != BookingStatus.CANCELLED and new_status == BookingStatus.CANCELLED:
            schedule.available_slots += 1
            schedule.is_available = True
        elif old_status == BookingStatus.CANCELLED and new_status != BookingStatus.CANCELLED:
            if schedule.available_slots > 0:
                schedule.available_slots -= 1
            if schedule.available_slots == 0:
                schedule.is_available = False

    await session.commit()

    # Сповіщаємо клієнта
    user = await session.get(User, booking.user_id)
    practice = await session.get(Practice, booking.practice_id)
    if user and practice:
        client_messages = {
            BookingStatus.CONFIRMED: f"✅ Вашу заявку на «{practice.title}» підтверджено! 🤍",
            BookingStatus.CANCELLED: f"❌ Вашу заявку на «{practice.title}» скасовано. Якщо це помилка — звʼяжіться з менеджером.",
            BookingStatus.COMPLETED: f"🏁 Дякуємо що відвідали «{practice.title}»! 💫",
        }
        msg = client_messages.get(new_status)
        if msg:
            try:
                await bot.send_message(user.telegram_id, msg, parse_mode="HTML")
            except Exception:
                pass

    status_label = dict(STATUS_CYCLE).get(new_status, str(new_status))
    await callback.answer(f"Статус: {status_label}")
    # Оновити повідомлення-карту бронювання
    await _send_booking_card(bot, callback.message.chat.id, session, booking_id, edit_message=callback.message)


def _booking_status_kb(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for status, label in STATUS_CYCLE:
        kb.row(InlineKeyboardButton(
            text=f"{label}",
            callback_data=f"admin_setstatus_{booking_id}_{status.value}",
        ))
    kb.row(InlineKeyboardButton(text="◀️ Закрити", callback_data="admin_close"))
    return kb.as_markup()


async def _send_booking_card(bot: Bot, chat_id: int, session: AsyncSession, booking_id: int, edit_message: Message = None):
    booking = await session.get(Booking, booking_id)
    if not booking:
        return
    practice = await session.get(Practice, booking.practice_id)
    schedule = await session.get(PracticeSchedule, booking.schedule_id)
    user = await session.get(User, booking.user_id)

    status_label = dict(STATUS_CYCLE).get(booking.status, str(booking.status))
    handle = f"@{user.username}" if user and user.username else (user.full_name if user else "?")
    date_str = schedule.datetime.strftime("%d.%m.%Y о %H:%M") if schedule else "—"

    text = (
        f"📋 <b>Бронювання #{booking.id}</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"🪷  <b>{practice.title if practice else '?'}</b>\n"
        f"📅  {date_str}\n"
        f"💰  {int(practice.price) if practice else 0} грн\n"
        f"👤  {handle}\n\n"
        f"<b>Поточний статус:</b>  {status_label}\n\n"
        "👇 Оберіть новий статус:"
    )

    kb = _booking_status_kb(booking.id)
    if edit_message:
        try:
            await edit_message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text.regexp(r"^/booking_\d+"))
async def cmd_booking(message: Message, session: AsyncSession, bot: Bot):
    """Деталі бронювання: /booking_<id>"""
    try:
        booking_id = int(message.text.split("_", 1)[1].split()[0])
    except Exception:
        await message.answer("Невірний формат. /booking_<id>")
        return
    await _send_booking_card(bot, message.chat.id, session, booking_id)


@router.callback_query(F.data.startswith("admin_open_booking_"))
async def cb_admin_open_booking(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Відкрити повну картку бронювання зі статусами."""
    try:
        booking_id = int(callback.data.replace("admin_open_booking_", ""))
    except Exception:
        await callback.answer("Невірна команда", show_alert=True)
        return
    await _send_booking_card(bot, callback.message.chat.id, session, booking_id)
    await callback.answer()


# ────────────────────── 🪷 Керування практиками ──────────────────────

def _practices_admin_kb(practices: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in practices:
        emoji = "🟢" if p.is_active else "⚪️"
        kb.row(InlineKeyboardButton(
            text=f"{emoji}  {p.title}",
            callback_data=f"admin_p_{p.id}",
        ))
    kb.row(InlineKeyboardButton(text="➕  Створити нову практику", callback_data="admin_p_new"))
    kb.row(InlineKeyboardButton(text="◀️  До адмін-меню", callback_data="admin_menu"))
    return kb.as_markup()


@router.callback_query(F.data == "admin_practices")
async def cb_admin_practices(callback: CallbackQuery, session: AsyncSession):
    """Список НЕархівних практик."""
    result = await session.execute(
        select(Practice).where(Practice.is_archived == False)
        .order_by(Practice.is_active.desc(), Practice.id)
    )
    practices = result.scalars().all()

    archived_count = (await session.execute(
        select(func.count()).select_from(Practice).where(Practice.is_archived == True)
    )).scalar() or 0

    kb = InlineKeyboardBuilder()
    for p in practices:
        emoji = "🟢" if p.is_active else "⚪️"
        kb.row(InlineKeyboardButton(
            text=f"{emoji}  {p.title}",
            callback_data=f"admin_p_{p.id}",
        ))
    kb.row(InlineKeyboardButton(text="➕  Створити нову практику", callback_data="admin_p_new"))
    kb.row(InlineKeyboardButton(
        text=f"📦  Архів  ({archived_count})",
        callback_data="admin_archive",
    ))
    kb.row(InlineKeyboardButton(text="◀️  До адмін-меню", callback_data="admin_menu"))

    text = (
        "🪷 <b>КЕРУВАННЯ ПРАКТИКАМИ</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🟢 = активна  •  ⚪️ = неактивна\n"
        "👇 Оберіть практику або створіть нову:"
    )
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


def _practice_card_kb(practice: Practice) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📅  Розклад", callback_data=f"admin_p_sched_{practice.id}"))
    kb.row(InlineKeyboardButton(text="➕  Додати дату", callback_data=f"admin_p_addsched_{practice.id}"))
    kb.row(
        InlineKeyboardButton(text="✏️ Назва", callback_data=f"admin_p_edit_{practice.id}_title"),
        InlineKeyboardButton(text="✏️ Опис", callback_data=f"admin_p_edit_{practice.id}_description"),
    )
    kb.row(InlineKeyboardButton(
        text="✏️  Деталі (довгий опис «Детальніше»)",
        callback_data=f"admin_p_edit_{practice.id}_details",
    ))
    kb.row(
        InlineKeyboardButton(text="✏️ Ціна", callback_data=f"admin_p_edit_{practice.id}_price"),
        InlineKeyboardButton(text="✏️ Тривалість", callback_data=f"admin_p_edit_{practice.id}_duration_minutes"),
    )
    kb.row(InlineKeyboardButton(text="✏️  Макс. учасників", callback_data=f"admin_p_edit_{practice.id}_max_participants"))
    kb.row(InlineKeyboardButton(text="📍  Локація практики", callback_data=f"admin_p_loc_{practice.id}"))
    toggle = "⚪️ Деактивувати" if practice.is_active else "🟢 Активувати"
    kb.row(InlineKeyboardButton(text=toggle, callback_data=f"admin_p_toggle_{practice.id}"))
    kb.row(InlineKeyboardButton(text="📦  Архівувати", callback_data=f"admin_p_archive_{practice.id}"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_practices"))
    return kb.as_markup()


def _format_practice_card(practice: Practice, location: Optional[Location] = None) -> str:
    state = "🟢 активна" if practice.is_active else "⚪️ неактивна"
    desc_preview = (practice.description or "")[:200]
    if len(practice.description or "") > 200:
        desc_preview += "..."
    loc_line = f"📍  <b>Локація:</b>  {location.title}" if location else "📍  <b>Локація:</b>  <i>не вказана</i>"
    return (
        f"🪷 <b>{practice.title}</b>  ({state})\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Опис (превʼю):</b>\n<i>{desc_preview}</i>\n\n"
        f"💰  <b>Ціна:</b>  {int(practice.price)} грн\n"
        f"⏱  <b>Тривалість:</b>  {practice.duration_minutes} хв\n"
        f"👥  <b>Макс. учасників:</b>  {practice.max_participants or '—'}\n"
        f"{loc_line}\n"
        f"🏷  <b>Тип:</b>  {practice.practice_type.value}"
    )


@router.callback_query(F.data.regexp(r"^admin_p_\d+$"))
async def cb_admin_practice_card(callback: CallbackQuery, session: AsyncSession):
    practice_id = int(callback.data.replace("admin_p_", ""))
    practice = await session.get(Practice, practice_id)
    if not practice:
        await callback.answer("Не знайдено", show_alert=True)
        return
    location = await session.get(Location, practice.location_id) if practice.location_id else None
    await callback.message.edit_text(
        _format_practice_card(practice, location),
        reply_markup=_practice_card_kb(practice),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_p_archive_"))
async def cb_admin_practice_archive(callback: CallbackQuery, session: AsyncSession):
    """Архівувати практику — приховує від клієнтів, дані зберігаються."""
    practice_id = int(callback.data.replace("admin_p_archive_", ""))
    practice = await session.get(Practice, practice_id)
    if not practice:
        await callback.answer("Не знайдено", show_alert=True)
        return

    practice.is_archived = True
    practice.is_active = False  # щоб точно не показувалась
    await session.commit()

    await callback.answer(f"📦 Архівовано: {practice.title}", show_alert=True)
    callback.data = "admin_practices"
    await cb_admin_practices(callback, session)


# ───────── Архів ─────────

@router.callback_query(F.data == "admin_archive")
async def cb_admin_archive_list(callback: CallbackQuery, session: AsyncSession):
    """Список архівних практик."""
    result = await session.execute(
        select(Practice).where(Practice.is_archived == True).order_by(Practice.id)
    )
    practices = result.scalars().all()

    kb = InlineKeyboardBuilder()
    if not practices:
        text = (
            "📦 <b>АРХІВ</b>\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "<i>Архів порожній.</i>"
        )
    else:
        lines = ["📦 <b>АРХІВ ПРАКТИК</b>", "━━━━━━━━━━━━━━━━━", ""]
        for p in practices:
            lines.append(f"📦  <b>{p.title}</b>")
            kb.row(InlineKeyboardButton(
                text=f"📦  {p.title}",
                callback_data=f"admin_arch_{p.id}",
            ))
        text = "\n".join(lines)

    kb.row(InlineKeyboardButton(text="◀️  До списку практик", callback_data="admin_practices"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


def _archived_practice_kb(practice_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="♻️  Розархівувати",
        callback_data=f"admin_unarch_{practice_id}",
    ))
    kb.row(InlineKeyboardButton(
        text="🗑  Видалити назавжди",
        callback_data=f"admin_p_del_{practice_id}",
    ))
    kb.row(InlineKeyboardButton(text="◀️  До архіву", callback_data="admin_archive"))
    return kb.as_markup()


@router.callback_query(F.data.regexp(r"^admin_arch_\d+$"))
async def cb_admin_archived_practice(callback: CallbackQuery, session: AsyncSession):
    practice_id = int(callback.data.replace("admin_arch_", ""))
    practice = await session.get(Practice, practice_id)
    if not practice:
        await callback.answer("Не знайдено", show_alert=True)
        return

    sched_count = (await session.execute(
        select(func.count()).select_from(PracticeSchedule).where(
            PracticeSchedule.practice_id == practice_id
        )
    )).scalar() or 0
    booking_count = (await session.execute(
        select(func.count()).select_from(Booking).where(
            Booking.practice_id == practice_id
        )
    )).scalar() or 0

    text = (
        f"📦 <b>{practice.title}</b>\n"
        "<i>в архіві</i>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"💰  <b>Ціна:</b>  {int(practice.price)} грн\n"
        f"⏱  <b>Тривалість:</b>  {practice.duration_minutes} хв\n"
        f"📅  <b>Дат розкладу:</b>  {sched_count}\n"
        f"📋  <b>Бронювань:</b>  {booking_count}\n\n"
        "♻️  Розархівуйте щоб повернути практику в активні.\n"
        "🗑  Або видаліть назавжди (з усіма бронюваннями і платежами)."
    )
    await callback.message.edit_text(
        text, reply_markup=_archived_practice_kb(practice_id), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_unarch_"))
async def cb_admin_unarchive(callback: CallbackQuery, session: AsyncSession):
    practice_id = int(callback.data.replace("admin_unarch_", ""))
    practice = await session.get(Practice, practice_id)
    if not practice:
        await callback.answer("Не знайдено", show_alert=True)
        return
    practice.is_archived = False
    practice.is_active = True
    await session.commit()
    await callback.answer(f"♻️ Розархівовано: {practice.title}", show_alert=True)
    callback.data = "admin_practices"
    await cb_admin_practices(callback, session)


@router.callback_query(F.data.startswith("admin_p_del_"))
async def cb_admin_practice_delete_warn(callback: CallbackQuery, session: AsyncSession):
    """Видалення з архіву — попередження + підтвердження."""
    practice_id = int(callback.data.replace("admin_p_del_", ""))
    practice = await session.get(Practice, practice_id)
    if not practice:
        await callback.answer("Не знайдено", show_alert=True)
        return

    sched_count = (await session.execute(
        select(func.count()).select_from(PracticeSchedule).where(
            PracticeSchedule.practice_id == practice_id
        )
    )).scalar() or 0
    booking_count = (await session.execute(
        select(func.count()).select_from(Booking).where(
            Booking.practice_id == practice_id
        )
    )).scalar() or 0

    text = (
        "🗑 <b>ВИДАЛЕННЯ НАЗАВЖДИ</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"<b>{practice.title}</b>\n\n"
        "⚠️  Буде видалено <b>повністю</b>:\n"
        f"• сама практика\n"
        f"• {sched_count} дат розкладу\n"
        f"• {booking_count} бронювань і повʼязаних платежів\n\n"
        "<i>Цю дію неможливо відмінити.</i>"
    )

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="✅  Так, видалити назавжди",
        callback_data=f"admin_p_delconfirm_{practice_id}",
    ))
    kb.row(InlineKeyboardButton(text="◀️  Скасувати", callback_data=f"admin_arch_{practice_id}"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_p_delconfirm_"))
async def cb_admin_practice_delete_confirm(callback: CallbackQuery, session: AsyncSession):
    """Реальне видалення з каскадом по FK."""
    practice_id = int(callback.data.replace("admin_p_delconfirm_", ""))
    practice = await session.get(Practice, practice_id)
    if not practice:
        await callback.answer("Не знайдено", show_alert=True)
        return

    title = practice.title

    bookings_result = await session.execute(
        select(Booking.id).where(Booking.practice_id == practice_id)
    )
    booking_ids = [row[0] for row in bookings_result.all()]

    if booking_ids:
        await session.execute(
            sa_delete(Payment).where(Payment.booking_id.in_(booking_ids))
        )
        await session.execute(
            sa_delete(Booking).where(Booking.id.in_(booking_ids))
        )
    await session.execute(
        sa_delete(PracticeSchedule).where(PracticeSchedule.practice_id == practice_id)
    )
    await session.execute(
        sa_delete(Practice).where(Practice.id == practice_id)
    )
    await session.commit()

    await callback.answer(f"🗑 Видалено: {title}", show_alert=True)
    callback.data = "admin_archive"
    await cb_admin_archive_list(callback, session)


@router.callback_query(F.data.startswith("admin_p_loc_"))
async def cb_admin_practice_location_pick(callback: CallbackQuery, session: AsyncSession):
    """Показати список активних локацій для привʼязки до практики."""
    practice_id = int(callback.data.replace("admin_p_loc_", ""))
    practice = await session.get(Practice, practice_id)
    if not practice:
        await callback.answer("Не знайдено", show_alert=True)
        return

    locations_result = await session.execute(
        select(Location).where(Location.is_active == True)
        .order_by(Location.sort_order, Location.id)
    )
    locations = locations_result.scalars().all()

    kb = InlineKeyboardBuilder()
    for loc in locations:
        mark = "✅ " if practice.location_id == loc.id else ""
        kb.row(InlineKeyboardButton(
            text=f"{mark}📍  {loc.title}",
            callback_data=f"admin_p_setloc_{practice_id}_{loc.id}",
        ))
    if practice.location_id:
        kb.row(InlineKeyboardButton(
            text="🚫  Зняти привʼязку",
            callback_data=f"admin_p_setloc_{practice_id}_0",
        ))
    kb.row(InlineKeyboardButton(text="◀️  Назад", callback_data=f"admin_p_{practice_id}"))

    text = (
        f"📍 <b>Локація для:</b>  {practice.title}\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "Оберіть локацію — її буде показано клієнтам по кнопці\n"
        "<b>«📍 Як нас знайти»</b> у картці практики."
    )
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_p_setloc_"))
async def cb_admin_practice_set_location(callback: CallbackQuery, session: AsyncSession):
    """admin_p_setloc_<practice_id>_<location_id> (location_id=0 → unset)."""
    suffix = callback.data.replace("admin_p_setloc_", "")
    try:
        practice_id_s, location_id_s = suffix.rsplit("_", 1)
        practice_id = int(practice_id_s)
        location_id = int(location_id_s)
    except Exception:
        await callback.answer("Невірна команда", show_alert=True)
        return

    practice = await session.get(Practice, practice_id)
    if not practice:
        await callback.answer("Не знайдено", show_alert=True)
        return

    practice.location_id = location_id if location_id > 0 else None
    await session.commit()

    if location_id > 0:
        loc = await session.get(Location, location_id)
        await callback.answer(f"📍 {loc.title if loc else 'OK'}")
    else:
        await callback.answer("🚫 Привʼязку знято")

    callback.data = f"admin_p_{practice_id}"
    await cb_admin_practice_card(callback, session)


@router.callback_query(F.data.startswith("admin_p_toggle_"))
async def cb_admin_practice_toggle(callback: CallbackQuery, session: AsyncSession):
    practice_id = int(callback.data.replace("admin_p_toggle_", ""))
    practice = await session.get(Practice, practice_id)
    if not practice:
        await callback.answer("Не знайдено", show_alert=True)
        return
    practice.is_active = not practice.is_active
    await session.commit()
    await callback.answer("Активовано" if practice.is_active else "Деактивовано")
    await callback.message.edit_text(
        _format_practice_card(practice),
        reply_markup=_practice_card_kb(practice),
        parse_mode="HTML",
    )


# ── Розклад практики (адмін)

@router.callback_query(F.data.startswith("admin_p_sched_"))
async def cb_admin_practice_schedule(callback: CallbackQuery, session: AsyncSession):
    practice_id = int(callback.data.replace("admin_p_sched_", ""))
    practice = await session.get(Practice, practice_id)
    if not practice:
        await callback.answer("Не знайдено", show_alert=True)
        return

    result = await session.execute(
        select(PracticeSchedule).where(
            PracticeSchedule.practice_id == practice_id,
        ).order_by(PracticeSchedule.datetime)
    )
    schedules = result.scalars().all()

    lines = [f"📅 <b>Розклад: {practice.title}</b>", "━━━━━━━━━━━━━━━━━", ""]
    kb = InlineKeyboardBuilder()

    if not schedules:
        lines.append("<i>Поки немає жодної дати.</i>")
    else:
        for s in schedules:
            past = "🕓 " if s.datetime < datetime.utcnow() else ""
            lines.append(
                f"{past}<b>{s.datetime.strftime('%d.%m.%Y %H:%M')}</b>  •  залишилось {s.available_slots}"
            )
            kb.row(InlineKeyboardButton(
                text=f"🗑  {s.datetime.strftime('%d.%m %H:%M')}",
                callback_data=f"admin_sched_del_{s.id}",
            ))

    kb.row(InlineKeyboardButton(text="➕  Додати дату", callback_data=f"admin_p_addsched_{practice_id}"))
    kb.row(InlineKeyboardButton(text="◀️  Назад", callback_data=f"admin_p_{practice_id}"))

    await callback.message.edit_text("\n".join(lines), reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_sched_del_"))
async def cb_admin_schedule_delete(callback: CallbackQuery, session: AsyncSession):
    sched_id = int(callback.data.replace("admin_sched_del_", ""))
    sched = await session.get(PracticeSchedule, sched_id)
    if not sched:
        await callback.answer("Не знайдено", show_alert=True)
        return
    practice_id = sched.practice_id
    # Перевіримо чи є активні бронювання — якщо так, не видаляємо, лише позначаємо як недоступне
    bookings_result = await session.execute(
        select(func.count()).select_from(Booking).where(
            Booking.schedule_id == sched_id,
            Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
        )
    )
    active_bookings = bookings_result.scalar() or 0
    if active_bookings > 0:
        sched.is_available = False
        await session.commit()
        await callback.answer("Має активні бронювання — лише прихована", show_alert=True)
    else:
        await session.delete(sched)
        await session.commit()
        await callback.answer("Дату видалено")
    # повертаємось до розкладу
    callback.data = f"admin_p_sched_{practice_id}"
    await cb_admin_practice_schedule(callback, session)


# ── Додавання дати до розкладу

@router.callback_query(F.data.startswith("admin_p_addsched_"))
async def cb_admin_addsched_start(callback: CallbackQuery, state: FSMContext):
    practice_id = int(callback.data.replace("admin_p_addsched_", ""))
    await state.set_state(AdminStates.add_schedule_datetime)
    await state.update_data(practice_id=practice_id)
    await callback.message.answer(
        "📅 <b>Додавання дати</b>\n\n"
        "Надішліть дату й час у форматі <code>ДД.ММ.РРРР ГГ:ХХ</code>\n"
        "Наприклад: <code>11.05.2026 11:00</code>\n\n"
        "Або /cancel для відміни.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.add_schedule_datetime, F.text == "/cancel")
async def admin_addsched_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Скасовано.")


@router.message(AdminStates.add_schedule_datetime)
async def admin_addsched_apply(message: Message, state: FSMContext, session: AsyncSession):
    try:
        dt = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
    except Exception:
        await message.answer("❌ Невірний формат. Спробуйте: <code>ДД.ММ.РРРР ГГ:ХХ</code>", parse_mode="HTML")
        return

    data = await state.get_data()
    practice_id = data.get("practice_id")
    practice = await session.get(Practice, practice_id)
    if not practice:
        await message.answer("Практику не знайдено")
        await state.clear()
        return

    sched = PracticeSchedule(
        practice_id=practice_id,
        datetime=dt,
        available_slots=practice.max_participants or 13,
        is_available=True,
    )
    session.add(sched)
    await session.commit()
    await state.clear()
    await message.answer(f"✅ Додано дату <b>{dt.strftime('%d.%m.%Y %H:%M')}</b>", parse_mode="HTML")


# ── Редагування поля практики (одне поле через FSM)

@router.callback_query(F.data.regexp(r"^admin_p_edit_\d+_(title|description|details|price|duration_minutes|max_participants)$"))
async def cb_admin_practice_edit_start(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    practice_id = int(parts[3])
    field = "_".join(parts[4:])
    await state.set_state(AdminStates.edit_field_value)
    await state.update_data(practice_id=practice_id, field=field)

    prompts = {
        "title": "Надішліть нову назву практики:",
        "description": "Надішліть новий короткий опис (показується у картці; можна з HTML-тегами <b>, <i>):",
        "details": (
            "Надішліть детальний опис практики (можна з HTML, переноси рядків).\n"
            "Цей текст показується клієнтам по кнопці «📖 Детальніше про практику»."
        ),
        "price": "Надішліть нову ціну в грн (число):",
        "duration_minutes": "Надішліть нову тривалість у хвилинах (число):",
        "max_participants": "Надішліть нове максимальне число учасників (число):",
    }
    await callback.message.answer(
        f"✏️ <b>Редагування</b>\n\n{prompts[field]}\n\nАбо /cancel для відміни.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.edit_field_value, F.text == "/cancel")
async def admin_edit_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Скасовано.")


@router.message(AdminStates.edit_field_value)
async def admin_edit_apply(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    practice_id = data.get("practice_id")
    field = data.get("field")

    practice = await session.get(Practice, practice_id)
    if not practice:
        await message.answer("Практику не знайдено")
        await state.clear()
        return

    raw = message.text.strip()
    try:
        if field in ("price",):
            value = float(raw.replace(",", "."))
        elif field in ("duration_minutes", "max_participants"):
            value = int(raw)
        else:
            value = raw
    except ValueError:
        await message.answer("❌ Очікувалось число. Спробуйте ще раз або /cancel.")
        return

    setattr(practice, field, value)
    await session.commit()
    await state.clear()

    await message.answer(
        "✅ Збережено.\n\n" + _format_practice_card(practice),
        reply_markup=_practice_card_kb(practice),
        parse_mode="HTML",
    )


# ── Створення нової практики через FSM

@router.callback_query(F.data == "admin_p_new")
async def cb_admin_practice_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.new_practice_title)
    await callback.message.answer(
        "✨ <b>Створення нової практики</b>\n\n"
        "Крок 1/5: надішліть <b>назву</b> практики.\n"
        "Або /cancel для відміни.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.new_practice_title, F.text == "/cancel")
@router.message(AdminStates.new_practice_description, F.text == "/cancel")
@router.message(AdminStates.new_practice_price, F.text == "/cancel")
@router.message(AdminStates.new_practice_duration, F.text == "/cancel")
@router.message(AdminStates.new_practice_max, F.text == "/cancel")
async def new_practice_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Створення скасовано.")


@router.message(AdminStates.new_practice_title)
async def new_practice_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AdminStates.new_practice_description)
    await message.answer("Крок 2/5: надішліть <b>опис</b> (можна з HTML).", parse_mode="HTML")


@router.message(AdminStates.new_practice_description)
async def new_practice_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AdminStates.new_practice_price)
    await message.answer("Крок 3/5: надішліть <b>ціну</b> в грн (число).", parse_mode="HTML")


@router.message(AdminStates.new_practice_price)
async def new_practice_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("❌ Очікувалось число. Спробуйте ще раз.")
        return
    await state.update_data(price=price)
    await state.set_state(AdminStates.new_practice_duration)
    await message.answer("Крок 4/5: надішліть <b>тривалість</b> у хвилинах (число).", parse_mode="HTML")


@router.message(AdminStates.new_practice_duration)
async def new_practice_duration(message: Message, state: FSMContext):
    try:
        duration = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Очікувалось ціле число. Спробуйте ще раз.")
        return
    await state.update_data(duration=duration)
    await state.set_state(AdminStates.new_practice_max)
    await message.answer("Крок 5/5: надішліть <b>максимум учасників</b> (число).", parse_mode="HTML")


@router.message(AdminStates.new_practice_max)
async def new_practice_max(message: Message, state: FSMContext, session: AsyncSession):
    try:
        max_p = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Очікувалось ціле число. Спробуйте ще раз.")
        return

    data = await state.get_data()
    practice = Practice(
        title=data["title"],
        description=data["description"],
        practice_type=PracticeType.GROUP,
        duration_minutes=data["duration"],
        price=data["price"],
        max_participants=max_p,
        is_active=True,
    )
    session.add(practice)
    await session.commit()
    await session.refresh(practice)
    await state.clear()

    await message.answer(
        "🎉 <b>Практику створено!</b>\n\n" + _format_practice_card(practice),
        reply_markup=_practice_card_kb(practice),
        parse_mode="HTML",
    )


# ────────────────────── 📍 Локації (адмін) ──────────────────────

@router.callback_query(F.data == "admin_locations")
async def cb_admin_locations(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(Location).order_by(Location.sort_order, Location.id)
    )
    locations = result.scalars().all()

    kb = InlineKeyboardBuilder()
    if not locations:
        text = (
            "📍 <b>ЛОКАЦІЇ</b>\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "<i>Локацій ще немає. Запустіть на сервері:\n"
            "<code>venv/bin/python seed_locations.py</code></i>"
        )
    else:
        lines = ["📍 <b>ЛОКАЦІЇ</b>", "━━━━━━━━━━━━━━━━━", ""]
        for loc in locations:
            video_mark = "🎬" if loc.video_file_id else "📹❌"
            active_mark = "🟢" if loc.is_active else "⚪️"
            lines.append(f"{active_mark} {video_mark}  <b>{loc.title}</b>\n   <i>{loc.address}</i>")
            kb.row(InlineKeyboardButton(
                text=f"{active_mark} {video_mark}  {loc.title}",
                callback_data=f"admin_loc_{loc.id}",
            ))
        text = "\n".join(lines)

    kb.row(InlineKeyboardButton(text="◀️  До адмін-меню", callback_data="admin_menu"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


def _location_admin_kb(loc: Location) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🎬  Завантажити відео", callback_data=f"admin_loc_video_{loc.id}"))
    if loc.video_file_id:
        kb.row(InlineKeyboardButton(text="🗑  Видалити відео", callback_data=f"admin_loc_delvideo_{loc.id}"))
    toggle = "⚪️ Деактивувати" if loc.is_active else "🟢 Активувати"
    kb.row(InlineKeyboardButton(text=toggle, callback_data=f"admin_loc_toggle_{loc.id}"))
    kb.row(InlineKeyboardButton(text="◀️  До списку локацій", callback_data="admin_locations"))
    return kb.as_markup()


def _format_location_admin(loc: Location) -> str:
    state = "🟢 активна" if loc.is_active else "⚪️ неактивна"
    video = "🎬 відео завантажено" if loc.video_file_id else "📹❌ відео не завантажено"
    return (
        f"📍 <b>{loc.title}</b>  ({state})\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"🏠  <b>Адреса:</b>\n{loc.address}\n\n"
        f"🗺  <b>Карта:</b>  <a href='{loc.maps_url}'>Google Maps</a>\n\n"
        f"{video}"
    )


@router.callback_query(F.data.regexp(r"^admin_loc_\d+$"))
async def cb_admin_location(callback: CallbackQuery, session: AsyncSession):
    loc_id = int(callback.data.replace("admin_loc_", ""))
    loc = await session.get(Location, loc_id)
    if not loc:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await callback.message.edit_text(
        _format_location_admin(loc),
        reply_markup=_location_admin_kb(loc),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_loc_toggle_"))
async def cb_admin_location_toggle(callback: CallbackQuery, session: AsyncSession):
    loc_id = int(callback.data.replace("admin_loc_toggle_", ""))
    loc = await session.get(Location, loc_id)
    if not loc:
        await callback.answer("Не знайдено", show_alert=True)
        return
    loc.is_active = not loc.is_active
    await session.commit()
    await callback.answer("Активовано" if loc.is_active else "Деактивовано")
    await callback.message.edit_text(
        _format_location_admin(loc),
        reply_markup=_location_admin_kb(loc),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("admin_loc_delvideo_"))
async def cb_admin_location_del_video(callback: CallbackQuery, session: AsyncSession):
    loc_id = int(callback.data.replace("admin_loc_delvideo_", ""))
    loc = await session.get(Location, loc_id)
    if not loc:
        await callback.answer("Не знайдено", show_alert=True)
        return
    loc.video_file_id = None
    await session.commit()
    await callback.answer("Відео видалено")
    await callback.message.edit_text(
        _format_location_admin(loc),
        reply_markup=_location_admin_kb(loc),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("admin_loc_video_"))
async def cb_admin_location_video_start(callback: CallbackQuery, state: FSMContext):
    loc_id = int(callback.data.replace("admin_loc_video_", ""))
    await state.set_state(AdminStates.location_upload_video)
    await state.update_data(location_id=loc_id)
    await callback.message.answer(
        "🎬 <b>Завантаження відео для локації</b>\n\n"
        "Надішліть відеофайл у цей чат — він буде збережений як інструкція.\n"
        "Підтримуються відео або відео-документи (mp4).\n\n"
        "Або /cancel для відміни.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.location_upload_video, F.text == "/cancel")
async def admin_loc_video_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Скасовано.")


@router.message(AdminStates.location_upload_video, F.video | F.document | F.animation)
async def admin_loc_video_save(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    loc_id = data.get("location_id")
    loc = await session.get(Location, loc_id)
    if not loc:
        await message.answer("Локацію не знайдено")
        await state.clear()
        return

    file_id = None
    if message.video:
        file_id = message.video.file_id
    elif message.animation:
        file_id = message.animation.file_id
    elif message.document:
        file_id = message.document.file_id

    if not file_id:
        await message.answer("Не вдалось отримати файл. Спробуйте ще раз або /cancel.")
        return

    loc.video_file_id = file_id
    await session.commit()
    await state.clear()
    await message.answer(
        f"✅ Відео збережено для локації <b>{loc.title}</b>",
        parse_mode="HTML",
    )


# ────────────────────── 📝 Анкети ──────────────────────

@router.callback_query(F.data == "admin_anketas")
async def cb_admin_anketas(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(Questionnaire).order_by(Questionnaire.updated_at.desc()).limit(30)
    )
    questionnaires = result.scalars().all()

    lines = ["📝 <b>АНКЕТИ УЧАСНИКІВ</b>", "━━━━━━━━━━━━━━━━━", ""]
    kb = InlineKeyboardBuilder()

    if not questionnaires:
        lines.append("<i>Поки що ніхто не заповнив анкету.</i>")
    else:
        for q in questionnaires:
            user = await session.get(User, q.user_id)
            handle = f"@{user.username}" if user and user.username else (user.full_name if user else "?")
            updated = q.updated_at.strftime("%d.%m %H:%M") if q.updated_at else "—"
            lines.append(f"• {handle}  •  <i>{updated}</i>")
            kb.row(InlineKeyboardButton(
                text=f"📝 {handle}  •  {updated}",
                callback_data=f"admin_anketa_{q.id}",
            ))

    kb.row(InlineKeyboardButton(text="◀️  До адмін-меню", callback_data="admin_menu"))
    await callback.message.edit_text("\n".join(lines), reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


def _format_anketa(q: Questionnaire, user: User) -> str:
    try:
        answers = json.loads(q.data) if q.data else {}
    except Exception:
        answers = {}

    handle = f"@{user.username}" if user and user.username else (user.full_name if user else "?")
    lines = [
        "📝 <b>АНКЕТА УЧАСНИКА</b>",
        f"👤 {user.full_name if user else '?'}  •  {handle}",
        f"<i>заповнено {q.updated_at.strftime('%d.%m.%Y %H:%M') if q.updated_at else '—'}</i>",
        "━━━━━━━━━━━━━━━━━",
        "",
    ]
    for i, qdef in enumerate(ANKETA_QUESTIONS, start=1):
        # Беремо тільки заголовок питання (перший рядок без HTML), щоб не дублювати
        prompt_short = qdef["prompt"].split("\n")[0]
        # Прибираємо <b>1/12.</b> на початку для краси
        prompt_short = prompt_short.replace(f"<b>{i}/12.</b>", "").strip()
        ans = answers.get(qdef["key"], "—")
        lines.append(f"<b>{i}.</b>  {prompt_short}\n   ↳  <i>{ans}</i>\n")

    return "\n".join(lines)


@router.callback_query(F.data.startswith("admin_anketa_"))
async def cb_admin_anketa_view(callback: CallbackQuery, session: AsyncSession):
    anketa_id = int(callback.data.replace("admin_anketa_", ""))
    q = await session.get(Questionnaire, anketa_id)
    if not q:
        await callback.answer("Анкету не знайдено", show_alert=True)
        return
    user = await session.get(User, q.user_id)

    kb = InlineKeyboardBuilder()
    if user and user.telegram_id:
        kb.row(InlineKeyboardButton(
            text="💬  Написати клієнту",
            url=f"tg://user?id={user.telegram_id}",
        ))
    kb.row(InlineKeyboardButton(text="◀️  До списку анкет", callback_data="admin_anketas"))

    text = _format_anketa(q, user)
    # Telegram обрізає повідомлення до 4096 символів — урізаємо при потребі
    if len(text) > 4000:
        text = text[:3990] + "\n\n…"

    try:
        await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.message(F.text.regexp(r"^/anketa_\d+"))
async def cmd_anketa(message: Message, session: AsyncSession):
    try:
        anketa_id = int(message.text.split("_", 1)[1].split()[0])
    except Exception:
        await message.answer("Невірний формат. /anketa_<id>")
        return
    q = await session.get(Questionnaire, anketa_id)
    if not q:
        await message.answer("Анкету не знайдено")
        return
    user = await session.get(User, q.user_id)
    text = _format_anketa(q, user)
    if len(text) > 4000:
        text = text[:3990] + "\n\n…"
    kb = InlineKeyboardBuilder()
    if user and user.telegram_id:
        kb.row(InlineKeyboardButton(
            text="💬  Написати клієнту",
            url=f"tg://user?id={user.telegram_id}",
        ))
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


# ────────────────────── 🐘 Закриті заявки ──────────────────────

CLOSED_STATUS_LABELS = {
    ClosedFormatStatus.NEW: "🆕 Нова",
    ClosedFormatStatus.ACCEPTED: "✅ Погоджена",
    ClosedFormatStatus.PAID: "💰 Оплачена",
    ClosedFormatStatus.COMPLETED: "🏁 Проведена",
    ClosedFormatStatus.CANCELLED: "❌ Скасована",
}

CLOSED_CLIENT_MESSAGES = {
    ClosedFormatStatus.ACCEPTED: (
        "✅ <b>Ваш закритий формат погоджено!</b>\n\n"
        "Зараз надішлемо реквізити для передоплати 3000 грн.\n"
        "Чекаємо на вас 🤍"
    ),
    ClosedFormatStatus.PAID: (
        "💰 <b>Дякуємо, передоплату отримано!</b>\n\nЧекаємо на вас 🪷"
    ),
    ClosedFormatStatus.COMPLETED: (
        "🏁 <b>Дякуємо за зустріч!</b> 💫\n\nДо нових зустрічей у Magic Vibes 🤍"
    ),
    ClosedFormatStatus.CANCELLED: (
        "❌ <b>Заявку скасовано</b>\n\nЯкщо це помилка — звʼяжіться з менеджером 💬"
    ),
}


@router.callback_query(F.data == "admin_closed")
async def cb_admin_closed_list(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(ClosedFormatRequest).order_by(ClosedFormatRequest.created_at.desc()).limit(20)
    )
    requests = result.scalars().all()

    lines = ["🐘 <b>ЗАКРИТІ ЗАЯВКИ</b>", "━━━━━━━━━━━━━━━━━", ""]
    kb = InlineKeyboardBuilder()

    if not requests:
        lines.append("<i>Заявок ще немає.</i>")
    else:
        for r in requests:
            user = await session.get(User, r.user_id)
            handle = f"@{user.username}" if user and user.username else (user.full_name if user else "?")
            status_label = CLOSED_STATUS_LABELS.get(r.status, str(r.status))
            created = r.created_at.strftime("%d.%m %H:%M") if r.created_at else "—"
            lines.append(f"{status_label}  •  <b>#{r.id}</b>  •  {handle}  •  <i>{created}</i>")
            kb.row(InlineKeyboardButton(
                text=f"#{r.id}  {status_label}  •  {handle}",
                callback_data=f"admin_closed_open_{r.id}",
            ))

    kb.row(InlineKeyboardButton(text="◀️  До адмін-меню", callback_data="admin_menu"))
    await callback.message.edit_text("\n".join(lines), reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


def _closed_request_kb(request_id: int, user_telegram_id: Optional[int] = None) -> InlineKeyboardMarkup:
    from aiogram.types import InlineKeyboardButton as IKB
    kb = InlineKeyboardBuilder()
    for status, label in CLOSED_STATUS_LABELS.items():
        kb.row(IKB(text=label, callback_data=f"admin_closed_set_{request_id}_{status.value}"))
    if user_telegram_id:
        kb.row(IKB(text="💬  Написати клієнту", url=f"tg://user?id={user_telegram_id}"))
    kb.row(IKB(text="◀️  До списку", callback_data="admin_closed"))
    return kb.as_markup()


def _format_closed_request(r: ClosedFormatRequest, user: User) -> str:
    handle = f"@{user.username}" if user and user.username else (user.full_name if user else "?")
    notes = f"\n📝  <b>Коментар:</b>  <i>{r.notes}</i>" if r.notes else ""
    phone = f"\n📞  <b>Телефон:</b>  {r.contact_phone}" if r.contact_phone else ""
    status_label = CLOSED_STATUS_LABELS.get(r.status, str(r.status))
    created = r.created_at.strftime("%d.%m.%Y %H:%M") if r.created_at else "—"
    return (
        f"🐘 <b>Заявка #{r.id}</b>  ({status_label})\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"📅  <b>Бажана дата:</b>  {r.requested_date_text}\n"
        f"👥  <b>Розмір групи:</b>  {r.group_size}{phone}\n\n"
        f"👤  {user.full_name if user else '?'}  •  {handle}{notes}\n\n"
        f"<i>Створено {created}</i>\n\n"
        "👇 Оберіть новий статус:"
    )


@router.callback_query(F.data.startswith("admin_closed_open_"))
async def cb_admin_closed_open(callback: CallbackQuery, session: AsyncSession):
    request_id = int(callback.data.replace("admin_closed_open_", ""))
    r = await session.get(ClosedFormatRequest, request_id)
    if not r:
        await callback.answer("Не знайдено", show_alert=True)
        return
    user = await session.get(User, r.user_id)

    text = _format_closed_request(r, user)
    kb = _closed_request_kb(request_id, user.telegram_id if user else None)

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(F.text.regexp(r"^/closed_\d+"))
async def cmd_closed(message: Message, session: AsyncSession):
    try:
        request_id = int(message.text.split("_", 1)[1].split()[0])
    except Exception:
        await message.answer("Невірний формат. /closed_<id>")
        return
    r = await session.get(ClosedFormatRequest, request_id)
    if not r:
        await message.answer("Не знайдено")
        return
    user = await session.get(User, r.user_id)
    await message.answer(
        _format_closed_request(r, user),
        reply_markup=_closed_request_kb(request_id, user.telegram_id if user else None),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_closed_set_"))
async def cb_admin_closed_set(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Зміна статусу заявки + автоповідомлення клієнту."""
    try:
        suffix = callback.data.replace("admin_closed_set_", "")
        request_id_s, status_s = suffix.split("_", 1)
        request_id = int(request_id_s)
        new_status = ClosedFormatStatus(status_s)
    except Exception:
        await callback.answer("Невірна команда", show_alert=True)
        return

    r = await session.get(ClosedFormatRequest, request_id)
    if not r:
        await callback.answer("Не знайдено", show_alert=True)
        return

    r.status = new_status
    await session.commit()

    # Сповіщаємо клієнта
    user = await session.get(User, r.user_id)
    msg = CLOSED_CLIENT_MESSAGES.get(new_status)
    if user and msg:
        try:
            await bot.send_message(user.telegram_id, msg, parse_mode="HTML")
        except Exception:
            pass

    label = CLOSED_STATUS_LABELS.get(new_status, str(new_status))
    await callback.answer(f"Статус: {label}")

    text = _format_closed_request(r, user)
    kb = _closed_request_kb(request_id, user.telegram_id if user else None)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
