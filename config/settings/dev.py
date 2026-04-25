from decouple import Csv, config

from .base import *


SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="127.0.0.1,localhost",
    cast=Csv(),
)

TELEGRAM_NOTIFICATIONS_ENABLED = config(
    "TELEGRAM_NOTIFICATIONS_ENABLED",
    default=False,
    cast=bool,
)
TELEGRAM_BOT_TOKEN = config("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_MANAGER_CHAT_IDS = config(
    "TELEGRAM_MANAGER_CHAT_IDS",
    default="",
    cast=Csv(),
)
TELEGRAM_NOTIFICATION_RETRY_MINUTES = config(
    "TELEGRAM_NOTIFICATION_RETRY_MINUTES",
    default=10,
    cast=int,
)
