"""
Закритий формат для груп — заявка з 4 кроків,
менеджер контактує клієнта вручну.
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import ClosedFormatRequest, ClosedFormatStatus, User
from keyboards.inline import get_back_to_main_menu
from content.texts import (
    CLOSED_FORMAT_SHORT, CLOSED_FORMAT_DETAILS,
    CLOSED_FORMAT_REQUEST_INTRO, CLOSED_FORMAT_THANK_YOU,
)
from services.notifications import notify_new_closed_format_request

router = Router()


class ClosedFormatStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_size = State()
    waiting_for_phone = State()
    waiting_for_notes = State()


def _intro_kb() -> "InlineKeyboardMarkup":
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📖  Детальніше", callback_data="closed_format_details"))
    kb.row(InlineKeyboardButton(text="💬  Залишити заявку", callback_data="closed_format_request"))
    kb.row(InlineKeyboardButton(text="◀️  До головного меню", callback_data="main_menu"))
    return kb.as_markup()


def _details_kb() -> "InlineKeyboardMarkup":
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💬  Залишити заявку", callback_data="closed_format_request"))
    kb.row(InlineKeyboardButton(text="◀️  Назад", callback_data="closed_format"))
    return kb.as_markup()


@router.callback_query(F.data == "closed_format")
async def show_closed_format(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            text=CLOSED_FORMAT_SHORT,
            reply_markup=_intro_kb(),
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            text=CLOSED_FORMAT_SHORT,
            reply_markup=_intro_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "closed_format_details")
async def show_closed_format_details(callback: CallbackQuery):
    await callback.message.edit_text(
        text=CLOSED_FORMAT_DETAILS,
        reply_markup=_details_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ───────── FSM: 4 кроки ─────────

@router.callback_query(F.data == "closed_format_request")
async def start_request(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ClosedFormatStates.waiting_for_date)
    await callback.message.answer(CLOSED_FORMAT_REQUEST_INTRO, parse_mode="HTML")
    await callback.answer()


@router.message(ClosedFormatStates.waiting_for_date, F.text == "/cancel")
@router.message(ClosedFormatStates.waiting_for_size, F.text == "/cancel")
@router.message(ClosedFormatStates.waiting_for_phone, F.text == "/cancel")
@router.message(ClosedFormatStates.waiting_for_notes, F.text == "/cancel")
async def cancel_request(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Скасовано.", reply_markup=get_back_to_main_menu())


@router.message(ClosedFormatStates.waiting_for_date)
async def process_date(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Будь ласка, надішліть дату текстом. Або /cancel.")
        return
    if len(text) > 500:
        await message.answer("Занадто довго (макс 500 символів). Скоротіть.")
        return
    await state.update_data(requested_date_text=text)
    await state.set_state(ClosedFormatStates.waiting_for_size)
    await message.answer(
        "<b>Крок 2/4.</b>  Скільки людей буде у вашій групі?\n\n"
        "Надішліть число. Рекомендована кількість — від 9 до 12 осіб.",
        parse_mode="HTML",
    )


@router.message(ClosedFormatStates.waiting_for_size)
async def process_size(message: Message, state: FSMContext):
    try:
        size = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Очікувалось число. Спробуйте ще раз або /cancel.")
        return
    if size < 2 or size > 30:
        await message.answer("❌ Кількість має бути від 2 до 30. Спробуйте ще раз.")
        return
    await state.update_data(group_size=size)
    await state.set_state(ClosedFormatStates.waiting_for_phone)
    await message.answer(
        "<b>Крок 3/4.</b>  Контактний телефон для звʼязку.\n\n"
        "Або надішліть «-» якщо не хочете залишати (звʼяжемося в Telegram).",
        parse_mode="HTML",
    )


@router.message(ClosedFormatStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    phone = None if text in ("-", "—", "") else text[:50]
    await state.update_data(contact_phone=phone)
    await state.set_state(ClosedFormatStates.waiting_for_notes)
    await message.answer(
        "<b>Крок 4/4.</b>  Що ще нам важливо знати про вашу групу?\n\n"
        "Наприклад: привід зустрічі, особливі побажання, хто ці люди.\n"
        "Якщо нема чого додати — надішліть «-».",
        parse_mode="HTML",
    )


@router.message(ClosedFormatStates.waiting_for_notes)
async def process_notes(message: Message, state: FSMContext, session: AsyncSession, config):
    text = (message.text or "").strip()
    notes = None if text in ("-", "—", "") else text

    data = await state.get_data()

    # Реєструємо/знаходимо користувача
    result = await session.execute(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name or "",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    request = ClosedFormatRequest(
        user_id=user.id,
        requested_date_text=data["requested_date_text"],
        group_size=data["group_size"],
        contact_phone=data.get("contact_phone"),
        notes=notes,
        status=ClosedFormatStatus.NEW,
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)

    # Уведомлюємо адмінів
    try:
        await notify_new_closed_format_request(
            message.bot, config.tg_bot.admin_ids, session, request.id,
        )
    except Exception:
        pass

    await state.clear()
    await message.answer(
        CLOSED_FORMAT_THANK_YOU,
        reply_markup=get_back_to_main_menu(),
        parse_mode="HTML",
    )
