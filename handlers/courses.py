"""
Обробники курсів (Стартовий та 3-місячне навчання)
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta

from database.models import Course, CourseEnrollment, Payment, User, CourseType, PaymentStatus
from keyboards.inline import (
    get_course_enrollment_keyboard,
    get_three_month_request_keyboard,
    get_payment_keyboard,
    get_back_to_main_menu,
)
from services.monopay import MonoPayService
from services.notifications import notify_new_course_request

router = Router()


@router.callback_query(F.data == "starter_course")
async def show_starter_course(callback: CallbackQuery, session: AsyncSession):
    """Стартовий онлайн-курс — поки в розробці"""
    result = await session.execute(
        select(Course).where(
            Course.is_active == True,
            Course.course_type == CourseType.STARTER,
        ).limit(1)
    )
    course = result.scalar_one_or_none()

    if False and course:  # Тимчасово відключено: курсу ще немає
        text = f"""
🌟 <b>{course.title}</b>

{course.description}

━━━━━━━━━━━━━━━━━
⏱  <b>Тривалість:</b> {course.duration_days} днів
💰  <b>Вартість:</b> {int(course.price)} грн

<b>Що входить у курс:</b>
• Доступ до всіх матеріалів курсу
• Практичні завдання
• Підтримка куратора
• Сертифікат після завершення

Після оплати ви одразу отримаєте доступ до матеріалів.
"""

        await callback.message.edit_text(
            text=text,
            reply_markup=get_course_enrollment_keyboard(course.id),
            parse_mode="HTML",
        )
    else:
        text = """
🌟 <b>Стартовий онлайн-курс</b>

🚧  Цей курс зараз у розробці.

Слідкуйте за оновленнями — скоро ми відкриємо доступ до повноцінного онлайн-курсу 🤍

Поки що ви можете:
• 🪷  Записатися на актуальну практику
• 🧘‍♀️  Замовити індивідуальну сесію
• 💬  Звʼязатися з менеджером для консультації
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML",
        )

    await callback.answer()


@router.callback_query(F.data == "three_month_course")
async def show_three_month_course(callback: CallbackQuery, session: AsyncSession):
    """3-місячний курс навчання"""
    result = await session.execute(
        select(Course).where(
            Course.is_active == True,
            Course.course_type == CourseType.THREE_MONTH,
        ).limit(1)
    )
    course = result.scalar_one_or_none()

    if course:
        text = f"""
📚 <b>{course.title}</b>

{course.description}

━━━━━━━━━━━━━━━━━
⏱  <b>Тривалість:</b> {course.duration_days} днів (3 місяці)
💰  <b>Вартість:</b> {int(course.price)} грн

<b>Програма навчання включає:</b>
• Щотижневі живі сесії
• Доступ до записів усіх занять
• Індивідуальні консультації
• Домашні завдання з перевіркою
• Робота в групі однодумців
• Персональний план розвитку
• Сертифікат після завершення

Це повноцінна програма для глибокої трансформації 💫

━━━━━━━━━━━━━━━━━
👇 <b>Залиште заявку</b> — наш менеджер звʼяжеться з вами найближчим часом, відповість на питання та підкаже наступні кроки.
"""

        await callback.message.edit_text(
            text=text,
            reply_markup=get_three_month_request_keyboard(),
            parse_mode="HTML",
        )
    else:
        text = """
📚 <b>Навчання 3 місяці</b>

На жаль, набір на курс зараз закритий.
Звʼяжіться з менеджером, щоб записатися в лист очікування.
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML",
        )

    await callback.answer()


@router.callback_query(F.data == "request_three_month")
async def request_three_month_course(callback: CallbackQuery, session: AsyncSession, config):
    """Заявка на 3-місячне навчання — без оплати, менеджер контактує сам."""
    result = await session.execute(
        select(Course).where(
            Course.is_active == True,
            Course.course_type == CourseType.THREE_MONTH,
        ).limit(1)
    )
    course = result.scalar_one_or_none()

    if not course:
        await callback.answer("Курс наразі недоступний", show_alert=True)
        return

    # Реєструємо/знаходимо користувача
    result = await session.execute(
        select(User).where(User.telegram_id == callback.from_user.id)
    )
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name or "",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    # Якщо вже є активна/відкрита заявка — не дублюємо
    existing = await session.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.user_id == user.id,
            CourseEnrollment.course_id == course.id,
        )
    )
    if existing.scalar_one_or_none():
        await callback.message.edit_text(
            "✅ <b>Заявку вже отримано!</b>\n\n"
            "Наш менеджер скоро звʼяжеться з вами 🤍",
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # Створюємо заявку (без оплати, is_active=False до підтвердження менеджером)
    enrollment = CourseEnrollment(
        user_id=user.id,
        course_id=course.id,
        is_active=False,
    )
    session.add(enrollment)
    await session.commit()
    await session.refresh(enrollment)

    # Уведомляем админов
    try:
        await notify_new_course_request(callback.bot, config.tg_bot.admin_ids, session, enrollment.id)
    except Exception:
        pass

    await callback.message.edit_text(
        f"""
✅ <b>Дякуємо! Вашу заявку отримано 🤍</b>

📚  <b>Курс:</b>  {course.title}

━━━━━━━━━━━━━━━━━
Наш менеджер звʼяжеться з вами найближчим часом, відповість на всі питання та допоможе зі стартом.

