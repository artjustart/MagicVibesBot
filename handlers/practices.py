"""
Обробники запису на групові практики
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from database.models import (
    Practice, PracticeSchedule, Booking, Payment, User,
    PracticeType, BookingStatus, PaymentStatus,
)
from keyboards.inline import (
    get_practices_keyboard,
    get_practice_schedule_keyboard,
    get_booking_confirmation_keyboard,
    get_back_to_main_menu,
)
from services.requisites import format_requisites, format_purpose_for_booking
from services.notifications import notify_new_booking
from content.texts import WHAT_TO_BRING, CANCELLATION_POLICY, ORG_INFO
from datetime import timedelta

router = Router()


class BookingStates(StatesGroup):
    waiting_for_notes = State()
    waiting_for_proof = State()  # очікуємо скріншот/PDF-квитанцію


def _practice_teaser(description: str) -> str:
    """Перший абзац опису — як короткий тизер."""
    if not description:
        return ""
    parts = [p.strip() for p in description.strip().split("\n\n") if p.strip()]
    return parts[0] if parts else description[:300]


@router.callback_query(F.data == "practices_list")
async def show_practices_list(callback: CallbackQuery, session: AsyncSession):
    """Список актуальних групових практик — у вигляді виразних карток."""
    result = await session.execute(
        select(Practice).where(
            Practice.is_active == True,
            Practice.practice_type == PracticeType.GROUP,
        )
    )
    practices = result.scalars().all()

    if not practices:
        text = """
🪷 <b>Актуальні практики</b>

На жаль, зараз немає доступних практик.
Слідкуйте за оновленнями 🤍
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # Видаляємо поточне меню — далі надсилаємо красиві картки
    try:
        await callback.message.delete()
    except Exception:
        pass

    bot = callback.bot
    chat_id = callback.from_user.id

    # Шапка (компактна — не ламається на вузьких екранах)
    await bot.send_message(
        chat_id=chat_id,
        text="🪷 <b>АКТУАЛЬНІ ПРАКТИКИ</b> 🪷",
        parse_mode="HTML",
    )

    # Картка для кожної практики
    for practice in practices:
        # Найближчі 3 заняття
        sched_result = await session.execute(
            select(PracticeSchedule).where(
                PracticeSchedule.practice_id == practice.id,
                PracticeSchedule.is_available == True,
                PracticeSchedule.datetime >= datetime.utcnow(),
                PracticeSchedule.available_slots > 0,
            ).order_by(PracticeSchedule.datetime).limit(3)
        )
        upcoming = sched_result.scalars().all()

        if upcoming:
            dates_lines = "\n".join(
                f"   • <b>{s.datetime.strftime('%d.%m.%Y о %H:%M')}</b>  —  залишилось <b>{s.available_slots}</b> місць"
                for s in upcoming
            )
            schedule_block = f"📅  <b>Найближчі дати:</b>\n{dates_lines}\n"
        else:
            schedule_block = "📅  <i>Найближчі дати уточнюйте у менеджера</i>\n"

        teaser = _practice_teaser(practice.description)

        card_text = (
            f"🌟  <b>{practice.title}</b>\n\n"
            f"{teaser}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{schedule_block}"
            f"⏱  <b>Тривалість:</b>  {practice.duration_minutes} хв\n"
            f"💰  <b>Вартість:</b>  <b>{int(practice.price)} грн</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(
            text="🪷   ЗАПИСАТИСЯ НА ПРАКТИКУ   🪷",
            callback_data=f"practice_{practice.id}",
        ))

        await bot.send_message(
            chat_id=chat_id,
            text=card_text,
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )

    # Кнопка повернення в меню — окремим повідомленням знизу
    await bot.send_message(
        chat_id=chat_id,
        text="━━━━━━━━━━━━━━━━━━━━",
        reply_markup=get_back_to_main_menu(),
    )

    await callback.answer()


