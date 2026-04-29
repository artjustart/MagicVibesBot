"""
Банківські реквізити Magic Vibes для оплати переказом.
"""

REQUISITES = {
    "recipient": "ФОП Міроненко Людмила Джемалівна",
    "iban": "UA453052990000026007016803048",
    "code": "2825421342",  # РНОКПП / ЄДРПОУ
}


def format_requisites(purpose: str) -> str:
    """Текст з реквізитами та призначенням платежу."""
    return (
        "💳 <b>РЕКВІЗИТИ ДЛЯ ОПЛАТИ</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "<b>Отримувач:</b>\n"
        f"<code>{REQUISITES['recipient']}</code>\n\n"
        "<b>IBAN:</b>\n"
        f"<code>{REQUISITES['iban']}</code>\n\n"
        "<b>РНОКПП / ЄДРПОУ:</b>\n"
        f"<code>{REQUISITES['code']}</code>\n\n"
        "<b>Призначення платежу:</b>\n"
        f"<code>{purpose}</code>\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "ℹ️ Натисніть на текст щоб <b>скопіювати</b>.\n\n"
        "📸 <b>Після оплати</b> натисніть кнопку нижче і надішліть скріншот квитанції або PDF-чек."
    )


def format_purpose_for_booking(practice_title: str, date_str: str, full_name: str) -> str:
    """Призначення платежу для бронювання практики/сесії."""
    safe_name = full_name or "(вкажіть ПІБ)"
    return f"Оплата за «{practice_title}» {date_str}. ПІБ: {safe_name}"


def format_purpose_generic(full_name: str) -> str:
    """Призначення платежу — загальне (з кнопки головного меню)."""
    safe_name = full_name or "(вкажіть ПІБ платника)"
    return f"Оплата за послуги Magic Vibes. ПІБ платника: {safe_name}"
