"""
Webhook обработчик для приема уведомлений от MonoPay
Для использования в продакшене с aiohttp или FastAPI
"""
from aiohttp import web
import json
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from config.settings import load_config
from database.models import Payment, Booking, CourseEnrollment, BookingStatus, PaymentStatus
from services.monopay import MonoPayService


async def handle_monopay_webhook(request: web.Request):
    """
    Обработчик webhook от MonoPay
    
    MonoPay отправляет POST запрос на этот endpoint когда меняется статус платежа
    """
    
    try:
        # Получаем подпись из заголовков
        signature = request.headers.get('X-Sign')
        if not signature:
            return web.Response(status=400, text="Missing signature")
        
        # Получаем тело запроса
        body_text = await request.text()
        body = json.loads(body_text)
        
        # Проверяем подпись
        config = load_config()
        mono_service = MonoPayService(config.monopay.token, config.monopay.merchant_id)
        
        if not mono_service.verify_webhook_signature(signature, body_text):
            return web.Response(status=403, text="Invalid signature")
        
        # Обрабатываем уведомление
        invoice_id = body.get('invoiceId')
        status = body.get('status')
        reference = body.get('reference')  # Наш payment_123
        
        if not reference or not reference.startswith('payment_'):
            return web.Response(status=400, text="Invalid reference")
        
        # Извлекаем ID платежа
        payment_id = int(reference.split('_')[1])
        
        # Получаем сессию БД
        engine = create_async_engine(config.db.url)
        session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with session_maker() as session:
            # Получаем платеж
            payment = await session.get(Payment, payment_id)
            
            if not payment:
                return web.Response(status=404, text="Payment not found")
            
            # Обновляем статус платежа
            if status == 'success':
                payment.status = PaymentStatus.SUCCESS
                payment.paid_at = datetime.utcnow()
                
                # Если это бронирование - подтверждаем его
                if payment.booking_id:
                    booking = await session.get(Booking, payment.booking_id)
                    if booking:
                        booking.status = BookingStatus.CONFIRMED
                        
                        # Отправляем уведомление пользователю
                        from aiogram import Bot
                        bot = Bot(token=config.tg_bot.token)
                        
                        # Получаем данные для сообщения
                        from database.models import User, Practice, PracticeSchedule
                        user = await session.get(User, booking.user_id)
                        practice = await session.get(Practice, booking.practice_id)
                        schedule = await session.get(PracticeSchedule, booking.schedule_id)
                        
                        date_str = schedule.datetime.strftime("%d.%m.%Y в %H:%M")
                        
                        text = f"""
✅ <b>Оплата прошла успешно!</b>

Ваше бронирование подтверждено:

🧘‍♀️ <b>Практика:</b> {practice.title}
📅 <b>Дата и время:</b> {date_str}

Ждем вас! За 24 часа до практики мы пришлем напоминание.
"""
                        
                        await bot.send_message(
                            chat_id=user.telegram_id,
                            text=text,
                            parse_mode="HTML"
                        )
                        await bot.session.close()
                
                # Если это курс - активируем доступ
                elif payment.course_enrollment_id:
                    enrollment = await session.get(CourseEnrollment, payment.course_enrollment_id)
                    if enrollment:
                        enrollment.is_active = True
                        
                        # Отправляем материалы курса
                        from handlers.courses import activate_course_access
                        from aiogram import Bot
                        bot = Bot(token=config.tg_bot.token)
                        
                        await activate_course_access(payment_id, session, bot)
                        await bot.session.close()
                
                await session.commit()
                
            elif status == 'failure':
                payment.status = PaymentStatus.FAILED
                await session.commit()
                
            elif status == 'reversed':
                payment.status = PaymentStatus.REFUNDED
                
                # Если это бронирование - отменяем его
                if payment.booking_id:
                    booking = await session.get(Booking, payment.booking_id)
                    if booking:
                        booking.status = BookingStatus.CANCELLED
                        
                        # Возвращаем место в расписание
                        schedule = await session.get(PracticeSchedule, booking.schedule_id)
                        if schedule:
                            schedule.available_slots += 1
                            schedule.is_available = True
                
                await session.commit()
        
        await engine.dispose()
        
        return web.Response(status=200, text="OK")
        
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return web.Response(status=500, text="Internal error")


# Пример использования с aiohttp
async def create_webhook_app():
    """Создание aiohttp приложения для webhook"""
    app = web.Application()
    app.router.add_post('/webhook/monopay', handle_monopay_webhook)
    return app


# Пример запуска (для отдельного процесса)
if __name__ == '__main__':
    from datetime import datetime
    
    app = create_webhook_app()
    web.run_app(app, host='0.0.0.0', port=8080)


# ============================================================
# Альтернативный вариант с FastAPI (более современный подход)
# ============================================================

"""
from fastapi import FastAPI, Request, HTTPException, Header
from typing import Optional

app = FastAPI()

@app.post("/webhook/monopay")
async def monopay_webhook(
    request: Request,
    x_sign: Optional[str] = Header(None)
):
    if not x_sign:
        raise HTTPException(status_code=400, detail="Missing signature")
    
    body_text = await request.body()
    body = await request.json()
    
    # Проверка подписи
    config = load_config()
    mono_service = MonoPayService(config.monopay.token, config.monopay.merchant_id)
    
    if not mono_service.verify_webhook_signature(x_sign, body_text.decode()):
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    # Обработка платежа (аналогично примеру выше)
    # ...
    
    return {"status": "ok"}

# Запуск: uvicorn webhook:app --host 0.0.0.0 --port 8080
"""
