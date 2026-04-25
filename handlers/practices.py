"""
Обработчики записи на групповые практики
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta

from database.models import Practice, PracticeSchedule, Booking, Payment, User, PracticeType, BookingStatus, PaymentStatus
from keyboards.inline import (
    get_practices_keyboard,
    get_practice_schedule_keyboard,
    get_booking_confirmation_keyboard,
    get_payment_keyboard,
    get_back_to_main_menu
)
from services.monopay import MonoPayService

router = Router()

class BookingStates(StatesGroup):
    waiting_for_notes = State()

@router.callback_query(F.data == "practices_list")
async def show_practices_list(callback: CallbackQuery, session: AsyncSession):
    """Показ списка актуальных практик"""
    
    # Получаем активные групповые практики
    result = await session.execute(
        select(Practice).where(
            Practice.is_active == True,
            Practice.practice_type == PracticeType.GROUP
        )
    )
    practices = result.scalars().all()
    
    if practices:
        text = """
📅 <b>Актуальные практики</b>

Выберите практику для просмотра расписания и записи:
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_practices_keyboard(practices),
            parse_mode="HTML"
        )
    else:
        text = """
📅 <b>Актуальные практики</b>

К сожалению, сейчас нет доступных практик.
Следите за обновлениями!
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("practice_"))
async def show_practice_schedule(callback: CallbackQuery, session: AsyncSession):
    """Показ расписания конкретной практики"""
    
    practice_id = int(callback.data.replace("practice_", ""))
    
    # Получаем практику
    practice = await session.get(Practice, practice_id)
    
    if not practice:
        await callback.answer("Практика не найдена", show_alert=True)
        return
    
    # Получаем доступное расписание (с текущей даты)
    result = await session.execute(
        select(PracticeSchedule).where(
            PracticeSchedule.practice_id == practice_id,
            PracticeSchedule.is_available == True,
            PracticeSchedule.datetime >= datetime.utcnow(),
            PracticeSchedule.available_slots > 0
        ).order_by(PracticeSchedule.datetime)
    )
    schedules = result.scalars().all()
    
    if schedules:
        text = f"""
🧘‍♀️ <b>{practice.title}</b>

{practice.description}

⏱ <b>Длительность:</b> {practice.duration_minutes} минут
💰 <b>Стоимость:</b> {practice.price} грн
👥 <b>Макс. участников:</b> {practice.max_participants}

Выберите удобное время:
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_practice_schedule_keyboard(schedules, practice_id),
            parse_mode="HTML"
        )
    else:
        text = f"""
🧘‍♀️ <b>{practice.title}</b>

{practice.description}

К сожалению, сейчас нет доступных дат для этой практики.
Свяжитесь с менеджером для уточнения расписания.
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("book_"))
async def create_booking(callback: CallbackQuery, session: AsyncSession):
    """Создание бронирования"""
    
    schedule_id = int(callback.data.replace("book_", ""))
    
    # Получаем расписание
    schedule = await session.get(PracticeSchedule, schedule_id)
    
    if not schedule or not schedule.is_available or schedule.available_slots <= 0:
        await callback.answer("Это время уже недоступно", show_alert=True)
        return
    
    # Получаем практику
    practice = await session.get(Practice, schedule.practice_id)
    
    # Получаем пользователя
    result = await session.execute(
        select(User).where(User.telegram_id == callback.from_user.id)
    )
    user = result.scalar_one()
    
    # Создаем бронирование
    booking = Booking(
        user_id=user.id,
        practice_id=practice.id,
        schedule_id=schedule.id,
        status=BookingStatus.PENDING
    )
    session.add(booking)
    
    # Уменьшаем количество доступных мест
    schedule.available_slots -= 1
    if schedule.available_slots == 0:
        schedule.is_available = False
    
    await session.commit()
    await session.refresh(booking)
    
    # Формируем сообщение
    date_str = schedule.datetime.strftime("%d.%m.%Y в %H:%M")
    text = f"""
✅ <b>Бронирование создано!</b>

🧘‍♀️ <b>Практика:</b> {practice.title}
📅 <b>Дата и время:</b> {date_str}
⏱ <b>Длительность:</b> {practice.duration_minutes} минут
💰 <b>Стоимость:</b> {practice.price} грн

