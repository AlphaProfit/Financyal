import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, delete, func

from database import init_db, async_session, Movie, Channel, Favorite

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("BOT_TOKEN") 
ADMIN_ID = int(os.getenv("ADMIN_ID")) # ID твоего аккаунта в Telegram

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- FSM (Состояния для админки) ---
class AddMovie(StatesGroup):
    title = State()
    photo = State()
    description = State()
    rating = State()
    link = State()

class AddChannel(StatesGroup):
    id = State()
    url = State()

# --- КЛАВИАТУРЫ ---
def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="❤️ Понравившиеся")]
        ], resize_keyboard=True
    )

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Добавить фильм", callback_data="add_movie")],
        [InlineKeyboardButton(text="📢 Управление каналами", callback_data="manage_channels")]
    ])

# --- ПРОВЕРКА ПОДПИСКИ ---
async def check_subscription(user_id: int) -> bool:
    async with async_session() as session:
        channels = await session.execute(select(Channel))
        channels = channels.scalars().all()
        
    for channel in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel.channel_id, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception:
            return False # Если бот не админ в канале или ошибка
    return True

async def get_sub_keyboard():
    async with async_session() as session:
        channels = await session.execute(select(Channel))
        channels = channels.scalars().all()
    
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(text="Подписаться", url=ch.url)])
    buttons.append([InlineKeyboardButton(text="✅ Я подписался", callback_data="check_subs")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- ХЕНДЛЕРЫ ПОЛЬЗОВАТЕЛЯ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if await check_subscription(message.from_user.id):
        await message.answer(f"Привет, {message.from_user.first_name}! Это ChillSeria.\nНажми 'Поиск' и введи код фильма.", reply_markup=main_kb())
    else:
        await message.answer("⚠️ Для использования бота подпишитесь на каналы:", reply_markup=await get_sub_keyboard())

@dp.callback_query(F.data == "check_subs")
async def callback_check_subs(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("Доступ открыт! 🍿", reply_markup=main_kb())
    else:
        await callback.answer("Вы подписались не на все каналы!", show_alert=True)

@dp.message(F.text == "🔍 Поиск")
async def search_mode(message: types.Message):
    if not await check_subscription(message.from_user.id):
        return await message.answer("⚠️ Подпишитесь на каналы:", reply_markup=await get_sub_keyboard())
    await message.answer("Введите код фильма (число):")

@dp.message(F.text == "❤️ Понравившиеся")
async def favorites_list(message: types.Message):
    if not await check_subscription(message.from_user.id):
        return await message.answer("⚠️ Подпишитесь на каналы:", reply_markup=await get_sub_keyboard())
    
    async with async_session() as session:
        favs = await session.execute(
            select(Movie).join(Favorite).where(Favorite.user_id == message.from_user.id)
        )
        movies = favs.scalars().all()
    
    if not movies:
        await message.answer("Список пуст.")
        return

    text = "<b>Ваши фильмы:</b>\n\n"
    for m in movies:
        text += f"Code: <code>{m.code}</code> | {m.title}\n"
    await message.answer(text, parse_mode="HTML")

# Поиск по коду (если введено число)
@dp.message(lambda x: x.text and x.text.isdigit())
async def get_movie_by_code(message: types.Message):
    if not await check_subscription(message.from_user.id):
        return await message.answer("⚠️ Подпишитесь на каналы:", reply_markup=await get_sub_keyboard())
    
    code = int(message.text)
    async with async_session() as session:
        movie = await session.scalar(select(Movie).where(Movie.code == code))
        
        if not movie:
            return await message.answer("Фильм с таким кодом не найден 😔")
        
        # Проверка лайка
        is_fav = await session.scalar(
            select(Favorite).where(Favorite.user_id == message.from_user.id, Favorite.movie_id == movie.id)
        )
        fav_text = "💔 Удалить" if is_fav else "❤️ Понравилось"
        fav_data = f"fav_{movie.id}"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Смотреть", url=movie.link)],
            [InlineKeyboardButton(text=fav_text, callback_data=fav_data)]
        ])
        
        caption = (f"🎬 <b>{movie.title}</b>\n"
                   f"⭐️ Рейтинг: {movie.rating}\n\n"
                   f"{movie.description}\n\n"
                   f"🔑 Код: <code>{movie.code}</code>")
        
        await message.answer_photo(photo=movie.photo_id, caption=caption, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("fav_"))
async def toggle_favorite(callback: types.CallbackQuery):
    movie_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    async with async_session() as session:
        existing = await session.scalar(select(Favorite).where(Favorite.user_id == user_id, Favorite.movie_id == movie_id))
        if existing:
            await session.delete(existing)
            btn_text = "❤️ Понравилось"
            text_resp = "Удалено из избранного"
        else:
            session.add(Favorite(user_id=user_id, movie_id=movie_id))
            btn_text = "💔 Удалить"
            text_resp = "Добавлено в избранное"
        
        await session.commit()
        
        # Обновляем клавиатуру (берем текущую ссылку смотреть из старой клавы)
        old_kb = callback.message.reply_markup.inline_keyboard
        watch_url = old_kb[0][0].url
        
        new_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Смотреть", url=watch_url)],
            [InlineKeyboardButton(text=btn_text, callback_data=f"fav_{movie_id}")]
        ])
        
        await callback.message.edit_reply_markup(reply_markup=new_kb)
        await callback.answer(text_resp)

