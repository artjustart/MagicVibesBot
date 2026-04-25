"""
Обработчики индивидуальных сессий
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from database.models import Practice, Booking, Payment, User, PracticeType, BookingStatus, PaymentStatus, PracticeSchedule
from keyboards.inline import (
    get_individual_session_keyboard,
    get_booking_confirmation_keyboard,
    get_payment_keyboard,
    get_back_to_main_menu
)
from services.monopay import MonoPayService

router = Router()

class IndividualSessionStates(StatesGroup):
    waiting_for_datetime = State()
    waiting_for_notes = State()

@router.callback_query(F.data == "individual_session")
async def show_individual_session_info(callback: CallbackQuery, session: AsyncSession):
    """Показ информации об индивидуальных сессиях"""
    
    # Получаем индивидуальную практику
    result = await session.execute(
        select(Practice).where(
            Practice.is_active == True,
            Practice.practice_type == PracticeType.INDIVIDUAL
        ).limit(1)
    )
    practice = result.scalar_one_or_none()
    
    if practice:
        text = f"""
🧘‍♀️ <b>Индивидуальная сессия</b>

{practice.description}

⏱ <b>Длительность:</b> {practice.duration_minutes} минут
💰 <b>Стоимость:</b> {practice.price} грн

<b>Что входит в сессию:</b>
• Персональная работа с практиком
• Разработка индивидуального плана
• Подробная обратная связь
• Запись сессии (по желанию)

Вы можете выбрать удобное время или написать менеджеру для уточнения деталей.
"""
    else:
        # Если практики нет в БД, показываем общую информацию
        text = """
🧘‍♀️ <b>Индивидуальная сессия</b>

Персональная работа один-на-один с практиком.

<b>Что входит в сессию:</b>
• Работа с вашими запросами
• Индивидуальный подход
• Глубокая проработка
• Обратная связь

Для записи свяжитесь с менеджером для уточнения деталей и выбора удобного времени.
"""
    
    await callback.message.edit_text(
        text=text,
        reply_markup=get_individual_session_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "individual_choose_datetime")
async def choose_individual_datetime(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Выбор даты и времени для индивидуальной сессии"""
    
    # Получаем индивидуальную практику
    result = await session.execute(
        select(Practice).where(
            Practice.is_active == True,
            Practice.practice_type == PracticeType.INDIVIDUAL
        ).limit(1)
    )
    practice = result.scalar_one_or_none()
    
    if not practice:
        await callback.answer("Индивидуальные сессии временно недоступны", show_alert=True)
        return
    
    # Сохраняем ID практики в состоянии
    await state.update_data(practice_id=practice.id)
    await state.set_state(IndividualSessionStates.waiting_for_datetime)
    
    text = """
📅 <b>Выбор даты и времени</b>

Пожалуйста, напишите желаемую дату и время в формате:

<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>

Например: <code>25.12.2024 15:00</code>

Мы проверим доступность и свяжемся с вами для подтверждения.
"""
    
    await callback.message.edit_text(
        text=text,
        reply_markup=get_back_to_main_menu(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(IndividualSessionStates.waiting_for_datetime)
async def process_individual_datetime(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка введенной даты и времени"""
    
    try:
        # Парсим дату
        desired_datetime = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        
        # Проверяем, что дата в будущем
        if desired_datetime <= datetime.now():
            await message.answer(
                "❌ Пожалуйста, укажите дату в будущем.",
                reply_markup=get_back_to_main_menu()
            )
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        practice_id = data.get("practice_id")
        
        # Получаем пользователя
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one()
        
        # Получаем практику
        practice = await session.get(Practice, practice_id)
        
        # Создаем расписание для индивидуальной сессии
        schedule = PracticeSchedule(
            practice_id=practice_id,
            datetime=desired_datetime,
            available_slots=1,
            is_available=True
        )
        session.add(schedule)
        await session.flush()
        
        # Создаем бронирование
        booking = Booking(
            user_id=user.id,
            practice_id=practice_id,
            schedule_id=schedule.id,
            status=BookingStatus.PENDING,
            notes=f"Запрос на индивидуальную сессию: {message.text}"
        )
        session.add(booking)
        
        # Уменьшаем доступные слоты
        schedule.available_slots = 0
        schedule.is_available = False
        
        await session.commit()
        await session.refresh(booking)
        
        # Очищаем состояние
        await state.clear()
        
        # Формируем сообщение
        date_str = desired_datetime.strftime("%d.%m.%Y в %H:%M")
        text = f"""
✅ <b>Запрос на индивидуальную сессию создан!</b>

📅 <b>Желаемая дата и время:</b> {date_str}
⏱ <b>Длительность:</b> {practice.duration_minutes} минут
💰 <b>Стоимость:</b> {practice.price} грн

Мы проверим доступность этого времени и свяжемся с вами в ближайшее время.

После подтверждения времени менеджером вы сможете перейти к оплате.
"""
        
        await message.answer(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML"
        )
        
    except ValueError:
        await message.answer(
            """
❌ <b>Неверный формат даты</b>

Пожалуйста, используйте формат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>

Например: <code>25.12.2024 15:00</code>
""",
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML"
        )

# Webhook обработчик для подтверждения индивидуальной сессии менеджером
# (этот функционал можно расширить в админ-панели)

async def admin_confirm_individual_session(booking_id: int, session: AsyncSession, bot):
    """
    Функция для админа/менеджера для подтверждения индивидуальной сессии
    Вызывается из админ-панели (можно разработать отдельно)
    """
    
    booking = await session.get(Booking, booking_id)
    if not booking:
        return False
    
    practice = await session.get(Practice, booking.practice_id)
    schedule = await session.get(PracticeSchedule, booking.schedule_id)
    user = await session.get(User, booking.user_id)
    
    # Отправляем пользователю уведомление о подтверждении
    date_str = schedule.datetime.strftime("%d.%m.%Y в %H:%M")
    
    text = f"""
✅ <b>Ваша индивидуальная сессия подтверждена!</b>

📅 <b>Дата и время:</b> {date_str}
⏱ <b>Длительность:</b> {practice.duration_minutes} минут
💰 <b>Стоимость:</b> {practice.price} грн

Теперь вы можете перейти к оплате.
"""
    
    # Создаем платеж
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
        payment_provider="monopay"
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    
    # Создаем инвойс
    description = f"Индивидуальная сессия - {date_str}"
    invoice = await mono_service.create_invoice(
        amount=practice.price,
        description=description,
        reference=f"payment_{payment.id}"
    )
    
    if invoice["success"]:
        payment.transaction_id = invoice["invoice_id"]
        payment.payment_url = invoice["payment_url"]
        await session.commit()
        
        await bot.send_message(
            chat_id=user.telegram_id,
            text=text,
            reply_markup=get_payment_keyboard(payment.payment_url, payment.id),
            parse_mode="HTML"
        )
        
        return True
    
    return False