def _practice_info_kb(practice: Practice) -> "InlineKeyboardBuilder":
    """Інфо-екран картки практики з сабменю."""
    kb = InlineKeyboardBuilder()
    if practice.details:
        kb.row(InlineKeyboardButton(
            text="📖  Детальніше про практику",
            callback_data=f"pdetails_{practice.id}",
        ))
    kb.row(InlineKeyboardButton(
        text="🎒  Що взяти з собою",
        callback_data=f"pbring_{practice.id}",
    ))
    kb.row(InlineKeyboardButton(
        text="❗  Умови скасування",
        callback_data=f"ppolicy_{practice.id}",
    ))
    kb.row(InlineKeyboardButton(
        text="🗓  Організаційна інформація",
        callback_data=f"porg_{practice.id}",
    ))
    kb.row(InlineKeyboardButton(
        text="📅  Обрати дату й записатися",
        callback_data=f"pickdate_{practice.id}",
    ))
    kb.row(InlineKeyboardButton(
        text="◀️  До списку практик",
        callback_data="practices_list",
    ))
    return kb.as_markup()


def _back_to_practice_kb(practice_id: int) -> "InlineKeyboardMarkup":
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="◀️  До картки практики",
        callback_data=f"practice_{practice_id}",
    ))
    return kb.as_markup()


@router.callback_query(F.data.regexp(r"^practice_\d+$"))
async def show_practice_info(callback: CallbackQuery, session: AsyncSession):
    """Інфо-екран картки практики (короткий опис + сабменю)."""
    practice_id = int(callback.data.replace("practice_", ""))
    practice = await session.get(Practice, practice_id)
    if not practice:
        await callback.answer("Практику не знайдено", show_alert=True)
        return

    text = (
        f"🪷  <b>{practice.title}</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"{practice.description}\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"⏱  <b>Тривалість:</b>  {practice.duration_minutes} хв\n"
        f"💰  <b>Вартість:</b>  {int(practice.price)} грн\n\n"
        "👇 Що цікавить?"
    )

    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=_practice_info_kb(practice),
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            text=text,
            reply_markup=_practice_info_kb(practice),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("pdetails_"))