Подтвердите бронирование и перейдите к оплате:
"""
    
    await callback.message.edit_text(
        text=text,
        reply_markup=get_booking_confirmation_keyboard(booking.id),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_booking_"))
async def confirm_booking_and_pay(callback: CallbackQuery, session: AsyncSession, mono_service: MonoPayService):
    """Подтверждение бронирования и создание платежа"""
    
    booking_id = int(callback.data.replace("confirm_booking_", ""))
    
    # Получаем бронирование с релейшенами
    result = await session.execute(
        select(Booking).where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        await callback.answer("Бронирование не найдено", show_alert=True)
        return
    
    # Получаем связанные данные
    practice = await session.get(Practice, booking.practice_id)
    schedule = await session.get(PracticeSchedule, booking.schedule_id)
    
    # Создаем платеж
    payment = Payment(
        user_id=booking.user_id,
        booking_id=booking.id,
        amount=practice.price,
        currency="UAH",
        status=PaymentStatus.PENDING,
        payment_provider="monopay"
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    
    # Создаем инвойс в MonoPay
    date_str = schedule.datetime.strftime("%d.%m.%Y %H:%M")
    description = f"Практика '{practice.title}' - {date_str}"
    
    invoice = await mono_service.create_invoice(
        amount=practice.price,
        description=description,
        reference=f"payment_{payment.id}",
        webhook_url=f"https://your-domain.com/webhook/monopay"  # Замените на свой домен
    )
    
    if invoice["success"]:
        # Сохраняем данные платежа
        payment.transaction_id = invoice["invoice_id"]
        payment.payment_url = invoice["payment_url"]
        await session.commit()
        
        text = f"""
💳 <b>Переход к оплате</b>

🧘‍♀️ <b>Практика:</b> {practice.title}
📅 <b>Дата:</b> {date_str}
💰 <b>К оплате:</b> {practice.price} грн

Нажмите кнопку ниже для оплаты через MonoPay.
После оплаты нажмите "Я оплатил(а)" для проверки статуса.
"""
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_payment_keyboard(payment.payment_url, payment.id),
            parse_mode="HTML"
        )
    else:
        text = f"""
❌ <b>Ошибка создания платежа</b>

Произошла ошибка при создании платежа.
Пожалуйста, свяжитесь с менеджером или попробуйте позже.

Ошибка: {invoice.get('error', 'Неизвестная ошибка')}
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery, session: AsyncSession, mono_service: MonoPayService):
    """Проверка статуса платежа"""
    
    payment_id = int(callback.data.replace("check_payment_", ""))
    
    # Получаем платеж
    payment = await session.get(Payment, payment_id)
    
    if not payment:
        await callback.answer("Платеж не найден", show_alert=True)
        return
    
    # Проверяем статус в MonoPay
    status_result = await mono_service.check_payment_status(payment.transaction_id)
    
    if status_result["success"]:
        if status_result["paid"]:
            # Обновляем статус платежа
            payment.status = PaymentStatus.SUCCESS
            payment.paid_at = datetime.utcnow()
            
            # Подтверждаем бронирование
            booking = await session.get(Booking, payment.booking_id)
            booking.status = BookingStatus.CONFIRMED
            
            await session.commit()
            
            # Получаем данные для сообщения
            practice = await session.get(Practice, booking.practice_id)
            schedule = await session.get(PracticeSchedule, booking.schedule_id)
            date_str = schedule.datetime.strftime("%d.%m.%Y в %H:%M")
            
            text = f"""
✅ <b>Оплата прошла успешно!</b>

Ваше бронирование подтверждено:

🧘‍♀️ <b>Практика:</b> {practice.title}
📅 <b>Дата и время:</b> {date_str}
📍 <b>Адрес:</b> [будет отправлен дополнительно]

Ждем вас! За 24 часа до практики мы пришлем вам напоминание.

Если у вас возникнут вопросы, свяжитесь с менеджером.
"""
            
            await callback.message.edit_text(
                text=text,
                reply_markup=get_back_to_main_menu(),
                parse_mode="HTML"
            )
            await callback.answer("✅ Оплата подтверждена!", show_alert=True)
        else:
            await callback.answer(
                "⏳ Платеж еще не обработан. Пожалуйста, подождите немного и попробуйте снова.",
                show_alert=True
            )
    else:
        await callback.answer(
            "❌ Ошибка при проверке платежа. Попробуйте позже или свяжитесь с менеджером.",
            show_alert=True
        )

@router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: CallbackQuery, session: AsyncSession):
    """Отмена бронирования"""
    
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    
    # Получаем бронирование
    booking = await session.get(Booking, booking_id)
    
    if booking:
        # Возвращаем место в расписание
        schedule = await session.get(PracticeSchedule, booking.schedule_id)
        schedule.available_slots += 1
        schedule.is_available = True
        
        # Отменяем бронирование
        booking.status = BookingStatus.CANCELLED
        
        await session.commit()
        
        text = """
❌ <b>Бронирование отменено</b>

Вы можете выбрать другую практику или время.
"""
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML"
        )
        await callback.answer("Бронирование отменено")
    else:
        await callback.answer("Бронирование не найдено", show_alert=True)
