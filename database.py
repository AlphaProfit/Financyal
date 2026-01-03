from sqlalchemy import BigInteger, String, Text, Integer, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
import os

# Используем SQLite для тестов, но на Railway заменим на POSTGRES_URL
DB_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///db.sqlite3")

engine = create_async_engine(DB_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

class Base(AsyncAttrs, DeclarativeBase):
    pass

# Таблица фильмов
class Movie(Base):
    __tablename__ = 'movies'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[int] = mapped_column(unique=True)  # Код фильма
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    photo_id: Mapped[str] = mapped_column(String(255)) # file_id фото
    rating: Mapped[str] = mapped_column(String(50))
    link: Mapped[str] = mapped_column(String(500))

# Таблица каналов для обязательной подписки
class Channel(Base):
    __tablename__ = 'channels'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, unique=True) # ID канала (-100...)
    url: Mapped[str] = mapped_column(String(255)) # Ссылка приглашение

# Таблица лайков (Избранное)
class Favorite(Base):
    __tablename__ = 'favorites'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    movie_id: Mapped[int] = mapped_column(ForeignKey('movies.id'))
    
    movie: Mapped["Movie"] = relationship()

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
