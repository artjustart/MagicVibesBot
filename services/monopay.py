"""
Сервис интеграции с MonoPay для приема платежей
"""
import aiohttp
import hmac
import hashlib
import base64
from typing import Optional
from datetime import datetime

class MonoPayService:
    """Сервис для работы с MonoPay API"""
    
    BASE_URL = "https://api.monobank.ua/api/merchant"
    
    def __init__(self, token: str, merchant_id: str):
        self.token = token
        self.merchant_id = merchant_id
    
    def _generate_signature(self, data: str) -> str:
        """Генерация подписи для запроса"""
        signature = base64.b64encode(
            hmac.new(
                self.token.encode(),
                data.encode(),
                hashlib.sha256
            ).digest()
        ).decode()
        return signature
    
    async def create_invoice(
        self,
        amount: float,
        currency: str = "UAH",
        description: str = "",
        reference: str = "",
        redirect_url: str = "",
        webhook_url: str = ""
    ) -> dict:
        """
        Создание инвойса для оплаты
        
        Args:
            amount: Сумма в гривнах (копейках * 100)
            currency: Валюта (UAH по умолчанию)
            description: Описание платежа
            reference: Уникальный идентификатор платежа
            redirect_url: URL для редиректа после оплаты
            webhook_url: URL для webhook уведомлений
            
        Returns:
            dict с данными инвойса включая pageUrl (ссылка на оплату)
        """
        
        # MonoPay требует сумму в копейках
        amount_in_kopiyky = int(amount * 100)
        
        payload = {
            "amount": amount_in_kopiyky,
            "merchantPaymInfo": {
                "reference": reference,
                "destination": description
            }
        }
        
        if redirect_url:
            payload["redirectUrl"] = redirect_url
        if webhook_url:
            payload["webHookUrl"] = webhook_url
        
        headers = {
            "X-Token": self.token,
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.BASE_URL}/invoice/create",
                json=payload,
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "invoice_id": data.get("invoiceId"),
                        "payment_url": data.get("pageUrl"),
                        "data": data
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": error_text
                    }
    
    async def check_payment_status(self, invoice_id: str) -> dict:
        """
        Проверка статуса платежа
        
        Args:
            invoice_id: ID инвойса из MonoPay
            
        Returns:
            dict со статусом платежа
        """
        headers = {
            "X-Token": self.token
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.BASE_URL}/invoice/status?invoiceId={invoice_id}",
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Статусы MonoPay:
                    # created - создан
                    # processing - в обработке
                    # hold - холдирование средств
                    # success - успешно оплачен
                    # failure - ошибка оплаты
                    # reversed - возврат средств
                    # expired - истек срок действия
                    
                    status = data.get("status")
                    
                    return {
                        "success": True,
                        "status": status,
                        "paid": status == "success",
                        "amount": data.get("amount", 0) / 100,  # Конвертируем обратно в гривны
                        "data": data
                    }
                else:
                    return {
                        "success": False,
                        "error": await response.text()
                    }
    
    async def cancel_invoice(self, invoice_id: str) -> dict:
        """
        Отмена инвойса
        
        Args:
            invoice_id: ID инвойса из MonoPay
            
        Returns:
            dict с результатом операции
        """
        headers = {
            "X-Token": self.token,
            "Content-Type": "application/json"
        }
        
        payload = {
            "invoiceId": invoice_id
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.BASE_URL}/invoice/cancel",
                json=payload,
                headers=headers
            ) as response:
                if response.status == 200:
                    return {
                        "success": True,
                        "data": await response.json()
                    }
                else:
                    return {
                        "success": False,
                        "error": await response.text()
                    }
    
    def verify_webhook_signature(self, received_signature: str, body: str) -> bool:
        """
        Проверка подписи webhook от MonoPay
        
        Args:
            received_signature: Подпись из заголовка X-Sign
            body: Тело запроса
            
        Returns:
            True если подпись валидна
        """
        calculated_signature = self._generate_signature(body)
        return hmac.compare_digest(received_signature, calculated_signature)


# Пример использования:
"""
# Инициализация
mono_service = MonoPayService(
    token="your_token_here",
    merchant_id="your_merchant_id"
)

# Создание платежа
invoice = await mono_service.create_invoice(
    amount=500.00,  # 500 грн
    description="Оплата за индивидуальную сессию",
    reference="booking_123",
    webhook_url="https://your-domain.com/webhook/monopay"
)

if invoice["success"]:
    payment_url = invoice["payment_url"]
    # Отправить payment_url пользователю для оплаты
    
# Проверка статуса
status = await mono_service.check_payment_status(invoice["invoice_id"])
if status["paid"]:
    # Платеж успешно прошел
    pass
"""