async def show_practice_details(callback: CallbackQuery, session: AsyncSession):
    """Довгий опис практики (з БД-поля Practice.details)."""
    practice_id = int(callback.data.replace("pdetails_", ""))
    practice = await session.get(Practice, practice_id)
    if not practice or not practice.details:
        await callback.answer("Деталей ще немає", show_alert=True)
        return

    await callback.message.edit_text(
        text=practice.details,
        reply_markup=_back_to_practice_kb(practice_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pbring_"))
async def show_practice_what_to_bring(callback: CallbackQuery):
    practice_id = int(callback.data.replace("pbring_", ""))
    await callback.message.edit_text(
        text=WHAT_TO_BRING,
        reply_markup=_back_to_practice_kb(practice_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ppolicy_"))
async def show_practice_policy(callback: CallbackQuery):
    practice_id = int(callback.data.replace("ppolicy_", ""))
    await callback.message.edit_text(
        text=CANCELLATION_POLICY,
        reply_markup=_back_to_practice_kb(practice_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("porg_"))
async def show_practice_org(callback: CallbackQuery):
    practice_id = int(callback.data.replace("porg_", ""))
    await callback.message.edit_text(
        text=ORG_INFO,
        reply_markup=_back_to_practice_kb(practice_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pickdate_"))
async def show_practice_schedule(callback: CallbackQuery, session: AsyncSession):
    """Розклад конкретної практики — вибір дати."""
    practice_id = int(callback.data.replace("pickdate_", ""))
    practice = await session.get(Practice, practice_id)

    if not practice:
        await callback.answer("Практику не знайдено", show_alert=True)
        return

    result = await session.execute(
        select(PracticeSchedule).where(
            PracticeSchedule.practice_id == practice_id,
            PracticeSchedule.is_available == True,
            PracticeSchedule.datetime >= datetime.utcnow(),
            PracticeSchedule.available_slots > 0,
        ).order_by(PracticeSchedule.datetime)
    )
    schedules = result.scalars().all()

    if schedules:
        text = (
            f"🪷  <b>{practice.title}</b>\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            f"⏱  <b>Тривалість:</b>  {practice.duration_minutes} хв\n"
            f"💰  <b>Вартість:</b>  {int(practice.price)} грн\n\n"
            "📅 <b>Оберіть зручну дату:</b>"
        )
        # Власна клавіатура з кнопкою «До картки практики»
        kb = InlineKeyboardBuilder()
        for s in schedules:
            kb.row(InlineKeyboardButton(
                text=f"📅  {s.datetime.strftime('%d.%m  •  %H:%M')}  •  залишилось {s.available_slots}",
                callback_data=f"book_{s.id}",
            ))
        kb.row(InlineKeyboardButton(
            text="◀️  До картки практики",
            callback_data=f"practice_{practice_id}",
        ))
        await callback.message.edit_text(
            text=text,
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )
    else:
        text = (
            f"🪷  <b>{practice.title}</b>\n\n"
            "На жаль, зараз немає доступних дат.\n"
            "Звʼяжіться з менеджером, щоб уточнити розклад."
        )
        await callback.message.edit_text(
            text=text,
            reply_markup=_back_to_practice_kb(practice_id),
            parse_mode="HTML",
        )

    await callback.answer()


@router.callback_query(F.data.startswith("book_"))
async def create_booking(callback: CallbackQuery, session: AsyncSession, config):
    """Створення бронювання"""
    schedule_id = int(callback.data.replace("book_", ""))
    schedule = await session.get(PracticeSchedule, schedule_id)

    if not schedule or not schedule.is_available or schedule.available_slots <= 0:
        await callback.answer("Цей час уже недоступний", show_alert=True)
        return

    practice = await session.get(Practice, schedule.practice_id)

    result = await session.execute(
        select(User).where(User.telegram_id == callback.from_user.id)
    )
    user = result.scalar_one()

    booking = Booking(
        user_id=user.id,
        practice_id=practice.id,
        schedule_id=schedule.id,
        status=BookingStatus.PENDING,
    )
    session.add(booking)

    schedule.available_slots -= 1
    if schedule.available_slots == 0:
        schedule.is_available = False

    await session.commit()
    await session.refresh(booking)

    # Уведомлюємо адмінів про нову заявку
    try:
        await notify_new_booking(callback.bot, config.tg_bot.admin_ids, session, booking.id)
    except Exception:
        pass

    date_str = schedule.datetime.strftime("%d.%m.%Y о %H:%M")
    text = f"""
✅ <b>Бронювання створено!</b>

🪷  <b>Практика:</b> {practice.title}
📅  <b>Дата і час:</b> {date_str}
⏱  <b>Тривалість:</b> {practice.duration_minutes} хв
💰  <b>Вартість:</b> {int(practice.price)} грн

━━━━━━━━━━━━━━━━━
👇 Підтвердіть бронювання та перейдіть до оплати:
"""

    await callback.message.edit_text(
        text=text,
        reply_markup=get_booking_confirmation_keyboard(booking.id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_booking_"))
async def confirm_booking_and_pay(callback: CallbackQuery, session: AsyncSession):
    """Підтвердження бронювання — показуємо реквізити для оплати переказом."""
    booking_id = int(callback.data.replace("confirm_booking_", ""))

    booking = await session.get(Booking, booking_id)
    if not booking:
        await callback.answer("Бронювання не знайдено", show_alert=True)
        return

    practice = await session.get(Practice, booking.practice_id)
    schedule = await session.get(PracticeSchedule, booking.schedule_id)
    user = await session.get(User, booking.user_id)
    if not (practice and schedule and user):
        await callback.answer("Дані заявки неповні", show_alert=True)
        return

    # Створюємо запис платежу зі статусом PENDING (без MonoPay)
    payment = Payment(
        user_id=booking.user_id,
        booking_id=booking.id,
        amount=practice.price,
        currency="UAH",
        status=PaymentStatus.PENDING,
        payment_provider="manual_transfer",
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)

    date_str = schedule.datetime.strftime("%d.%m.%Y %H:%M")
    purpose = format_purpose_for_booking(practice.title, date_str, user.full_name or "")
    requisites_text = format_requisites(purpose)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="📸  Я сплатив(ла) — надіслати квитанцію",
        callback_data=f"proof_booking_{booking.id}",
    ))
    kb.row(InlineKeyboardButton(
        text="❌  Скасувати заявку",
        callback_data=f"cancel_booking_{booking.id}",
    ))
    kb.row(InlineKeyboardButton(text="◀️  До головного меню", callback_data="main_menu"))

    await callback.message.edit_text(
        text=requisites_text,
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


# ───────── Завантаження квитанції клієнтом ─────────

@router.callback_query(F.data.startswith("proof_booking_"))
async def start_proof_upload_for_booking(callback: CallbackQuery, state: FSMContext):
    """Очікуємо скріншот/PDF-квитанції для конкретного бронювання."""
    booking_id = int(callback.data.replace("proof_booking_", ""))
    await state.set_state(BookingStates.waiting_for_proof)
    await state.update_data(booking_id=booking_id, kind="booking")

    await callback.message.answer(
        "📸 <b>Надішліть, будь ласка, квитанцію</b>\n\n"
        "Підійде скріншот, фото або PDF-чек.\n"
        "Можна додати кілька файлів — кожне фото окремим повідомленням.\n\n"
        "Коли закінчите — натисніть /done\n"
        "Або /cancel щоб відмінити.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "proof_generic")
async def start_proof_upload_generic(callback: CallbackQuery, state: FSMContext):
    """Завантаження квитанції без привʼязки до бронювання (з кнопки в меню)."""
    await state.set_state(BookingStates.waiting_for_proof)
    await state.update_data(kind="generic")

    await callback.message.answer(
        "📸 <b>Надішліть, будь ласка, квитанцію</b>\n\n"
        "Підійде скріншот, фото або PDF-чек.\n"
        "Якщо файлів декілька — кожен окремим повідомленням.\n\n"
        "Коли закінчите — натисніть /done\n"
        "Або /cancel щоб відмінити.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(BookingStates.waiting_for_proof, F.text == "/cancel")
async def proof_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Скасовано.", reply_markup=get_back_to_main_menu())


@router.message(BookingStates.waiting_for_proof, F.text == "/done")
async def proof_done(message: Message, state: FSMContext):
    data = await state.get_data()
    sent = data.get("sent_count", 0)
    if sent == 0:
        await message.answer("Ви ще нічого не надіслали. Прикріпіть квитанцію або /cancel.")
        return
    await state.clear()
    await message.answer(
        f"✅ <b>Дякуємо!</b>\n\n"
        f"Ми отримали ваше підтвердження ({sent} файл(ів)).\n"
        "Менеджер перевірить оплату та звʼяжеться з вами найближчим часом 🤍",
        reply_markup=get_back_to_main_menu(),
        parse_mode="HTML",
    )


@router.message(BookingStates.waiting_for_proof, F.photo | F.document)
async def proof_collect(message: Message, state: FSMContext, session: AsyncSession, config):
    """Користувач прислав фото/документ — пересилаємо адмінам."""
    data = await state.get_data()
    kind = data.get("kind")
    sent_count = data.get("sent_count", 0) + 1
    await state.update_data(sent_count=sent_count)

    user = message.from_user
    handle = f"@{user.username}" if user.username else f"<a href='tg://user?id={user.id}'>відкрити чат</a>"

    if kind == "booking":
        booking_id = data.get("booking_id")
        booking = await session.get(Booking, booking_id) if booking_id else None
        practice = await session.get(Practice, booking.practice_id) if booking else None
        schedule = await session.get(PracticeSchedule, booking.schedule_id) if booking else None
        date_str = schedule.datetime.strftime("%d.%m.%Y о %H:%M") if schedule else "—"

        caption = (
            "💰 <b>КВИТАНЦІЯ ВІД КЛІЄНТА</b>\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            f"📋 <b>Заявка #{booking_id}</b>\n"
            f"🪷  {practice.title if practice else '?'}\n"
            f"📅  {date_str}\n"
            f"💰  {int(practice.price) if practice else 0} грн\n\n"
            f"👤  {user.full_name}  •  {handle}\n\n"
            f"/booking_{booking_id} — відкрити заявку"
        )
    else:
        caption = (
            "💰 <b>КВИТАНЦІЯ ВІД КЛІЄНТА</b>  (загальна)\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            f"👤  {user.full_name}  •  {handle}\n"
            "<i>Без привʼязки до бронювання</i>"
        )

    bot = message.bot
    for admin_id in config.tg_bot.admin_ids:
        try:
            # Пересилаємо оригінальне повідомлення (зберігає якість)
            forwarded = await bot.copy_message(
                chat_id=admin_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            # І окремим повідомленням — підпис із метаданими
            await bot.send_message(
                chat_id=admin_id,
                text=caption,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_to_message_id=forwarded.message_id,
            )
        except Exception:
            pass

    await message.answer(
        f"✅ Отримано ({sent_count}). Якщо є ще файли — надішліть, інакше /done."
    )


@router.callback_query(F.data.regexp(r"^cancel_booking_\d+$"))
async def cancel_booking_warn(callback: CallbackQuery, session: AsyncSession):
    """Перший крок скасування — попередження з умовами + підтвердження."""
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    booking = await session.get(Booking, booking_id)
    if not booking:
        await callback.answer("Бронювання не знайдено", show_alert=True)
        return

    practice = await session.get(Practice, booking.practice_id)
    schedule = await session.get(PracticeSchedule, booking.schedule_id)

    # Якщо менш ніж за 48 годин до практики — додаємо попередження
    late_warning = ""
    if schedule and schedule.datetime - datetime.utcnow() < timedelta(hours=48):
        late_warning = (
            "\n\n⚠️ <b>УВАГА:</b> до практики залишилось менш ніж 2 дні.\n"
            "За правилами скасування у цьому випадку <b>50% передоплати утримується</b> "
            "як компенсація за заброньоване місце і не повертається."
        )

    date_str = schedule.datetime.strftime("%d.%m.%Y о %H:%M") if schedule else "—"
    text = (
        "❌ <b>СКАСУВАННЯ БРОНЮВАННЯ</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"🪷  <b>{practice.title if practice else '?'}</b>\n"
        f"📅  {date_str}\n"
        f"💰  {int(practice.price) if practice else 0} грн"
        f"{late_warning}\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"{CANCELLATION_POLICY.strip()}\n\n"
        "Ви впевнені, що хочете скасувати бронювання?"
    )

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="✅  Так, скасувати",
        callback_data=f"cancelconfirm_{booking_id}",
    ))
    kb.row(InlineKeyboardButton(
        text="◀️  Ні, повернутися",
        callback_data="main_menu",
    ))

    await callback.message.edit_text(
        text=text,
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancelconfirm_"))
async def cancel_booking_confirm(callback: CallbackQuery, session: AsyncSession):
    """Реальне скасування після підтвердження."""
    booking_id = int(callback.data.replace("cancelconfirm_", ""))
    booking = await session.get(Booking, booking_id)
    if not booking:
        await callback.answer("Бронювання не знайдено", show_alert=True)
        return

    schedule = await session.get(PracticeSchedule, booking.schedule_id)
    if schedule and booking.status != BookingStatus.CANCELLED:
        schedule.available_slots += 1
        schedule.is_available = True

    booking.status = BookingStatus.CANCELLED
    await session.commit()

    await callback.message.edit_text(
        "❌ <b>Бронювання скасовано</b>\n\n"
        "Ви можете обрати іншу практику або інший час.",
        reply_markup=get_back_to_main_menu(),
        parse_mode="HTML",
    )
    await callback.answer("Бронювання скасовано")
