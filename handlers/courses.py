"""
Обработчики курсов (Стартовый и 3-месячное обучение)
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta

from database.models import Course, CourseEnrollment, Payment, User, CourseType, PaymentStatus
from keyboards.inline import (
    get_courses_keyboard,
    get_course_enrollment_keyboard,
    get_payment_keyboard,
    get_back_to_main_menu
)
from services.monopay import MonoPayService

router = Router()

@router.callback_query(F.data == "starter_course")
async def show_starter_course(callback: CallbackQuery, session: AsyncSession):
    """Показ стартового онлайн-курса"""
    
    # Получаем стартовый курс
    result = await session.execute(
        select(Course).where(
            Course.is_active == True,
            Course.course_type == CourseType.STARTER
        ).limit(1)
    )
    course = result.scalar_one_or_none()
    
    if course:
        text = f"""
🎓 <b>{course.title}</b>

{course.description}

⏱ <b>Длительность:</b> {course.duration_days} дней
💰 <b>Стоимость:</b> {course.price} грн

<b>Что входит в курс:</b>
• Доступ ко всем материалам курса
• Практические задания
• Поддержка куратора
• Сертификат по окончании

После оплаты вы сразу получите доступ к материалам.
"""
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_course_enrollment_keyboard(course.id),
            parse_mode="HTML"
        )
    else:
        text = """
🎓 <b>Стартовый онлайн-курс</b>

К сожалению, курс временно недоступен.
Свяжитесь с менеджером для получения дополнительной информации.
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()

@router.callback_query(F.data == "three_month_course")
async def show_three_month_course(callback: CallbackQuery, session: AsyncSession):
    """Показ 3-месячного курса обучения"""
    
    # Получаем 3-месячный курс
    result = await session.execute(
        select(Course).where(
            Course.is_active == True,
            Course.course_type == CourseType.THREE_MONTH
        ).limit(1)
    )
    course = result.scalar_one_or_none()
    
    if course:
        text = f"""
📚 <b>{course.title}</b>

{course.description}

⏱ <b>Длительность:</b> {course.duration_days} дней (3 месяца)
💰 <b>Стоимость:</b> {course.price} грн

<b>Программа обучения включает:</b>
• Еженедельные живые сессии
• Доступ к записям всех занятий
• Индивидуальные консультации
• Домашние задания с проверкой
• Работа в группе единомышленников
• Персональный план развития
• Сертификат по окончании

Это полноценная программа для глубокой трансформации!
"""
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_course_enrollment_keyboard(course.id),
            parse_mode="HTML"
        )
    else:
        text = """
📚 <b>Обучение 3 месяца</b>

К сожалению, набор на курс сейчас закрыт.
Свяжитесь с менеджером для записи в лист ожидания.
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("course_details_"))
async def show_course_details(callback: CallbackQuery, session: AsyncSession):
    """Подробная информация о курсе"""
    
    course_id = int(callback.data.replace("course_details_", ""))
    course = await session.get(Course, course_id)
    
    if not course:
        await callback.answer("Курс не найден", show_alert=True)
        return
    
    # Получаем количество материалов
    result = await session.execute(
        select(Course).where(Course.id == course_id)
    )
    
    text = f"""
📖 <b>Подробнее о курсе</b>

<b>{course.title}</b>

{course.description}

⏱ <b>Продолжительность:</b> {course.duration_days} дней
💰 <b>Инвестиция в себя:</b> {course.price} грн

<b>Формат обучения:</b>
• Онлайн в удобное время
• Доступ к платформе 24/7
• Практические материалы
• Обратная связь от кураторов

