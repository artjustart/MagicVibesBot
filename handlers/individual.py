"""
Обробники індивідуальних сесій
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from database.models import (
    Practice, Booking, Payment, User,
    PracticeType, BookingStatus, PaymentStatus, PracticeSchedule,
)
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards.inline import (
    get_individual_session_keyboard,
    get_back_to_main_menu,
)
from services.requisites import format_requisites, format_purpose_for_booking
from services.notifications import notify_new_individual_request
from content.texts import INDIVIDUAL_DESCRIPTION

router = Router()


class IndividualSessionStates(StatesGroup):
    waiting_for_datetime = State()
    waiting_for_notes = State()


@router.callback_query(F.data == "individual_session")
async def show_individual_session_info(callback: CallbackQuery, session: AsyncSession):
    """Інформація про індивідуальні сесії"""
    result = await session.execute(
        select(Practice).where(
            Practice.is_active == True,
            Practice.practice_type == PracticeType.INDIVIDUAL,
        ).limit(1)
    )
    practice = result.scalar_one_or_none()

    if practice:
        text = (
            f"{INDIVIDUAL_DESCRIPTION}\n\n"
            "━━━━━━━━━━━━━━━━━\n"
            f"⏱  <b>Тривалість:</b>  {practice.duration_minutes} хв\n"
            f"💰  <b>Вартість:</b>  {int(practice.price)} грн\n\n"
            "👇 Оберіть зручний час або напишіть менеджеру:"
        )
    else:
        text = INDIVIDUAL_DESCRIPTION

    await callback.message.edit_text(
        text=text,
        reply_markup=get_individual_session_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "individual_choose_datetime")
async def choose_individual_datetime(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Вибір дати і часу для індивідуальної сесії"""
    result = await session.execute(
        select(Practice).where(
            Practice.is_active == True,
            Practice.practice_type == PracticeType.INDIVIDUAL,
        ).limit(1)
    )
    practice = result.scalar_one_or_none()

    if not practice:
        await callback.answer("Індивідуальні сесії тимчасово недоступні", show_alert=True)
        return

    await state.update_data(practice_id=practice.id)
    await state.set_state(IndividualSessionStates.waiting_for_datetime)

    text = """
📅 <b>Вибір дати і часу</b>

Будь ласка, напишіть бажану дату та час у форматі:

<code>ДД.ММ.РРРР ГГ:ХХ</code>

Наприклад: <code>25.05.2026 15:00</code>

Ми перевіримо доступність і звʼяжемося з вами для підтвердження.
"""

    await callback.message.edit_text(
        text=text,
        reply_markup=get_back_to_main_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IndividualSessionStates.waiting_for_datetime)
async def process_individual_datetime(message: Message, state: FSMContext, session: AsyncSession, config):
    """Обробка введеної дати і часу"""
    try:
        desired_datetime = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")

        if desired_datetime <= datetime.now():
            await message.answer(
                "❌ Будь ласка, вкажіть дату в майбутньому.",
                reply_markup=get_back_to_main_menu(),
            )
            return

        data = await state.get_data()
        practice_id = data.get("practice_id")

        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one()

        practice = await session.get(Practice, practice_id)

        schedule = PracticeSchedule(
            practice_id=practice_id,
            datetime=desired_datetime,
            available_slots=1,
            is_available=True,
        )
        session.add(schedule)
        await session.flush()

        booking = Booking(
            user_id=user.id,
            practice_id=practice_id,
            schedule_id=schedule.id,
            status=BookingStatus.PENDING,
            notes=f"Запит на індивідуальну сесію: {message.text}",
        )
        session.add(booking)

        schedule.available_slots = 0
        schedule.is_available = False

        await session.commit()
        await session.refresh(booking)

        # Уведомляем админов про заявку на индивидуальную
        try:
            await notify_new_individual_request(message.bot, config.tg_bot.admin_ids, session, booking.id)
        except Exception:
            pass

        await state.clear()

        date_str = desired_datetime.strftime("%d.%m.%Y о %H:%M")
        purpose = format_purpose_for_booking(practice.title, date_str, user.full_name or "")

        # Спочатку — підтвердження запиту
        await message.answer(
            f"""
✅ <b>Запит на індивідуальну сесію створено!</b>

📅  <b>Бажана дата і час:</b> {date_str}
⏱  <b>Тривалість:</b> {practice.duration_minutes} хв
💰  <b>Вартість:</b> {int(practice.price)} грн

━━━━━━━━━━━━━━━━━
Ми перевіримо доступність цього часу і звʼяжемося з вами для підтвердження.
""",
            parse_mode="HTML",
        )

        # Потім — реквізити для оплати
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(
            text="📸  Я сплатив(ла) — надіслати квитанцію",
            callback_data=f"proof_booking_{booking.id}",
        ))
        kb.row(InlineKeyboardButton(text="◀️  До головного меню", callback_data="main_menu"))

        await message.answer(
            text=format_requisites(purpose),
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )

    except ValueError:
        await message.answer(
            """
❌ <b>Невірний формат дати</b>

Будь ласка, використовуйте формат: <code>ДД.ММ.РРРР ГГ:ХХ</code>

Наприклад: <code>25.05.2026 15:00</code>
""",
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML",
        )


async def admin_confirm_individual_session(booking_id: int, session: AsyncSession, bot):
    """
    Підтвердження індивідуальної сесії менеджером (для майбутньої адмінки).
    """
    booking = await session.get(Booking, booking_id)
    if not booking:
        return False

    practice = await session.get(Practice, booking.practice_id)
    schedule = await session.get(PracticeSchedule, booking.schedule_id)
    user = await session.get(User, booking.user_id)

    date_str = schedule.datetime.strftime("%d.%m.%Y о %H:%M")

    text = f"""
✅ <b>Вашу індивідуальну сесію підтверджено!</b>

📅  <b>Дата і час:</b> {date_str}
⏱  <b>Тривалість:</b> {practice.duration_minutes} хв
💰  <b>Вартість:</b> {int(practice.price)} грн

Тепер ви можете перейти до оплати.
"""

    from services.monopay import MonoPayService
    from config.settings import load_config

    config = load_config()
    mono_service = MonoPayService(config.monopay.token, config.monopay.merchant_id)

    payment = Payment(
        user_id=booking.user_id,
        booking_id=booking.id,
        amount=practice.price,
        currency="UAH",
        status=PaymentStatus.PENDING,
        payment_provider="monopay",
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)

    description = f"Індивідуальна сесія - {date_str}"
    invoice = await mono_service.create_invoice(
        amount=practice.price,
        description=description,
        reference=f"payment_{payment.id}",
    )

    if invoice["success"]:
        payment.transaction_id = invoice["invoice_id"]
        payment.payment_url = invoice["payment_url"]
        await session.commit()

        await bot.send_message(
            chat_id=user.telegram_id,
            text=text,
            reply_markup=get_payment_keyboard(payment.payment_url, payment.id),
            parse_mode="HTML",
        )

        return True

    return False
