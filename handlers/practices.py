"""
Обробники запису на групові практики
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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
    get_payment_keyboard,
    get_back_to_main_menu,
)
from services.monopay import MonoPayService

router = Router()


class BookingStates(StatesGroup):
    waiting_for_notes = State()


@router.callback_query(F.data == "practices_list")
async def show_practices_list(callback: CallbackQuery, session: AsyncSession):
    """Список актуальних групових практик"""
    result = await session.execute(
        select(Practice).where(
            Practice.is_active == True,
            Practice.practice_type == PracticeType.GROUP,
        )
    )
    practices = result.scalars().all()

    if practices:
        text = """
🪷 <b>Актуальні практики</b>

Оберіть практику, щоб переглянути опис, розклад і записатися:
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_practices_keyboard(practices),
            parse_mode="HTML",
        )
    else:
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


@router.callback_query(F.data.startswith("practice_"))
async def show_practice_schedule(callback: CallbackQuery, session: AsyncSession):
    """Розклад конкретної практики"""
    practice_id = int(callback.data.replace("practice_", ""))
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
        text = f"""
{practice.description}

━━━━━━━━━━━━━━━━━
⏱  <b>Тривалість:</b> {practice.duration_minutes} хв
💰  <b>Вартість:</b> {int(practice.price)} грн
👥  <b>Максимум учасників:</b> {practice.max_participants}

📅 <b>Оберіть зручну дату:</b>
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_practice_schedule_keyboard(schedules, practice_id),
            parse_mode="HTML",
        )
    else:
        text = f"""
{practice.description}

━━━━━━━━━━━━━━━━━
На жаль, зараз немає доступних дат.
Звʼяжіться з менеджером, щоб уточнити розклад.
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML",
        )

    await callback.answer()


@router.callback_query(F.data.startswith("book_"))
async def create_booking(callback: CallbackQuery, session: AsyncSession):
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
async def confirm_booking_and_pay(callback: CallbackQuery, session: AsyncSession, mono_service: MonoPayService):
    """Підтвердження бронювання та створення платежу"""
    booking_id = int(callback.data.replace("confirm_booking_", ""))

    result = await session.execute(
        select(Booking).where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()

    if not booking:
        await callback.answer("Бронювання не знайдено", show_alert=True)
        return

    practice = await session.get(Practice, booking.practice_id)
    schedule = await session.get(PracticeSchedule, booking.schedule_id)

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

    date_str = schedule.datetime.strftime("%d.%m.%Y %H:%M")
    description = f"Практика '{practice.title}' - {date_str}"

    invoice = await mono_service.create_invoice(
        amount=practice.price,
        description=description,
        reference=f"payment_{payment.id}",
        webhook_url="https://your-domain.com/webhook/monopay",
    )

    if invoice["success"]:
        payment.transaction_id = invoice["invoice_id"]
        payment.payment_url = invoice["payment_url"]
        await session.commit()

        text = f"""
💳 <b>Перехід до оплати</b>

🪷  <b>Практика:</b> {practice.title}
📅  <b>Дата:</b> {date_str}
💰  <b>До сплати:</b> {int(practice.price)} грн

━━━━━━━━━━━━━━━━━
Натисніть кнопку нижче, щоб сплатити через MonoPay.
Після оплати натисніть «✅ Я сплатив(ла)» для перевірки статусу.
"""

        await callback.message.edit_text(
            text=text,
            reply_markup=get_payment_keyboard(payment.payment_url, payment.id),
            parse_mode="HTML",
        )
    else:
        text = f"""
❌ <b>Помилка створення платежу</b>

Виникла помилка під час створення платежу.
Будь ласка, звʼяжіться з менеджером або спробуйте пізніше.

Помилка: {invoice.get('error', 'Невідома помилка')}
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML",
        )

    await callback.answer()


@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery, session: AsyncSession, mono_service: MonoPayService):
    """Перевірка статусу платежу"""
    payment_id = int(callback.data.replace("check_payment_", ""))
    payment = await session.get(Payment, payment_id)

    if not payment:
        await callback.answer("Платіж не знайдено", show_alert=True)
        return

    status_result = await mono_service.check_payment_status(payment.transaction_id)

    if status_result["success"]:
        if status_result["paid"]:
            payment.status = PaymentStatus.SUCCESS
            payment.paid_at = datetime.utcnow()

            booking = await session.get(Booking, payment.booking_id)
            booking.status = BookingStatus.CONFIRMED

            await session.commit()

            practice = await session.get(Practice, booking.practice_id)
            schedule = await session.get(PracticeSchedule, booking.schedule_id)
            date_str = schedule.datetime.strftime("%d.%m.%Y о %H:%M")

            text = f"""
✅ <b>Оплата пройшла успішно!</b>

Ваше бронювання підтверджено:

🪷  <b>Практика:</b> {practice.title}
📅  <b>Дата і час:</b> {date_str}
📍  <b>Адреса:</b> Київ, вул. Рейтарська, 13

━━━━━━━━━━━━━━━━━
Чекаємо на вас! За 24 години до практики ми надішлемо нагадування.

Якщо будуть питання — натисніть «💬 Звʼязатися з менеджером» 🤍
"""

            await callback.message.edit_text(
                text=text,
                reply_markup=get_back_to_main_menu(),
                parse_mode="HTML",
            )
            await callback.answer("✅ Оплату підтверджено!", show_alert=True)
        else:
            await callback.answer(
                "⏳ Платіж ще не оброблено. Зачекайте трохи та спробуйте знову.",
                show_alert=True,
            )
    else:
        await callback.answer(
            "❌ Помилка перевірки платежу. Спробуйте пізніше або звʼяжіться з менеджером.",
            show_alert=True,
        )


@router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: CallbackQuery, session: AsyncSession):
    """Скасування бронювання"""
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    booking = await session.get(Booking, booking_id)

    if booking:
        schedule = await session.get(PracticeSchedule, booking.schedule_id)
        schedule.available_slots += 1
        schedule.is_available = True

        booking.status = BookingStatus.CANCELLED
        await session.commit()

        text = """
❌ <b>Бронювання скасовано</b>

Ви можете обрати іншу практику або інший час.
"""

        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML",
        )
        await callback.answer("Бронювання скасовано")
    else:
        await callback.answer("Бронювання не знайдено", show_alert=True)