Готовы начать свой путь?
"""
    
    await callback.message.edit_text(
        text=text,
        reply_markup=get_course_enrollment_keyboard(course.id),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("enroll_course_"))
async def enroll_in_course(callback: CallbackQuery, session: AsyncSession, mono_service: MonoPayService):
    """Запись на курс и создание платежа"""
    
    course_id = int(callback.data.replace("enroll_course_", ""))
    
    # Получаем курс
    course = await session.get(Course, course_id)
    
    if not course or not course.is_active:
        await callback.answer("Курс недоступен", show_alert=True)
        return
    
    # Получаем пользователя
    result = await session.execute(
        select(User).where(User.telegram_id == callback.from_user.id)
    )
    user = result.scalar_one()
    
    # Проверяем, не записан ли уже пользователь
    result = await session.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.user_id == user.id,
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.is_active == True
        )
    )
    existing_enrollment = result.scalar_one_or_none()
    
    if existing_enrollment:
        await callback.answer("Вы уже записаны на этот курс!", show_alert=True)
        return
    
    # Создаем запись на курс
    expires_at = datetime.utcnow() + timedelta(days=course.duration_days)
    enrollment = CourseEnrollment(
        user_id=user.id,
        course_id=course_id,
        expires_at=expires_at,
        is_active=False  # Станет активным после оплаты
    )
    session.add(enrollment)
    await session.commit()
    await session.refresh(enrollment)
    
    # Создаем платеж
    payment = Payment(
        user_id=user.id,
        course_enrollment_id=enrollment.id,
        amount=course.price,
        currency="UAH",
        status=PaymentStatus.PENDING,
        payment_provider="monopay"
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    
    # Создаем инвойс в MonoPay
    description = f"Курс '{course.title}'"
    
    invoice = await mono_service.create_invoice(
        amount=course.price,
        description=description,
        reference=f"payment_{payment.id}",
        webhook_url=f"https://your-domain.com/webhook/monopay"
    )
    
    if invoice["success"]:
        # Сохраняем данные платежа
        payment.transaction_id = invoice["invoice_id"]
        payment.payment_url = invoice["payment_url"]
        await session.commit()
        
        text = f"""
💳 <b>Переход к оплате курса</b>

📚 <b>Курс:</b> {course.title}
⏱ <b>Длительность:</b> {course.duration_days} дней
💰 <b>К оплате:</b> {course.price} грн

После успешной оплаты вы сразу получите доступ ко всем материалам курса!

Нажмите кнопку ниже для оплаты через MonoPay.
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
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()

# Функция активации доступа к курсу после оплаты
async def activate_course_access(payment_id: int, session: AsyncSession, bot):
    """
    Активация доступа к курсу после успешной оплаты
    Вызывается из webhook обработчика или при проверке статуса платежа
    """
    
    payment = await session.get(Payment, payment_id)
    
    if not payment or payment.status != PaymentStatus.SUCCESS:
        return False
    
    # Получаем запись на курс
    enrollment = await session.get(CourseEnrollment, payment.course_enrollment_id)
    
    if not enrollment:
        return False
    
    # Активируем доступ
    enrollment.is_active = True
    await session.commit()
    
    # Получаем данные для отправки материалов
    course = await session.get(Course, enrollment.course_id)
    user = await session.get(User, enrollment.user_id)
    
    # Отправляем пользователю подтверждение и первые материалы
    text = f"""
✅ <b>Добро пожаловать на курс!</b>

Поздравляем! Вы успешно записались на курс <b>"{course.title}"</b>

📚 Доступ к материалам активирован до {enrollment.expires_at.strftime("%d.%m.%Y")}

Сейчас мы отправим вам первые материалы для изучения.

Приятного обучения! 🎓
"""
    
    await bot.send_message(
        chat_id=user.telegram_id,
        text=text,
        parse_mode="HTML"
    )
    
    # Отправляем материалы курса
    from database.models import CourseMaterial
    
    result = await session.execute(
        select(CourseMaterial).where(
            CourseMaterial.course_id == course.id
        ).order_by(CourseMaterial.order)
    )
    materials = result.scalars().all()
    
    for material in materials:
        try:
            if material.file_type == "document":
                await bot.send_document(
                    chat_id=user.telegram_id,
                    document=material.file_id,
                    caption=material.title
                )
            elif material.file_type == "video":
                await bot.send_video(
                    chat_id=user.telegram_id,
                    video=material.file_id,
                    caption=material.title
                )
            elif material.file_type == "audio":
                await bot.send_audio(
                    chat_id=user.telegram_id,
                    audio=material.file_id,
                    caption=material.title
                )
        except Exception as e:
            print(f"Error sending material {material.id}: {e}")
    
    return True
