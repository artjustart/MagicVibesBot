"""
Конфигурация бота Magic Vibes
"""
from dataclasses import dataclass
from environs import Env

@dataclass
class TgBot:
    token: str
    admin_ids: list[int]

@dataclass
class Database:
    host: str
    port: int
    user: str
    password: str
    name: str
    
    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

@dataclass
class MonoPay:
    token: str
    merchant_id: str

@dataclass
class Config:
    tg_bot: TgBot
    db: Database
    monopay: MonoPay

def load_config(path: str = None) -> Config:
    env = Env()
    env.read_env(path)
    
    return Config(
        tg_bot=TgBot(
            token=env.str("BOT_TOKEN"),
            admin_ids=list(map(int, env.list("ADMIN_IDS")))
        ),
        db=Database(
            host=env.str("DB_HOST"),
            port=env.int("DB_PORT", 5432),
            user=env.str("DB_USER"),
            password=env.str("DB_PASSWORD"),
            name=env.str("DB_NAME")
        ),
        monopay=MonoPay(
            token=env.str("MONOPAY_TOKEN"),
            merchant_id=env.str("MONOPAY_MERCHANT_ID")
        )
    )