Гарного дня 🪷
""",
        reply_markup=get_back_to_main_menu(),
        parse_mode="HTML",
    )
    await callback.answer("Заявку надіслано")


@router.callback_query(F.data.startswith("course_details_"))
async def show_course_details(callback: CallbackQuery, session: AsyncSession):
    """Детальна інформація про курс"""
    course_id = int(callback.data.replace("course_details_", ""))
    course = await session.get(Course, course_id)

    if not course:
        await callback.answer("Курс не знайдено", show_alert=True)
        return

    text = f"""
📖 <b>Детальніше про курс</b>

<b>{course.title}</b>

{course.description}

━━━━━━━━━━━━━━━━━
⏱  <b>Тривалість:</b> {course.duration_days} днів
💰  <b>Інвестиція в себе:</b> {int(course.price)} грн

<b>Формат навчання:</b>
• Онлайн у зручний час
• Доступ до платформи 24/7
• Практичні матеріали
• Зворотний звʼязок від кураторів

Готові розпочати свій шлях?
"""

    await callback.message.edit_text(
        text=text,
        reply_markup=get_course_enrollment_keyboard(course.id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("enroll_course_"))
async def enroll_in_course(callback: CallbackQuery, session: AsyncSession, mono_service: MonoPayService):
    """Запис на курс і створення платежу"""
    course_id = int(callback.data.replace("enroll_course_", ""))
    course = await session.get(Course, course_id)

    if not course or not course.is_active:
        await callback.answer("Курс недоступний", show_alert=True)
        return

    result = await session.execute(
        select(User).where(User.telegram_id == callback.from_user.id)
    )
    user = result.scalar_one()

    result = await session.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.user_id == user.id,
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.is_active == True,
        )
    )
    existing_enrollment = result.scalar_one_or_none()

    if existing_enrollment:
        await callback.answer("Ви вже записані на цей курс!", show_alert=True)
        return

    expires_at = datetime.utcnow() + timedelta(days=course.duration_days)
    enrollment = CourseEnrollment(
        user_id=user.id,
        course_id=course_id,
        expires_at=expires_at,
        is_active=False,
    )
    session.add(enrollment)
    await session.commit()
    await session.refresh(enrollment)

    payment = Payment(
        user_id=user.id,
        course_enrollment_id=enrollment.id,
        amount=course.price,
        currency="UAH",
        status=PaymentStatus.PENDING,
        payment_provider="monopay",
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)

    description = f"Курс '{course.title}'"

    invoice = await mono_service.create_invoice(
        amount=course.price,
        description=description,
        reference=f"payment_{payment.id}",
        webhook_url="https://your-domain.com/webhook/monopay",
    )

    if invoice["success"]:
        payment.transaction_id = invoice["invoice_id"]
        payment.payment_url = invoice["payment_url"]
        await session.commit()

        text = f"""
💳 <b>Перехід до оплати курсу</b>

📚  <b>Курс:</b> {course.title}
⏱  <b>Тривалість:</b> {course.duration_days} днів
💰  <b>До сплати:</b> {int(course.price)} грн

━━━━━━━━━━━━━━━━━
Після успішної оплати ви одразу отримаєте доступ до всіх матеріалів курсу!
"""

        await callback.message.edit_text(
            text=text,
            reply_markup=get_payment_keyboard(payment.payment_url, payment.id),
            parse_mode="HTML",
        )
    else:
        text = """
❌ <b>Помилка створення платежу</b>

Виникла помилка під час створення платежу.
Будь ласка, звʼяжіться з менеджером або спробуйте пізніше.
"""
        await callback.message.edit_text(
            text=text,
            reply_markup=get_back_to_main_menu(),
            parse_mode="HTML",
        )

    await callback.answer()


async def activate_course_access(payment_id: int, session: AsyncSession, bot):
    """
    Активація доступу до курсу після успішної оплати.
    Викликається з webhook-обробника або під час перевірки статусу платежу.
    """
    payment = await session.get(Payment, payment_id)

    if not payment or payment.status != PaymentStatus.SUCCESS:
        return False

    enrollment = await session.get(CourseEnrollment, payment.course_enrollment_id)

    if not enrollment:
        return False

    enrollment.is_active = True
    await session.commit()

    course = await session.get(Course, enrollment.course_id)
    user = await session.get(User, enrollment.user_id)

    text = f"""
✅ <b>Ласкаво просимо на курс!</b>

Вітаємо! Ви успішно записалися на курс <b>"{course.title}"</b>

📚 Доступ до матеріалів активовано до {enrollment.expires_at.strftime("%d.%m.%Y")}

Зараз ми надішлемо вам перші матеріали для вивчення.

Приємного навчання! 🎓
"""

    await bot.send_message(
        chat_id=user.telegram_id,
        text=text,
        parse_mode="HTML",
    )

    from database.models import CourseMaterial

    result = await session.execute(
        select(CourseMaterial).where(
            CourseMaterial.course_id == course.id,
        ).order_by(CourseMaterial.order)
    )
    materials = result.scalars().all()

    for material in materials:
        try:
            if material.file_type == "document":
                await bot.send_document(
                    chat_id=user.telegram_id,
                    document=material.file_id,
                    caption=material.title,
                )
            elif material.file_type == "video":
                await bot.send_video(
                    chat_id=user.telegram_id,
                    video=material.file_id,
                    caption=material.title,
                )
            elif material.file_type == "audio":
                await bot.send_audio(
                    chat_id=user.telegram_id,
                    audio=material.file_id,
                    caption=material.title,
                )
        except Exception as e:
            print(f"Error sending material {material.id}: {e}")

    return True
