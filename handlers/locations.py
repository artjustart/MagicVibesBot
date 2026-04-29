"""
Локації Magic Vibes — список адрес з мапою та відео-інструкцією.
"""
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import Location
from keyboards.inline import get_back_to_main_menu

router = Router()


def _locations_kb(locations: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for loc in locations:
        kb.row(InlineKeyboardButton(
            text=f"📍  {loc.title}",
            callback_data=f"loc_{loc.id}",
        ))
    kb.row(InlineKeyboardButton(text="◀️  До головного меню", callback_data="main_menu"))
    return kb.as_markup()


def _location_detail_kb(loc: Location) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🗺  Відкрити в Google Maps", url=loc.maps_url))
    kb.row(InlineKeyboardButton(text="◀️  До списку локацій", callback_data="locations"))
    kb.row(InlineKeyboardButton(text="🪷  Головне меню", callback_data="main_menu"))
    return kb.as_markup()


async def _send_or_edit(callback: CallbackQuery, text: str, reply_markup):
    """Якщо попереднє повідомлення — відео (з підписом), edit_text недоступний.
    Тоді видаляємо його й шлемо нове."""
    try:
        await callback.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
        return
    except Exception:
        pass
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.bot.send_message(
        chat_id=callback.from_user.id,
        text=text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "locations")
async def show_locations(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(Location).where(Location.is_active == True).order_by(Location.sort_order, Location.id)
    )
    locations = result.scalars().all()

    if not locations:
        await _send_or_edit(
            callback,
            "📍 <b>Локації</b>\n\n<i>Список локацій ще не налаштовано.</i>",
            get_back_to_main_menu(),
        )
        await callback.answer()
        return

    text = (
        "📍 <b>ЯК ДІСТАТИСЯ</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "Оберіть локацію — подивіться адресу, карту та відео-інструкцію 👇"
    )
    await _send_or_edit(callback, text, _locations_kb(locations))
    await callback.answer()


@router.callback_query(F.data.regexp(r"^loc_\d+$"))
async def show_location(callback: CallbackQuery, session: AsyncSession):
    location_id = int(callback.data.replace("loc_", ""))
    loc = await session.get(Location, location_id)
    if not loc:
        await callback.answer("Локацію не знайдено", show_alert=True)
        return

    text = (
        f"📍 <b>{loc.title}</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"🏠  <b>Адреса:</b>\n{loc.address}"
    )

    # Видаляємо попереднє повідомлення меню локацій (щоб відео+картка були єдиним блоком)
    try:
        await callback.message.delete()
    except Exception:
        pass

    bot = callback.bot
    chat_id = callback.from_user.id

    # Відеоінструкція, якщо завантажена
    if loc.video_file_id:
        try:
            await bot.send_video(
                chat_id=chat_id,
                video=loc.video_file_id,
                caption=text,
                parse_mode="HTML",
                reply_markup=_location_detail_kb(loc),
            )
            await callback.answer()
            return
        except Exception:
            # Якщо файл недоступний — просто текст
            pass

    await bot.send_message(
        chat_id=chat_id,
        text=text + "\n\n<i>📹 Відео-інструкція ще не завантажена.</i>",
        reply_markup=_location_detail_kb(loc),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()
