"""
Анкета учасника — 12 питань через FSM.
Підтримує типи питань: text, yes_no, yes_no_describe, choice_a_b_other.
"""
import json
from datetime import datetime

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import Questionnaire, User
from keyboards.inline import get_back_to_main_menu
from content.texts import ANKETA_INTRO, ANKETA_QUESTIONS, POST_ANKETA_TEXT
from services.notifications import notify_anketa_filled

router = Router()


class QuestionnaireStates(StatesGroup):
    intro = State()           # подивився інтро, чекаємо «Розпочати»
    answering = State()       # основний стан — поточний індекс зберігається в FSM data
    describing = State()      # підкрок: пишемо опис після «Так» в yes_no_describe
    choice_other = State()    # підкрок: пишемо «Свій варіант» в choice_a_b_other


# ──────────────── intro ────────────────

def _intro_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✨  Розпочати", callback_data="anketa_start"))
    kb.row(InlineKeyboardButton(text="◀️  До головного меню", callback_data="main_menu"))
    return kb.as_markup()


@router.callback_query(F.data == "start_questionnaire")
async def show_intro(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text(
            text=ANKETA_INTRO,
            reply_markup=_intro_kb(),
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            text=ANKETA_INTRO,
            reply_markup=_intro_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


# ──────────────── рушій питань ────────────────

def _yes_no_kb(idx: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅  Так", callback_data=f"aq_{idx}_yes"),
        InlineKeyboardButton(text="❌  Ні", callback_data=f"aq_{idx}_no"),
    )
    return kb.as_markup()


def _choice_abother_kb(idx: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="а", callback_data=f"aq_{idx}_a"))
    kb.row(InlineKeyboardButton(text="б", callback_data=f"aq_{idx}_b"))
    kb.row(InlineKeyboardButton(text="✏️  Свій варіант", callback_data=f"aq_{idx}_other"))
    return kb.as_markup()


async def _ask_question(message_or_callback, state: FSMContext, idx: int):
    """Показати питання з індексом idx."""
    if idx >= len(ANKETA_QUESTIONS):
        return  # завершення викликається окремо

    q = ANKETA_QUESTIONS[idx]
    qtype = q["type"]

    await state.update_data(current_idx=idx)

    if qtype == "yes_no" or qtype == "yes_no_describe":
        markup = _yes_no_kb(idx)
    elif qtype == "choice_a_b_other":
        markup = _choice_abother_kb(idx)
    else:
        markup = None

    text = q["prompt"] + "\n\n<i>Або /cancel щоб відмінити (прогрес не збережеться).</i>"

    target = message_or_callback.message if isinstance(message_or_callback, CallbackQuery) else message_or_callback
    if isinstance(message_or_callback, CallbackQuery):
        try:
            await target.edit_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            await target.answer(text, reply_markup=markup, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "anketa_start")
async def start_questions(callback: CallbackQuery, state: FSMContext):
    await state.set_state(QuestionnaireStates.answering)
    await state.update_data(answers={}, current_idx=0)
    await _ask_question(callback, state, 0)
    await callback.answer()


@router.message(QuestionnaireStates.answering, F.text == "/cancel")
@router.message(QuestionnaireStates.describing, F.text == "/cancel")
@router.message(QuestionnaireStates.choice_other, F.text == "/cancel")
async def cancel_anketa(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Анкету скасовано.", reply_markup=get_back_to_main_menu())


async def _save_answer_and_advance(state: FSMContext, key: str, value, message_or_callback):
    data = await state.get_data()
    answers = data.get("answers", {})
    answers[key] = value
    await state.update_data(answers=answers)

    next_idx = data.get("current_idx", 0) + 1
    if next_idx >= len(ANKETA_QUESTIONS):
        await _finish_anketa(message_or_callback, state)
    else:
        await state.set_state(QuestionnaireStates.answering)
        await _ask_question(message_or_callback, state, next_idx)


async def _finish_anketa(message_or_callback, state: FSMContext):
    """Зберегти анкету в БД, повідомити клієнта і адмінів."""
    data = await state.get_data()
    answers = data.get("answers", {})

    # Достаємо обʼєкти з повідомлення
    if isinstance(message_or_callback, CallbackQuery):
        bot = message_or_callback.bot
        chat = message_or_callback.message.chat
        from_user = message_or_callback.from_user
    else:
        bot = message_or_callback.bot
        chat = message_or_callback.chat
        from_user = message_or_callback.from_user

    # Витягуємо session і config через middleware? Ні — в FSM тут немає доступу.
    # Вирішення: зберігаємо в БД через nested виклик. Робимо це через middleware-data,
    # яке передається тільки в роутерні хендлери. Тому не використовуємо тут.
    # Натомість викликаємо message.bot та повідомлення як обгортку.
    # → save_to_db викликається з двох верхніх хендлерів, які мають session/config.
    # Сюди передаємо все вже готове. Refactor:
    raise NotImplementedError("must be called via _persist_and_finalize")  # pragma: no cover


# Завершальний шлях — викликається з handler'ів які мають session/config


async def _persist_and_finalize(
    message_or_callback,
    state: FSMContext,
    session: AsyncSession,
    config,
):
    data = await state.get_data()
    answers = data.get("answers", {})

    # User
    if isinstance(message_or_callback, CallbackQuery):
        tg_user = message_or_callback.from_user
        chat_id = message_or_callback.from_user.id
        bot = message_or_callback.bot
    else:
        tg_user = message_or_callback.from_user
        chat_id = message_or_callback.chat.id
        bot = message_or_callback.bot

    result = await session.execute(
        select(User).where(User.telegram_id == tg_user.id)
    )
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name or "",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    # Зберегти / оновити анкету
    existing = await session.execute(
        select(Questionnaire).where(Questionnaire.user_id == user.id)
    )
    q = existing.scalar_one_or_none()
    payload = json.dumps(answers, ensure_ascii=False)
    if q:
        q.data = payload
        q.updated_at = datetime.utcnow()
    else:
        q = Questionnaire(user_id=user.id, data=payload)
        session.add(q)
    await session.commit()
    await session.refresh(q)

    # Повідомити адмінів
    try:
        await notify_anketa_filled(bot, config.tg_bot.admin_ids, session, q.id)
    except Exception:
        pass

    await state.clear()
    await bot.send_message(
        chat_id=chat_id,
        text=POST_ANKETA_TEXT,
        reply_markup=get_back_to_main_menu(),
        parse_mode="HTML",
    )


# ──────────────── обробники окремих типів ────────────────

# yes/no та yes_no_describe — кнопки
@router.callback_query(F.data.regexp(r"^aq_\d+_(yes|no)$"))
async def handle_yes_no(callback: CallbackQuery, state: FSMContext, session: AsyncSession, config):
    parts = callback.data.split("_")
    idx = int(parts[1])
    answer = parts[2]  # yes | no

    if idx >= len(ANKETA_QUESTIONS):
        await callback.answer()
        return

    q = ANKETA_QUESTIONS[idx]
    key = q["key"]

    if q["type"] == "yes_no":
        # просто Так/Ні
        await callback.answer()
        await _save_answer_advance_helper(state, key, "Так" if answer == "yes" else "Ні",
                                          callback, session, config)
        return

    if q["type"] == "yes_no_describe":
        if answer == "no":
            await callback.answer()
            await _save_answer_advance_helper(state, key, "Ні",
                                              callback, session, config)
            return
        # «Так» → просимо опис
        await state.set_state(QuestionnaireStates.describing)
        await callback.message.edit_text(
            f"{q['prompt']}\n\n✅ <b>Так</b>\n\nОпишіть, будь ласка, деталі:",
            parse_mode="HTML",
        )
        await callback.answer()


@router.message(QuestionnaireStates.describing)
async def handle_describe(message: Message, state: FSMContext, session: AsyncSession, config):
    data = await state.get_data()
    idx = data.get("current_idx", 0)
    q = ANKETA_QUESTIONS[idx]
    text = (message.text or "").strip()
    if not text:
        await message.answer("Будь ласка, опишіть текстом. Або /cancel.")
        return
    answer = f"Так: {text}"
    await _save_answer_advance_helper(state, q["key"], answer, message, session, config)


# choice_a_b_other — кнопки
@router.callback_query(F.data.regexp(r"^aq_\d+_(a|b|other)$"))
async def handle_choice(callback: CallbackQuery, state: FSMContext, session: AsyncSession, config):
    parts = callback.data.split("_")
    idx = int(parts[1])
    choice = parts[2]

    if idx >= len(ANKETA_QUESTIONS):
        await callback.answer()
        return

    q = ANKETA_QUESTIONS[idx]
    if q["type"] != "choice_a_b_other":
        await callback.answer()
        return

    if choice == "a":
        await callback.answer()
        await _save_answer_advance_helper(state, q["key"], "а", callback, session, config)
    elif choice == "b":
        await callback.answer()
        await _save_answer_advance_helper(state, q["key"], "б", callback, session, config)
    else:
        await state.set_state(QuestionnaireStates.choice_other)
        await callback.message.edit_text(
            f"{q['prompt']}\n\n✏️ <b>Свій варіант</b>\n\nОпишіть, будь ласка:",
            parse_mode="HTML",
        )
        await callback.answer()


@router.message(QuestionnaireStates.choice_other)
async def handle_choice_other(message: Message, state: FSMContext, session: AsyncSession, config):
    data = await state.get_data()
    idx = data.get("current_idx", 0)
    q = ANKETA_QUESTIONS[idx]
    text = (message.text or "").strip()
    if not text:
        await message.answer("Будь ласка, опишіть текстом. Або /cancel.")
        return
    await _save_answer_advance_helper(state, q["key"], f"Свій: {text}", message, session, config)


# text — звичайна відповідь
@router.message(QuestionnaireStates.answering)
async def handle_text_answer(message: Message, state: FSMContext, session: AsyncSession, config):
    data = await state.get_data()
    idx = data.get("current_idx", 0)
    if idx >= len(ANKETA_QUESTIONS):
        return
    q = ANKETA_QUESTIONS[idx]
    if q["type"] != "text":
        # для yes_no/choice користувач має тиснути кнопки
        await message.answer("Будь ласка, скористайтеся кнопками вище.")
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Порожня відповідь. Спробуйте ще раз або /cancel.")
        return
    await _save_answer_advance_helper(state, q["key"], text, message, session, config)


# ──────────────── helper: зберегти + просунутися ────────────────

async def _save_answer_advance_helper(state: FSMContext, key: str, value: str,
                                      message_or_callback, session: AsyncSession, config):
    data = await state.get_data()
    answers = data.get("answers", {})
    answers[key] = value
    await state.update_data(answers=answers)

    next_idx = data.get("current_idx", 0) + 1
    if next_idx >= len(ANKETA_QUESTIONS):
        await _persist_and_finalize(message_or_callback, state, session, config)
    else:
        await state.set_state(QuestionnaireStates.answering)
        await _ask_question(message_or_callback, state, next_idx)