# --- АДМИН ПАНЕЛЬ ---

@dp.message(Command("panel"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("Админ панель:", reply_markup=admin_kb())

# 1. Добавление фильма
@dp.callback_query(F.data == "add_movie")
async def start_add_movie(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название фильма:")
    await state.set_state(AddMovie.title)

@dp.message(AddMovie.title)
async def add_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Отправьте фото (превью):")
    await state.set_state(AddMovie.photo)

@dp.message(AddMovie.photo)
async def add_photo(message: types.Message, state: FSMContext):
    if not message.photo:
        return await message.answer("Пришлите фото!")
    await state.update_data(photo_id=message.photo[-1].file_id)
    await message.answer("Введите описание:")
    await state.set_state(AddMovie.description)

@dp.message(AddMovie.description)
async def add_desc(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Введите рейтинг (например 8.5/10):")
    await state.set_state(AddMovie.rating)

@dp.message(AddMovie.rating)
async def add_rating(message: types.Message, state: FSMContext):
    await state.update_data(rating=message.text)
    await message.answer("Введите ссылку на просмотр (Kinobadi):")
    await state.set_state(AddMovie.link)

@dp.message(AddMovie.link)
async def finish_movie(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        # Генерируем код (последний + 1)
        last_code = await session.scalar(select(func.max(Movie.code)))
        new_code = (last_code or 0) + 1
        
        movie = Movie(
            code=new_code,
            title=data['title'],
            photo_id=data['photo_id'],
            description=data['description'],
            rating=data['rating'],
            link=message.text
        )
        session.add(movie)
        await session.commit()
    
    await message.answer(f"✅ Фильм добавлен!\nКод фильма: <b>{new_code}</b>", parse_mode="HTML")
    await state.clear()

# 2. Управление каналами
@dp.callback_query(F.data == "manage_channels")
async def manage_channels(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel")],
        [InlineKeyboardButton(text="➖ Удалить все каналы", callback_data="del_channels")]
    ])
    await callback.message.answer("Управление ОП:", reply_markup=kb)

@dp.callback_query(F.data == "add_channel")
async def ask_channel_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Перешлите любое сообщение из канала или введите ID (начинается с -100). БОТ ДОЛЖЕН БЫТЬ АДМИНОМ В КАНАЛЕ!")
    await state.set_state(AddChannel.id)

@dp.message(AddChannel.id)
async def get_channel_id(message: types.Message, state: FSMContext):
    if message.forward_from_chat:
        cid = message.forward_from_chat.id
    else:
        try:
            cid = int(message.text)
        except:
            return await message.answer("Неверный ID.")
    
    await state.update_data(id=cid)
    await message.answer("Теперь отправьте ссылку-приглашение на этот канал:")
    await state.set_state(AddChannel.url)

@dp.message(AddChannel.url)
async def finish_channel(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        session.add(Channel(channel_id=data['id'], url=message.text))
        await session.commit()
    await message.answer("Канал добавлен в ОП.")
    await state.clear()

@dp.callback_query(F.data == "del_channels")
async def delete_channels(callback: types.CallbackQuery):
    async with async_session() as session:
        await session.execute(delete(Channel))
        await session.commit()
    await callback.message.answer("Список обязательной подписки очищен.")

# --- ЗАПУСК ---
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exit")
