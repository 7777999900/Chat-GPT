import asyncio
import logging
import json
import os
import re
import time
import traceback
import threading
import uuid
import shutil
import glob
import hashlib
import random
import string
import io
import base64
import zipfile
import sys
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Union, Any, Tuple, Set, Callable
from functools import wraps
from urllib.parse import urlencode, quote, unquote

import aiohttp  # Using aiohttp instead of requests for async HTTP calls
from aiofiles import open as aio_open  # Async file operations
from aiohttp import web

from aiogram import Bot, Dispatcher, Router, F, html
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ChatAction, ParseMode
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, FSInputFile,
    InputMediaPhoto, PhotoSize
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.utils.chat_action import ChatActionMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import GetUpdates

# Версия бота
BOT_VERSION = "1.3.1"

# Получаем порт из переменной окружения или используем 10000 по умолчанию (требование Render)
PORT = int(os.environ.get("PORT", 10000))
APP_URL = os.environ.get("APP_URL", "")

# Конфигурация путей для хранения данных на Render
# На бесплатном плане Render /tmp не сохраняется между перезапусками,
# поэтому всегда используем директорию проекта /opt/render/project/src/
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Всегда используем директорию проекта для хранения данных
DATA_DIR = os.path.join(BASE_DIR, "data") 
os.makedirs(DATA_DIR, exist_ok=True)

# Настройка логирования с учетом ограничений Render
LOG_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Создаем дополнительные директории для разных типов данных
CACHE_DIR = os.path.join(DATA_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

BACKUP_DIR = os.path.join(DATA_DIR, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

USER_MEDIA_DIR = os.path.join(DATA_DIR, "user_media")
os.makedirs(USER_MEDIA_DIR, exist_ok=True)

STATS_DIR = os.path.join(DATA_DIR, "stats")
os.makedirs(STATS_DIR, exist_ok=True)

# Конфигурация и константы
CONFIG = {
    "API_URL": "https://api.intelligence.io.solutions/api/v1",
    "TOKEN": os.environ.get("TELEGRAM_TOKEN", "7839597384:AAFlm4v3qcudhJfiFfshz1HW6xpKhtqlV5g"),
    "API_KEY": os.environ.get("AI_API_KEY", "io-v2-eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJvd25lciI6ImJlMjYwYjFhLWI0OWMtNDU2MC04ODZiLTMwYTBmMGFlNGZlNSIsImV4cCI6NDg5OTUwNzg0MH0.Z46h1WZ-2jsXyg43r2M0okgeLoSEzrq-ULHRMS-EW6r3ccxYkXTZ5mNJO5Aw1qBAkRI5NX9t8zXc1sbUxt8WzA"),
    "DEFAULT_SYSTEM_PROMPT": "Вы - полезный AI-ассистент с энциклопедическими знаниями. Предоставляйте точные и информативные ответы. Вы обладаете обширными знаниями о различных исторических личностях, включая писателей, ученых и философов, таких как Пушкин, Толстой, Гоголь, Эйнштейн, Тесла, Ньютон, Сократ, и многих других. Для технических вопросов и примеров кода используйте Markdown-форматирование.",
    "MAX_MESSAGE_LENGTH": 4096,
    "MAX_CONTEXT_LENGTH": 50,  # Увеличено количество сообщений в истории
    "TEMPERATURE": 0.3,  # Уровень креативности (ниже = более предсказуемо)
    "MAX_TOKENS": 8000,  # Увеличено макс. количество токенов для длинных ответов
    "RETRY_ATTEMPTS": 5,  # Количество попыток при ошибке
    "ADMIN_IDS": [12345678],  # ID администраторов
    "ALLOWED_FORMATS": ["jpg", "jpeg", "png", "webp"],  # Поддерживаемые форматы изображений
    "MAX_FILE_SIZE": 20 * 1024 * 1024,  # Увеличен максимальный размер файла (20 МБ)
    "CACHE_TIMEOUT": 3600,  # Время жизни кэша в секундах (1 час)
    "FALLBACK_MODE": True,  # Автоматически переключаться на другие модели при ошибке
    "PERSISTENT_STORAGE": DATA_DIR,  # Директория для хранения данных (адаптировано для Render)
    "CONTEXT_DECAY": 0.9,  # Коэффициент важности старых сообщений в контексте (1.0 = все сообщения равнозначны)
    "REQUEST_TIMEOUT": 120,  # Увеличен таймаут запросов к API для длинных ответов
    "USE_WEBHOOK": True if APP_URL else False,  # Использовать webhook вместо polling если указан APP_URL
    "MAX_INLINE_KEYBOARDS": 5,  # Максимальное количество кнопок в ряду для inline клавиатуры
    "STATS_API_KEY": os.environ.get("STATS_API_KEY", "statskey"),  # Ключ для доступа к API статистики
    "MAX_DAILY_REQUESTS": 40,  # Увеличено максимальное количество запросов в день на бесплатном плане
    "PREMIUM_USER_IDS": [],  # ID премиум пользователей с неограниченным доступом
    "LOG_ROTATION_SIZE": 10 * 1024 * 1024,  # Размер файла лога перед ротацией (10 МБ)
    "LOG_BACKUPS_COUNT": 5,  # Количество файлов ротации для хранения
    "HEALTH_CHECK_INTERVAL": 3600,  # Интервал проверки работоспособности в секундах
    "USER_TIMEOUT_SECONDS": 300,  # Увеличен таймаут ожидания ответа пользователя в секундах
    "RATE_LIMIT_WINDOW": 60,  # Окно для ограничения частоты запросов (в секундах)
    "RATE_LIMIT_MAX_REQUESTS": 15,  # Увеличено максимальное количество запросов за окно времени
    "BACKUP_INTERVAL": 3600,  # Интервал резервного копирования в секундах
    "MAINTENANCE_MODE": False,  # Режим технического обслуживания
    "WEBHOOK_SECRET_TOKEN": os.environ.get("WEBHOOK_SECRET", ""),  # Секретный токен для защиты вебхука
    "DEBUG_MODE": os.environ.get("DEBUG_MODE", "0") == "1",  # Режим отладки
    "ENABLE_THINKING_ANIMATION": True,  # Имитация "AI думает"
    "ENABLE_SPAM_PROTECTION": True,  # Защита от спама и рекламы
    "STREAM_RESPONSES": True,  # Потоковая отправка ответов для длинных сообщений
    "THINKING_MESSAGES": [
        "💭 AI анализирует ваш вопрос...",
        "🔍 AI обрабатывает информацию...",
        "🧠 AI формулирует ответ...",
        "⏳ AI подбирает наилучший ответ...",
        "📚 AI изучает материалы по теме...",
        "🔄 AI работает над вашим запросом..."
    ],
}

# Патерны для фильтрации спама и рекламы
SPAM_PATTERNS = [
    r"(?i)заработ[а-я]+ деньги",
    r"(?i)инвестиц[а-я]+ в крипт[а-я]+",
    r"(?i)получ[а-я]+ доход",
    r"(?i)пассивн[а-я]+ доход",
    r"(?i)зараб[а-я]+ без вложен[а-я]+",
    r"(?i)обуч[а-я]+ трейд[а-я]+",
    r"(?i)присоедин[а-я]+ к бот[а-я]+",
    r"(?i)приглаш[а-я]+ в чат",
    r"(?i)реклам[а-я]+ пост",
    r"(?i)розыгрыш приз[а-я]+",
    r"(?i)бесплатн[а-я]+ курс",
    r"(?i)переход[а-я]+ по ссылк[а-я]+",
    r"(?i)админ[а-я]+ бот[а-я]+",
    r"(?i)telegram-канал",
    r"(?i)заходи[а-я]+ в бот[а-я]+",
    r"(?i)(t\.me|telegram\.me)\/[a-zA-Z0-9_]+",
    r"(?i)подпис[а-я]+ на канал",
    r"(?i)подзаработ[а-я]+",
    r"(?i)быстр[а-я]+ деньг[а-я]+",
]

# Сведения об исторических личностях
HISTORICAL_FIGURES = {
    "пушкин": {
        "full_name": "Александр Сергеевич Пушкин",
        "years": "1799-1837",
        "category": "Поэт, драматург, прозаик, публицист, критик",
        "description": "Величайший русский поэт, драматург и прозаик, основоположник современного русского литературного языка.",
        "works": ["Евгений Онегин", "Руслан и Людмила", "Капитанская дочка", "Борис Годунов", "Медный всадник"],
    },
    "гоголь": {
        "full_name": "Николай Васильевич Гоголь",
        "years": "1809-1852",
        "category": "Прозаик, драматург, поэт, критик, публицист",
        "description": "Русский прозаик, драматург, поэт, критик, публицист, признанный одним из классиков русской литературы.",
        "works": ["Мертвые души", "Ревизор", "Тарас Бульба", "Вечера на хуторе близ Диканьки", "Петербургские повести"],
    },
    "толстой": {
        "full_name": "Лев Николаевич Толстой",
        "years": "1828-1910",
        "category": "Писатель, мыслитель",
        "description": "Один из наиболее известных русских писателей и мыслителей, автор романов 'Война и мир', 'Анна Каренина', 'Воскресение'.",
        "works": ["Война и мир", "Анна Каренина", "Воскресение", "Севастопольские рассказы", "Детство. Отрочество. Юность"],
    },
    "лермонтов": {
        "full_name": "Михаил Юрьевич Лермонтов",
        "years": "1814-1841",
        "category": "Поэт, прозаик, драматург",
        "description": "Русский поэт, прозаик, драматург, художник. Творчество Лермонтова, в котором сочетаются гражданские, философские и личные мотивы, отвечавшие насущным потребностям духовной жизни русского общества, ознаменовало собой новый расцвет русской литературы.",
        "works": ["Герой нашего времени", "Мцыри", "Демон", "Бородино", "Маскарад"],
    },
    "эйнштейн": {
        "full_name": "Альберт Эйнштейн",
        "years": "1879-1955",
        "category": "Физик-теоретик",
        "description": "Физик-теоретик, один из основателей современной теоретической физики, лауреат Нобелевской премии по физике 1921 года, общественный деятель-гуманист.",
        "discoveries": ["Теория относительности", "Фотоэлектрический эффект", "Броуновское движение", "E=mc²"],
    },
    "тесла": {
        "full_name": "Никола Тесла",
        "years": "1856-1943",
        "category": "Изобретатель, инженер, физик",
        "description": "Сербский и американский изобретатель и физик, создатель многих устройств на переменном токе, сделавший революционный вклад в развитие электротехники и радиотехники.",
        "discoveries": ["Электродвигатель на переменном токе", "Трансформатор Теслы", "Беспроводная передача энергии", "Радиоуправление"]
    },
    "ньютон": {
        "full_name": "Исаак Ньютон",
        "years": "1643-1727",
        "category": "Физик, математик, астроном",
        "description": "Английский физик, математик, механик и астроном, один из создателей классической физики и дифференциального и интегрального исчислений.",
        "discoveries": ["Закон всемирного тяготения", "Законы движения", "Корпускулярная теория света", "Исчисление бесконечно малых"]
    },
    "сократ": {
        "full_name": "Сократ",
        "years": "470-399 до н.э.",
        "category": "Философ",
        "description": "Древнегреческий философ, учение которого знаменует поворот в философии -- от рассмотрения природы и мира к рассмотрению человека.",
        "works": ["Диалоги (в записях Платона)", "Апология Сократа", "Сократический метод"]
    },
    "платон": {
        "full_name": "Платон",
        "years": "428/427-348/347 до н.э.",
        "category": "Философ",
        "description": "Древнегреческий философ, ученик Сократа, основатель Академии, одной из первых философских школ. Его идеалистическая философия оказала огромное влияние на последующее развитие философской мысли.",
        "works": ["Государство", "Пир", "Федон", "Теэтет", "Софист"]
    }
}

# Категории моделей для более удобного представления
MODEL_CATEGORIES = {
    "Продвинутые": [
        "meta-llama/Llama-3.3-70B-Instruct",
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        "mistralai/Mistral-Large-Instruct-2411",
        "databricks/dbrx-instruct",
        "google/gemma-3-27b-it",
    ],
    "С возможностью анализа изображений": [
        "meta-llama/Llama-3.2-90B-Vision-Instruct",
        "Qwen/Qwen2-VL-7B-Instruct",
    ],
    "Специализированные": [
        "Qwen/Qwen2.5-Coder-32B-Instruct",
        "nvidia/AceMath-7B-Instruct",
        "jinaai/ReaderLM-v2",
        "watt-ai/watt-tool-70B",
    ],
    "Универсальные": [
        "Qwen/QwQ-32B",
        "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
        "mistralai/Ministral-8B-Instruct-2410",
        "netease-youdao/Confucius-01-14B",
        "microsoft/phi-4",
        "bespokelabs/Bespoke-Stratos-32B",
        "NovaSky-AI/Sky-T1-32B-Preview",
        "tiiuae/Falcon3-10B-Instruct",
        "THUDM/glm-4-9b-chat",
        "CohereForAI/aya-expanse-326",
        "openbmb/MiniCPM3-4B",
        "Qwen/Qwen2.5-1.5B-Instruct",
        "ozone-ai/ox-1",
        "microsoft/Phi-3.5-mini-instruct",
        "ibm-granite/granite-3.1-8b-instruct",
        "SentientAGI/Dobby-Mini-Unhinged-Llama-3.1-8B",
        "neuralmagic/Llama-3.1-Nemotron-70B-Instruct-HF-FP8-dynamic",
    ]
}

# Модели для различных типов вопросов
SPECIALIZED_MODELS = {
    "code": ["Qwen/Qwen2.5-Coder-32B-Instruct", "watt-ai/watt-tool-70B"],
    "math": ["nvidia/AceMath-7B-Instruct"],
    "reading": ["jinaai/ReaderLM-v2"],
    "history": ["meta-llama/Llama-3.3-70B-Instruct", "mistralai/Mistral-Large-Instruct-2411"],
    "literature": ["meta-llama/Llama-3.3-70B-Instruct", "mistralai/Mistral-Large-Instruct-2411"],
    "science": ["meta-llama/Llama-3.3-70B-Instruct", "google/gemma-3-27b-it"],
    "medicine": ["databricks/dbrx-instruct", "meta-llama/Llama-3.3-70B-Instruct"],
    "philosophy": ["mistralai/Mistral-Large-Instruct-2411", "netease-youdao/Confucius-01-14B"],
}

# Список всех моделей из категорий
ALL_MODELS = []
for category, models in MODEL_CATEGORIES.items():
    ALL_MODELS.extend(models)

# Приветственные фразы для простых вопросов
GREETINGS = {
    r"(?i)^(привет|хай|здравствуй|здрасте|хелло|hi|hello)": [
        "Привет! Чем я могу вам помочь?",
        "Здравствуйте! Готов помочь вам.",
        "Приветствую! Задавайте ваш вопрос."
    ],
    r"(?i)^как дела|как (ты|у тебя)": [
        "Всё отлично, спасибо! Чем могу помочь?",
        "Работаю в штатном режиме. Чем могу быть полезен?",
        "У меня всё хорошо. Готов помочь вам."
    ],
    r"(?i)^доброе утро": [
        "Доброе утро! Чем я могу помочь вам сегодня?",
        "Доброе утро! Готов к работе."
    ],
    r"(?i)^добрый день": [
        "Добрый день! Чем могу быть полезен?",
        "Добрый день! Готов ответить на ваши вопросы."
    ],
    r"(?i)^добрый вечер": [
        "Добрый вечер! Чем я могу вам помочь?",
        "Добрый вечер! Готов к работе."
    ]
}

# Регулярные выражения для определения типов вопросов
TOPIC_PATTERNS = {
    "code": r"(?i)(код|программ|скрипт|функци|метод|класс|python|java|javascript|html|css|sql|bash|ruby|golang|c\+\+)",
    "math": r"(?i)(математик|уравнени|вычисли|решить|задач|дробь|интеграл|производн|алгебр|геометри)",
    "history": r"(?i)(истори|[\d]{3,4} год|древн|средневеков|войн|революци|импери|государств|царь|король)",
    "literature": r"(?i)(литератур|писатель|поэт|стих|роман|повесть|рассказ|книг|поэм)",
    "science": r"(?i)(наук|физик|хими|биолог|астроном|геолог|географ|теор|эксперимент)",
    "medicine": r"(?i)(медицин|здоровь|болезн|лечени|диагноз|врач|пациент|симптом|терапи|хирург)",
    "philosophy": r"(?i)(философ|мысл|этик|мораль|сознани|бытие|познани|онтолог|гносеолог)",
}

# Шаблоны для распознавания запросов об исторических личностях
HISTORICAL_PATTERN = r"(?i)(?:кто (?:так(ой|ая|ое|ие)|был|явля(?:ет|л)ся|известен как)|расскаж(?:и|ите) (?:о|про|мне о|мне про)|что (?:ты |вы )?знаешь (?:о|про)|информаци[яю] (?:о|про))\s+([А-Яа-яЁё]+)"

# Словарь для хранения статистики запросов по пользователям и ограничения частоты запросов
rate_limits = {}

# Словарь для хранения временных сообщений "AI пишет..."
thinking_messages = {}

# Настройка логирования с защитой от ошибок файловой системы и ротацией
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO if not CONFIG["DEBUG_MODE"] else logging.DEBUG)

try:
    # Создаем ротируемый файловый обработчик логов
    from logging.handlers import RotatingFileHandler
    
    log_file_path = os.path.join(LOG_DIR, "bot.log")
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=CONFIG["LOG_ROTATION_SIZE"],
        backupCount=CONFIG["LOG_BACKUPS_COUNT"],
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    
    # Отдельный файл для ошибок
    error_log_path = os.path.join(LOG_DIR, "errors.log")
    error_handler = RotatingFileHandler(
        error_log_path,
        maxBytes=5*1024*1024,  # 5 МБ максимальный размер
        backupCount=3,  # Хранить до 3 файлов ротации
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s\n%(pathname)s:%(lineno)d\n'))
    logger.addHandler(error_handler)
    
except Exception as e:
    print(f"Не удалось настроить файловый логгер: {e}")
    # Продолжаем работу без файлового логгера

# Всегда добавляем консольный логгер
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

# Основные компоненты
bot = Bot(token=CONFIG["TOKEN"])
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)
dp.message.middleware(ChatActionMiddleware())

# FSM для состояний бота
class UserStates(StatesGroup):
    waiting_for_message = State()  # Ожидание сообщения
    custom_system_prompt = State()  # Ввод пользовательского системного промпта
    waiting_for_model_selection = State()  # Выбор модели
    waiting_for_temperature = State()  # Настройка temperature
    waiting_for_feedback = State()  # Ожидание отзыва о качестве ответа
    waiting_for_direct_model = State()  # Ожидание ввода конкретной модели
    waiting_for_image_caption = State()  # Ожидание подписи к изображению
    waiting_for_admin_broadcast = State()  # Ожидание сообщения для рассылки от админа
    waiting_for_premium_code = State()  # Ожидание ввода премиум-кода
    waiting_for_file_processing = State()  # Ожидание выбора типа обработки файла
    waiting_for_spam_pattern = State()  # Ожидание ввода нового паттерна спама

# Кэш и переменные для моделей
model_cache = {}  # Кэш ответов моделей
user_settings = {}  # Настройки пользователей
user_contexts = {}  # История диалогов с пользователями
user_feedback = {}  # Отзывы пользователей о качестве ответов
model_performance = {}  # Статистика производительности моделей (для адаптивного выбора)
request_stats = {}  # Статистика запросов
user_files = {}  # Временное хранилище файлов пользователей
premium_codes = set()  # Набор действительных премиум-кодов
user_states = {}  # Хранение информации о состоянии пользователей между командами
blocked_users = set()  # Множество заблокированных пользователей для спама

# Создаем словарь для хранения пользовательских сессий и состояний обработки
user_sessions = {}  

# HTTP сессия для асинхронных запросов
http_session = None

# Класс для сбора и хранения метрик работы бота - исправлен для Render
class BotMetrics:
    """Класс для сбора и хранения метрик работы бота."""
    
    def __init__(self):
        self.start_time = time.time()
        self.requests_total = 0
        self.requests_success = 0
        self.requests_failed = 0
        self.response_times = []
        self.errors = {}
        self.active_users = set()
        self.models_usage = {}
        self.topics_usage = {}
        self.daily_stats = {}
        self.spam_blocked = 0
        self.complex_queries = 0  # Счетчик сложных запросов
        self.lock = asyncio.Lock()
        
        # Загружаем сохраненные метрики, если они есть
        self._load_metrics()
    
    async def initialize(self):
        """Асинхронная инициализация - запускается после запуска event loop"""
        asyncio.create_task(self._periodic_save())
    
    async def record_request(self, user_id: int, success: bool, response_time: float, model: str = None, 
                           topic: str = None, error: str = None, is_complex: bool = False):
        """Записывает информацию о запросе."""
        async with self.lock:
            self.requests_total += 1
            if success:
                self.requests_success += 1
                self.response_times.append(response_time)
                # Держим только последние 1000 времен ответа для экономии памяти
                if len(self.response_times) > 1000:
                    self.response_times = self.response_times[-1000:]
            else:
                self.requests_failed += 1
                if error:
                    self.errors[error] = self.errors.get(error, 0) + 1
            
            self.active_users.add(user_id)
            
            if is_complex:
                self.complex_queries += 1
                
            if model:
                self.models_usage[model] = self.models_usage.get(model, 0) + 1
                
            if topic:
                self.topics_usage[topic] = self.topics_usage.get(topic, 0) + 1
                
            # Обновляем дневную статистику
            today = date.today().isoformat()
            if today not in self.daily_stats:
                self.daily_stats[today] = {
                    "requests": 0,
                    "success": 0,
                    "failed": 0,
                    "unique_users": set(),
                    "models": {},
                    "topics": {},
                    "spam_blocked": 0,
                    "complex_queries": 0
                }
            
            daily = self.daily_stats[today]
            daily["requests"] += 1
            
            if success:
                daily["success"] += 1
            else:
                daily["failed"] += 1
                
            daily["unique_users"].add(user_id)
            
            if is_complex:
                daily["complex_queries"] = daily.get("complex_queries", 0) + 1
                
            if model:
                daily["models"][model] = daily["models"].get(model, 0) + 1
                
            if topic:
                daily["topics"][topic] = daily["topics"].get(topic, 0) + 1
    
    def record_spam_block(self):
        """Учитывает блокировку спама."""
        self.spam_blocked += 1
        
        today = date.today().isoformat()
        if today in self.daily_stats:
            self.daily_stats[today]["spam_blocked"] = self.daily_stats[today].get("spam_blocked", 0) + 1
    
    def get_stats(self) -> dict:
        """Возвращает текущую статистику бота."""
        uptime = time.time() - self.start_time
        avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0
        
        # Для JSON-сериализации преобразуем множества в списки
        daily_stats_json = {}
        for day, stats in self.daily_stats.items():
            daily_stats_json[day] = {
                "requests": stats["requests"],
                "success": stats["success"],
                "failed": stats["failed"],
                "unique_users": len(stats["unique_users"]),
                "models": stats["models"],
                "topics": stats["topics"],
                "spam_blocked": stats.get("spam_blocked", 0),
                "complex_queries": stats.get("complex_queries", 0)
            }
        
        return {
            "uptime_seconds": uptime,
            "uptime_formatted": self._format_uptime(uptime),
            "requests": {
                "total": self.requests_total,
                "success": self.requests_success,
                "failed": self.requests_failed,
                "success_rate": (self.requests_success / self.requests_total * 100) if self.requests_total else 0
            },
            "response_time": {
                "average_ms": avg_response_time * 1000,
                "min_ms": min(self.response_times) * 1000 if self.response_times else 0,
                "max_ms": max(self.response_times) * 1000 if self.response_times else 0
            },
            "users": {
                "active_count": len(self.active_users)
            },
            "models": {
                k: v for k, v in sorted(self.models_usage.items(), key=lambda x: x[1], reverse=True)
            },
            "topics": {
                k: v for k, v in sorted(self.topics_usage.items(), key=lambda x: x[1], reverse=True)
            },
            "top_errors": {
                k: v for k, v in sorted(self.errors.items(), key=lambda x: x[1], reverse=True)[:5]
            },
            "daily_stats": daily_stats_json,
            "spam_blocked": self.spam_blocked,
            "complex_queries": self.complex_queries,
            "timestamp": datetime.now().isoformat(),
            "version": BOT_VERSION
        }
    
    def _load_metrics(self):
        """Загружает сохраненные метрики."""
        try:
            metrics_file = os.path.join(STATS_DIR, "latest_metrics.json")
            if os.path.exists(metrics_file):
                with open(metrics_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    self.requests_total = data.get("requests", {}).get("total", 0)
                    self.requests_success = data.get("requests", {}).get("success", 0)
                    self.requests_failed = data.get("requests", {}).get("failed", 0)
                    self.errors = data.get("top_errors", {})
                    self.models_usage = data.get("models", {})
                    self.topics_usage = data.get("topics", {})
                    self.spam_blocked = data.get("spam_blocked", 0)
                    self.complex_queries = data.get("complex_queries", 0)
                    
                    # Загружаем дневную статистику
                    daily_stats = data.get("daily_stats", {})
                    for day, stats in daily_stats.items():
                        self.daily_stats[day] = {
                            "requests": stats.get("requests", 0),
                            "success": stats.get("success", 0),
                            "failed": stats.get("failed", 0),
                            "unique_users": set(),
                            "models": stats.get("models", {}),
                            "topics": stats.get("topics", {}),
                            "spam_blocked": stats.get("spam_blocked", 0),
                            "complex_queries": stats.get("complex_queries", 0)
                        }
                        
                        # Уникальных пользователей загрузить не можем (они были преобразованы в count)
                        
                    logger.info("Метрики успешно загружены из сохраненного файла")
        except Exception as e:
            logger.error(f"Ошибка при загрузке метрик: {e}")
    
    async def _periodic_save(self):
        """Периодически сохраняет метрики."""
        while True:
            await asyncio.sleep(300)  # Сохраняем каждые 5 минут
            await self._save_metrics()
    
    async def _save_metrics(self):
        """Сохраняет текущие метрики."""
        try:
            stats = self.get_stats()
            # Сохраняем как текущие метрики
            metrics_file = os.path.join(STATS_DIR, "latest_metrics.json")
            
            # Асинхронная запись файла
            async with aio_open(metrics_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(stats, ensure_ascii=False, indent=2))
                
            # Также сохраняем с временной меткой каждый час
            current_hour = datetime.now().strftime('%Y%m%d_%H')
            hourly_file = os.path.join(STATS_DIR, f"metrics_{current_hour}.json")
            if not os.path.exists(hourly_file):
                async with aio_open(hourly_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(stats, ensure_ascii=False, indent=2))
                
                # Очищаем старые файлы метрик (оставляем только 48 последних = 2 дня)
                await self._cleanup_old_metrics(48)
        except Exception as e:
            logger.error(f"Ошибка при сохранении метрик: {e}")
    
    async def _cleanup_old_metrics(self, keep_count: int):
        """Очищает старые файлы метрик, оставляя только указанное количество."""
        try:
            metrics_files = glob.glob(os.path.join(STATS_DIR, "metrics_*.json"))
            metrics_files.sort(key=os.path.getmtime)
            
            if len(metrics_files) > keep_count:
                for old_file in metrics_files[:-keep_count]:
                    try:
                        os.remove(old_file)
                        logger.debug(f"Удален старый файл метрик: {old_file}")
                    except Exception as e:
                        logger.warning(f"Не удалось удалить старый файл метрик {old_file}: {e}")
        except Exception as e:
            logger.warning(f"Ошибка при очистке старых файлов метрик: {e}")
    
    def _format_uptime(self, seconds: float) -> str:
        """Форматирует время работы в человекочитаемый вид."""
        days, remainder = divmod(int(seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days} дн.")
        if hours > 0 or days > 0:
            parts.append(f"{hours} ч.")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{minutes} мин.")
        parts.append(f"{seconds} сек.")
        
        return " ".join(parts)

# Создаем экземпляр метрик
bot_metrics = BotMetrics()

# Функции-декораторы
def with_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0,
               exceptions: tuple = (Exception,)):
    """Декоратор для повторного выполнения функции при исключениях.
    
    Args:
        max_retries: Максимальное количество повторных попыток
        delay: Начальная задержка между попытками (секунды)
        backoff: Множитель для увеличения задержки с каждой попыткой
        exceptions: Кортеж исключений, при которых выполнять повторные попытки
        
    Returns:
        Декоратор функции
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            mtries, mdelay = max_retries, delay
            
            while mtries > 0:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    mtries -= 1
                    if mtries <= 0:
                        logger.error(f"Функция {func.__name__} не выполнена после {max_retries} попыток")
                        raise
                    
                    logger.warning(f"Повторная попытка {max_retries - mtries}/{max_retries} для {func.__name__}: {str(e)}")
                    
                    # Увеличиваем задержку с каждой попыткой (экспоненциальный backoff)
                    await asyncio.sleep(mdelay)
                    mdelay *= backoff
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def admin_only(func):
    """Декоратор для функций, доступных только администраторам."""
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        if message.from_user.id not in CONFIG["ADMIN_IDS"]:
            await message.answer("⛔ Эта команда доступна только администраторам.")
            return
        return await func(message, *args, **kwargs)
    return wrapper

def rate_limit(func):
    """Декоратор для ограничения частоты запросов от пользователя."""
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        user_id = message.from_user.id
        username = message.from_user.username
        
        # Проверяем, не является ли пользователь администратором или премиум-пользователем
        if user_id in CONFIG["ADMIN_IDS"] or username == "qqq5599" or user_id in CONFIG["PREMIUM_USER_IDS"]:
            return await func(message, *args, **kwargs)
        
        current_time = time.time()
        window_size = CONFIG["RATE_LIMIT_WINDOW"]
        max_requests = CONFIG["RATE_LIMIT_MAX_REQUESTS"]
        
        if user_id not in rate_limits:
            rate_limits[user_id] = {"requests": [], "warned": False}
        
        # Очищаем старые запросы
        rate_limits[user_id]["requests"] = [req_time for req_time in rate_limits[user_id]["requests"] 
                                         if current_time - req_time < window_size]
        
        # Проверяем, не превышен ли лимит
        if len(rate_limits[user_id]["requests"]) >= max_requests:
            if not rate_limits[user_id]["warned"]:
                await message.answer(
                    f"⚠️ Вы отправляете слишком много запросов. Пожалуйста, подождите {window_size} секунд перед "
                    f"следующим запросом. Лимит: {max_requests} запросов за {window_size} секунд."
                )
                rate_limits[user_id]["warned"] = True
            return
        
        # Добавляем текущий запрос
        rate_limits[user_id]["requests"].append(current_time)
        rate_limits[user_id]["warned"] = False
        
        return await func(message, *args, **kwargs)
    return wrapper

def spam_filter(func):
    """Декоратор для фильтрации спама и рекламы."""
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        if not CONFIG["ENABLE_SPAM_PROTECTION"]:
            return await func(message, *args, **kwargs)
            
        user_id = message.from_user.id
        
        # Администраторы не подпадают под фильтр спама
        if user_id in CONFIG["ADMIN_IDS"]:
            return await func(message, *args, **kwargs)
            
        # Проверяем наличие сообщения
        if message.text:
            # Проверяем текст сообщения на наличие спам-паттернов
            for pattern in SPAM_PATTERNS:
                if re.search(pattern, message.text):
                    # Блокируем спам
                    bot_metrics.record_spam_block()
                    
                    # Добавляем пользователя в список потенциальных спамеров
                    blocked_users.add(user_id)
                    
                    # Логируем инцидент
                    logger.warning(f"Заблокирован спам от пользователя {user_id}: {message.text[:100]}...")
                    
                    # Уведомляем пользователя
                    await message.answer(
                        "⛔ Ваше сообщение было определено как потенциальный спам или реклама и не было обработано. "
                        "Пожалуйста, не отправляйте рекламные материалы или ссылки на сторонние ресурсы."
                    )
                    
                    # Уведомляем администраторов о спаме
                    for admin_id in CONFIG["ADMIN_IDS"]:
                        try:
                            await bot.send_message(
                                admin_id,
                                f"🚫 **Обнаружен спам**\n\n"
                                f"**Пользователь**: `{user_id}`\n"
                                f"**Паттерн**: `{pattern}`\n\n"
                                f"**Текст**:\n```\n{message.text[:300]}...\n```",
                                parse_mode=ParseMode.MARKDOWN
                            )
                        except Exception as e:
                            logger.error(f"Не удалось отправить уведомление о спаме администратору {admin_id}: {e}")
                    
                    return
        
        # Если сообщение прошло проверку, выполняем обработчик
        return await func(message, *args, **kwargs)
    return wrapper

# Декоратор для сохранения контекста при исключениях
def safe_execution(f):
    @wraps(f)
    async def wrapped(*args, **kwargs):
        user_id = None
        start_time = time.time()
        success = False
        error_message = None
        model = None
        topic = None
        is_complex = False
        
        # Пытаемся извлечь user_id из аргументов
        for arg in args:
            if isinstance(arg, Message) and arg.from_user:
                user_id = arg.from_user.id
                # Пытаемся определить тему, если есть текст сообщения
                if arg.text:
                    topic = detect_question_topic(arg.text)
                    # Определяем сложность запроса по длине текста
                    is_complex = len(arg.text) > 300
                break
            elif isinstance(arg, CallbackQuery) and arg.from_user:
                user_id = arg.from_user.id
                break
        
        # Извлекаем модель из настроек пользователя, если возможно
        if user_id and str(user_id) in user_settings:
            model = user_settings[str(user_id)].get("model")
        
        try:
            result = await f(*args, **kwargs)
            success = True
            return result
        except Exception as e:
            # Получаем информацию о вызывающей функции
            error_context = {
                'function': f.__name__,
                'args': str(args),
                'kwargs': str(kwargs),
                'exception': str(e),
                'traceback': traceback.format_exc()
            }
            
            error_message = str(e)
            
            # Логируем ошибку с полным контекстом
            logger.error(f"Ошибка в {f.__name__}: {str(e)}\n{traceback.format_exc()}")
            
            # Удаляем сообщение "AI пишет..." если оно есть
            if user_id in thinking_messages and thinking_messages[user_id]:
                try:
                    await bot.delete_message(
                        chat_id=thinking_messages[user_id]["chat_id"],
                        message_id=thinking_messages[user_id]["message_id"]
                    )
                    thinking_messages[user_id] = None
                except Exception:
                    pass
            
            # Если среди аргументов есть сообщение, отправляем уведомление
            for arg in args:
                if isinstance(arg, Message):
                    try:
                        await arg.answer("Произошла техническая ошибка. Попробуйте еще раз или обратитесь к администратору.")
                    except Exception:
                        pass
                    break
            return None
        finally:
            # Записываем метрики
            if user_id:
                execution_time = time.time() - start_time
                await bot_metrics.record_request(
                    user_id, success, execution_time, model, topic, 
                    error_message, is_complex=is_complex
                )
    return wrapped

# Функции-помощники
def format_model_name(model_name: str) -> str:
    """Форматирует имя модели для отображения."""
    return model_name.split('/')[-1]

def detect_question_topic(text: str) -> Optional[str]:
    """Определяет тему вопроса для выбора специализированной модели."""
    for topic, pattern in TOPIC_PATTERNS.items():
        if re.search(pattern, text):
            return topic
    return None

def get_best_model_for_topic(topic: str) -> Optional[str]:
    """Возвращает лучшую модель для конкретной темы."""
    if topic in SPECIALIZED_MODELS and SPECIALIZED_MODELS[topic]:
        # Выбираем случайную модель из списка специализированных
        import random
        return random.choice(SPECIALIZED_MODELS[topic])
    return None

def clean_markdown(text: str) -> str:
    """Очищает и исправляет потенциально неправильный Markdown в тексте."""
    if not text:
        return ""
    
    # Счетчики для проверки парности Markdown символов
    backticks_count = text.count('`')
    asterisk_count = text.count('*')
    underscore_count = text.count('_')
    
    # Проверяем и исправляем непарные одиночные обратные кавычки
    if backticks_count % 2 != 0:
        # Находим последнюю обратную кавычку и удаляем её
        last_backtick_pos = text.rfind('`')
        if last_backtick_pos != -1:
            text = text[:last_backtick_pos] + text[last_backtick_pos+1:]
    
    # Проверяем и исправляем блоки кода
    code_blocks = re.findall(r'```[\s\S]*?```', text)
    for block in code_blocks:
        # Если блок кода не заканчивается правильно
        if not block.endswith('```'):
            text = text.replace(block, block + '```')
    
    # Находим незавершенные блоки кода (начинаются с ```, но не заканчиваются ```)
    matches = re.finditer(r'```(?:[\s\S]*?)(?!```[\s\S]*?$)', text)
    for match in matches:
        start_pos = match.start()
        # Добавляем закрывающий блок кода в конец
        text += '\n```'
    
    # Проверяем и исправляем непарные звездочки для курсива/жирного
    if asterisk_count % 2 != 0:
        # Простая фиксация - удаляем последнюю звездочку
        last_asterisk_pos = text.rfind('*')
        if last_asterisk_pos != -1:
            text = text[:last_asterisk_pos] + text[last_asterisk_pos+1:]
    
    # Проверяем и исправляем непарные подчеркивания для курсива
    if underscore_count % 2 != 0:
        # Простая фиксация - удаляем последнее подчеркивание
        last_underscore_pos = text.rfind('_')
        if last_underscore_pos != -1:
            text = text[:last_underscore_pos] + text[last_underscore_pos+1:]
    
    return text

async def get_cached_response(cache_key: str, max_age: int = None) -> Optional[dict]:
    """Получает кэшированный ответ если он существует и не истек срок действия.
    
    Args:
        cache_key: Ключ кэша
        max_age: Максимальный возраст кэша в секундах (None = использовать CONFIG["CACHE_TIMEOUT"])
        
    Returns:
        Dict с ответом или None если кэш отсутствует или устарел
    """
    cache_file = os.path.join(CACHE_DIR, f"{hashlib.md5(cache_key.encode()).hexdigest()}.json")
    
    if not os.path.exists(cache_file):
        return None
        
    try:
        async with aio_open(cache_file, 'r', encoding='utf-8') as f:
            cached_data = json.loads(await f.read())
            
        # Проверяем возраст кэша
        cache_time = cached_data.get("timestamp", 0)
        max_age = max_age or CONFIG["CACHE_TIMEOUT"]
        
        if time.time() - cache_time > max_age:
            # Кэш устарел
            return None
            
        return cached_data.get("data")
    except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
        logger.warning(f"Ошибка при чтении кэша {cache_key}: {e}")
        return None

async def set_cached_response(cache_key: str, data: Any) -> bool:
    """Сохраняет ответ в кэш.
    
    Args:
        cache_key: Ключ кэша
        data: Данные для сохранения
        
    Returns:
        True в случае успеха, False в случае ошибки
    """
    cache_file = os.path.join(CACHE_DIR, f"{hashlib.md5(cache_key.encode()).hexdigest()}.json")
    
    try:
        cache_data = {
            "timestamp": time.time(),
            "data": data
        }
        
        async with aio_open(cache_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(cache_data, ensure_ascii=False, indent=2))
            
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении кэша {cache_key}: {e}")
        return False

async def save_data_to_json(data: Any, filename: str, version: int = None) -> bool:
    """Безопасно сохраняет данные в JSON-файл с защитой от потери данных и версионированием.
    
    Args:
        data: Данные для сохранения
        filename: Имя файла (без пути)
        version: Версия данных для версионирования (опционально)
        
    Returns:
        True в случае успеха, False в случае ошибки
    """
    filepath = os.path.join(CONFIG["PERSISTENT_STORAGE"], filename)
    temp_filepath = f"{filepath}.tmp"
    backup_filepath = f"{filepath}.bak"
    
    try:
        # Создаем директорию если она не существует
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Добавляем метаданные версионирования
        if isinstance(data, dict) and version is not None:
            data_with_meta = {
                "_meta": {
                    "version": version,
                    "timestamp": datetime.now().isoformat(),
                    "schema_version": 1
                },
                "data": data
            }
        else:
            data_with_meta = data
        
        # Сначала записываем во временный файл
        async with aio_open(temp_filepath, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data_with_meta, ensure_ascii=False, indent=2))
        
        # Затем копируем текущий файл в бекап, если он существует
        if os.path.exists(filepath):
            # Сохраняем бэкап в отдельной директории с временной меткой
            backup_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"{os.path.basename(filepath)}.{backup_time}.bak"
            versioned_backup = os.path.join(BACKUP_DIR, backup_filename)
            
            # Копируем текущий файл и в бекап директорию тоже
            shutil.copy2(filepath, backup_filepath)
            shutil.copy2(filepath, versioned_backup)
        
        # И наконец, перемещаем временный файл на место основного
        os.replace(temp_filepath, filepath)
        
        # Периодическая очистка старых версий бэкапов (оставляем только 20 последних)
        await cleanup_old_backups(filename)
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении файла {filename}: {e}\n{traceback.format_exc()}")
        return False

async def cleanup_old_backups(filename_pattern: str, max_backups: int = 20):
    """Очищает старые резервные копии, оставляя только указанное количество последних.
    
    Args:
        filename_pattern: Паттерн имени файла для поиска в бэкапах
        max_backups: Максимальное количество бэкапов для сохранения
    """
    try:
        # Находим все файлы бэкапов с указанным паттерном
        backup_files = glob.glob(os.path.join(BACKUP_DIR, f"{filename_pattern}.*.bak"))
        
        # Сортируем по времени изменения (от старых к новым)
        backup_files.sort(key=os.path.getmtime)
        
        # Удаляем старые файлы, если их больше max_backups
        if len(backup_files) > max_backups:
            files_to_delete = backup_files[:-max_backups]
            for file_path in files_to_delete:
                try:
                    os.remove(file_path)
                    logger.debug(f"Удален старый бэкап: {file_path}")
                except OSError as e:
                    logger.warning(f"Не удалось удалить старый бэкап {file_path}: {e}")
    except Exception as e:
        logger.warning(f"Ошибка при очистке старых бэкапов: {e}")
        # Не прерываем основной процесс из-за ошибки

async def load_data_from_json(filename: str, default_data: Any = None) -> Any:
    """Безопасно загружает данные из JSON-файла с восстановлением из резервной копии.
    
    Args:
        filename: Имя файла (без пути)
        default_data: Данные по умолчанию, если не удалось загрузить файл
        
    Returns:
        Загруженные данные или default_data
    """
    filepath = os.path.join(CONFIG["PERSISTENT_STORAGE"], filename)
    backup_filepath = f"{filepath}.bak"
    
    try:
        # Пытаемся прочитать основной файл
        async with aio_open(filepath, 'r', encoding='utf-8') as f:
            data = json.loads(await f.read())
            
            # Проверяем и извлекаем данные, если есть метаданные
            if isinstance(data, dict) and "_meta" in data and "data" in data:
                return data["data"]
            return data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Не удалось загрузить {filename}: {e}. Попытка восстановления из бекапа.")
        
        try:
            # Пытаемся восстановить из бекапа
            if os.path.exists(backup_filepath):
                async with aio_open(backup_filepath, 'r', encoding='utf-8') as f:
                    data = json.loads(await f.read())
                    
                    # Проверяем и извлекаем данные, если есть метаданные
                    if isinstance(data, dict) and "_meta" in data and "data" in data:
                        return data["data"]
                    return data
        except Exception as be:
            logger.error(f"Не удалось восстановить из бекапа {filename}: {be}")
        
        # Если не удалось загрузить из бекапа, ищем в директории бэкапов
        try:
            # Находим самый новый бэкап в директории бэкапов
            backup_files = glob.glob(os.path.join(BACKUP_DIR, f"{filename}.*.bak"))
            if backup_files:
                # Сортируем по времени изменения (от новых к старым)
                backup_files.sort(key=os.path.getmtime, reverse=True)
                async with aio_open(backup_files[0], 'r', encoding='utf-8') as f:
                    data = json.loads(await f.read())
                    
                    # Проверяем и извлекаем данные, если есть метаданные
                    if isinstance(data, dict) and "_meta" in data and "data" in data:
                        return data["data"]
                    return data
        except Exception as e:
            logger.error(f"Не удалось восстановить из версионного бэкапа {filename}: {e}")
        
        # Возвращаем данные по умолчанию, если загрузка и восстановление не удались
        return default_data if default_data is not None else {}

async def save_user_settings():
    """Сохраняет настройки пользователей в JSON-файл."""
    await save_data_to_json(user_settings, 'user_settings.json', version=1)

async def load_user_settings():
    """Загружает настройки пользователей из JSON-файла."""
    global user_settings
    user_settings = await load_data_from_json('user_settings.json', {})

    # Миграция старых настроек и добавление новых полей
    for user_id, settings in user_settings.items():
        if "requests_left" not in settings:
            user_settings[user_id]["requests_left"] = CONFIG["MAX_DAILY_REQUESTS"]
            user_settings[user_id]["last_reset"] = str(date.today())
        if "model" not in settings:
            user_settings[user_id]["model"] = ALL_MODELS[0]
        if "system_prompt" not in settings:
            user_settings[user_id]["system_prompt"] = CONFIG["DEFAULT_SYSTEM_PROMPT"]
        if "temperature" not in settings:
            user_settings[user_id]["temperature"] = CONFIG["TEMPERATURE"]
        if "contexts" not in settings:
            user_settings[user_id]["contexts"] = {}
        # Новые поля для расширенной функциональности
        if "preferred_topics" not in settings:
            user_settings[user_id]["preferred_topics"] = []
        if "last_active" not in settings:
            user_settings[user_id]["last_active"] = str(date.today())
        if "favorite_models" not in settings:
            user_settings[user_id]["favorite_models"] = []
        if "is_premium" not in settings:
            user_settings[user_id]["is_premium"] = False
        if "premium_until" not in settings:
            user_settings[user_id]["premium_until"] = None
        if "language" not in settings:
            user_settings[user_id]["language"] = "ru"
        if "notifications_enabled" not in settings:
            user_settings[user_id]["notifications_enabled"] = True
        if "auto_translate" not in settings:
            user_settings[user_id]["auto_translate"] = False
        if "interface_mode" not in settings:
            user_settings[user_id]["interface_mode"] = "standard"  # standard/advanced
        if "stream_mode" not in settings:
            user_settings[user_id]["stream_mode"] = CONFIG["STREAM_RESPONSES"] # Потоковый режим ответов

    await save_user_settings()

async def load_blocked_users():
    """Загружает список заблокированных пользователей."""
    global blocked_users
    blocked_data = await load_data_from_json('blocked_users.json', {"users": []})
    blocked_users = set(blocked_data.get("users", []))

async def save_blocked_users():
    """Сохраняет список заблокированных пользователей."""
    await save_data_to_json({"users": list(blocked_users)}, 'blocked_users.json', version=1)

async def save_spam_patterns():
    """Сохраняет список паттернов спама."""
    await save_data_to_json({"patterns": SPAM_PATTERNS}, 'spam_patterns.json', version=1)

async def load_spam_patterns():
    """Загружает список паттернов спама."""
    global SPAM_PATTERNS
    patterns_data = await load_data_from_json('spam_patterns.json', {"patterns": SPAM_PATTERNS})
    SPAM_PATTERNS = patterns_data.get("patterns", SPAM_PATTERNS)

async def save_user_contexts():
    """Сохраняет контексты пользователей в JSON-файл."""
    # Преобразуем ключи (int) в строки для JSON
    serializable_contexts = {str(k): v for k, v in user_contexts.items()}
    await save_data_to_json(serializable_contexts, 'user_contexts.json', version=1)

async def load_user_contexts():
    """Загружает контексты пользователей из JSON-файла."""
    global user_contexts
    serialized_contexts = await load_data_from_json('user_contexts.json', {})
    # Преобразуем ключи обратно в int
    user_contexts = {int(k): v for k, v in serialized_contexts.items()}

async def save_model_performance():
    """Сохраняет данные о производительности моделей."""
    await save_data_to_json(model_performance, 'model_performance.json', version=1)

async def load_model_performance():
    """Загружает данные о производительности моделей."""
    global model_performance
    model_performance = await load_data_from_json('model_performance.json', {})
    
    # Инициализация новой модели, если её нет в статистике
    for model in ALL_MODELS:
        if model not in model_performance:
            model_performance[model] = {
                "successes": 0,
                "failures": 0,
                "avg_response_time": 0,
                "total_responses": 0,
                "topics": {}
            }
    
    await save_model_performance()

async def load_premium_codes():
    """Загружает премиум-коды из файла."""
    global premium_codes
    premium_codes_data = await load_data_from_json('premium_codes.json', {"codes": []})
    premium_codes = set(premium_codes_data.get("codes", []))

async def save_premium_codes():
    """Сохраняет премиум-коды в файл."""
    await save_data_to_json({"codes": list(premium_codes)}, 'premium_codes.json', version=1)

def generate_premium_code() -> str:
    """Генерирует новый уникальный премиум-код."""
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    premium_codes.add(code)
    return code

def is_premium_user(user_id: int) -> bool:
    """Проверяет, является ли пользователь премиум-пользователем."""
    if user_id in CONFIG["ADMIN_IDS"]:
        return True
        
    if str(user_id) not in user_settings:
        return False
        
    settings = user_settings[str(user_id)]
    
    # Проверяем наличие премиум-статуса и его срок
    if settings.get("is_premium", False):
        premium_until = settings.get("premium_until")
        if premium_until:
            try:
                expiry_date = datetime.fromisoformat(premium_until)
                if expiry_date > datetime.now():
                    return True
                else:
                    # Срок премиум-статуса истек
                    settings["is_premium"] = False
            except ValueError:
                # Некорректный формат даты
                settings["is_premium"] = False
        else:
            # Премиум без ограничения по времени
            return True
    
    return False

async def activate_premium(user_id: int, duration_days: int = 30) -> bool:
    """Активирует премиум-статус для пользователя.
    
    Args:
        user_id: ID пользователя
        duration_days: Продолжительность премиума в днях (0 = бессрочно)
        
    Returns:
        True если активация успешна, False в случае ошибки
    """
    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "model": ALL_MODELS[0],
            "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
            "temperature": CONFIG["TEMPERATURE"],
            "requests_left": CONFIG["MAX_DAILY_REQUESTS"],
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today()),
            "is_premium": False,
            "premium_until": None,
            "language": "ru",
            "notifications_enabled": True,
            "auto_translate": False,
            "interface_mode": "standard",
            "stream_mode": CONFIG["STREAM_RESPONSES"]
        }
    
    try:
        user_settings[str(user_id)]["is_premium"] = True
        
        if duration_days > 0:
            # Устанавливаем срок действия премиума
            premium_until = (datetime.now() + timedelta(days=duration_days)).isoformat()
            user_settings[str(user_id)]["premium_until"] = premium_until
        else:
            # Бессрочный премиум
            user_settings[str(user_id)]["premium_until"] = None
            
        # Добавляем пользователя в список премиум-пользователей
        if user_id not in CONFIG["PREMIUM_USER_IDS"]:
            CONFIG["PREMIUM_USER_IDS"].append(user_id)
            
        await save_user_settings()
        return True
    except Exception as e:
        logger.error(f"Ошибка при активации премиум-статуса: {e}")
        return False

def match_query_with_historical_figure(query: str) -> Optional[Tuple[str, dict]]:
    """Проверяет, относится ли запрос к исторической личности, и возвращает информацию о ней."""
    # Пытаемся найти шаблон "кто такой X" или "расскажи о X"
    match = re.search(HISTORICAL_PATTERN, query)
    if match:
        person_name = match.group(2).lower()
        
        # Проверяем есть ли в нашей базе такая личность
        for key, info in HISTORICAL_FIGURES.items():
            if person_name in key or key in person_name:
                return key, info
    
    # Также проверяем прямые упоминания в тексте
    for key, info in HISTORICAL_FIGURES.items():
        if key in query.lower():
            return key, info
    
    return None

async def send_thinking_animation(chat_id: int) -> Optional[int]:
    """Отправляет сообщение "AI пишет..." и возвращает его ID."""
    if not CONFIG["ENABLE_THINKING_ANIMATION"]:
        return None
        
    try:
        # Выбираем случайное сообщение о размышлении
        thinking_text = random.choice(CONFIG["THINKING_MESSAGES"])
        
        # Отправляем сообщение
        message = await bot.send_message(chat_id, thinking_text)
        
        # Сохраняем информацию о сообщении
        thinking_messages[chat_id] = {
            "message_id": message.message_id,
            "chat_id": chat_id,
            "text": thinking_text
        }
        
        return message.message_id
    except Exception as e:
        logger.warning(f"Не удалось отправить анимацию 'AI пишет': {e}")
        return None

async def remove_thinking_animation(chat_id: int) -> bool:
    """Удаляет сообщение "AI пишет..."."""
    if not CONFIG["ENABLE_THINKING_ANIMATION"]:
        return True
        
    if chat_id not in thinking_messages or thinking_messages[chat_id] is None:
        return False
        
    try:
        # Удаляем сообщение
        await bot.delete_message(
            chat_id=thinking_messages[chat_id]["chat_id"],
            message_id=thinking_messages[chat_id]["message_id"]
        )
        
        # Очищаем информацию о сообщении
        thinking_messages[chat_id] = None
        return True
    except Exception as e:
        logger.warning(f"Не удалось удалить анимацию 'AI пишет': {e}")
        return False

async def show_typing_action(chat_id: int, duration: float = 2.0):
    """Показывает индикатор набора текста с указанной продолжительностью."""
    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(duration)
    except Exception as e:
        logger.warning(f"Не удалось отправить статус набора текста: {e}")

def get_user_model(user_id: int, message_text: str = None) -> str:
    """Возвращает оптимальную модель для пользователя и типа вопроса."""
    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "model": ALL_MODELS[0],
            "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
            "temperature": CONFIG["TEMPERATURE"],
            "requests_left": CONFIG["MAX_DAILY_REQUESTS"],
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today()),
            "is_premium": False,
            "premium_until": None,
            "language": "ru",
            "notifications_enabled": True,
            "auto_translate": False,
            "interface_mode": "standard",
            "stream_mode": CONFIG["STREAM_RESPONSES"]
        }
    
    # Базовая модель пользователя
    base_model = user_settings[str(user_id)].get("model", ALL_MODELS[0])
    
    # Если текст сообщения не предоставлен, возвращаем базовую модель
    if not message_text:
        return base_model
    
    # Для длинных запросов используем наиболее мощные модели
    if len(message_text) > 800:
        for category_name in ["Продвинутые"]:
            category = MODEL_CATEGORIES.get(category_name, [])
            if category:
                # Выбираем случайную продвинутую модель для большого запроса
                return random.choice(category)
    
    # Проверка, относится ли запрос к исторической личности
    historical_match = match_query_with_historical_figure(message_text)
    if historical_match:
        # Используем специализированную модель для исторических вопросов
        if "history" in SPECIALIZED_MODELS and SPECIALIZED_MODELS["history"]:
            import random
            return random.choice(SPECIALIZED_MODELS["history"])
    
    # Определяем тему вопроса
    topic = detect_question_topic(message_text)
    if not topic:
        return base_model
    
    # Добавляем тему в предпочтения пользователя
    preferred_topics = user_settings[str(user_id)].get("preferred_topics", [])
    if topic not in preferred_topics:
        preferred_topics.append(topic)
        if len(preferred_topics) > 5:  # Ограничиваем количество сохраняемых тем
            preferred_topics.pop(0)
        user_settings[str(user_id)]["preferred_topics"] = preferred_topics
    
    # Попробуем найти специализированную модель для темы
    specialized_model = get_best_model_for_topic(topic)
    if specialized_model:
        logger.info(f"Выбрана специализированная модель {specialized_model} для темы {topic}")
        return specialized_model
    
    return base_model

def get_system_prompt(user_id: int) -> str:
    """Возвращает системный промпт пользователя или промпт по умолчанию."""
    if str(user_id) not in user_settings:
        return CONFIG["DEFAULT_SYSTEM_PROMPT"]
    return user_settings[str(user_id)].get("system_prompt", CONFIG["DEFAULT_SYSTEM_PROMPT"])

def get_user_temperature(user_id: int) -> float:
    """Возвращает значение temperature для пользователя или значение по умолчанию."""
    if str(user_id) not in user_settings:
        return CONFIG["TEMPERATURE"]
    return user_settings[str(user_id)].get("temperature", CONFIG["TEMPERATURE"])

def get_user_stream_mode(user_id: int) -> bool:
    """Возвращает предпочтение пользователя по потоковой отправке ответов."""
    if str(user_id) not in user_settings:
        return CONFIG["STREAM_RESPONSES"]
    return user_settings[str(user_id)].get("stream_mode", CONFIG["STREAM_RESPONSES"])

def get_user_context(user_id: int) -> List[Dict[str, str]]:
    """Возвращает историю диалога с пользователем."""
    if user_id not in user_contexts:
        user_contexts[user_id] = []
    return user_contexts[user_id]

def add_to_user_context(user_id: int, role: str, content: str, importance: float = 1.0):
    """Добавляет сообщение в историю диалога с пользователем."""
    if user_id not in user_contexts:
        user_contexts[user_id] = []

    # Добавляем новое сообщение с уровнем важности
    user_contexts[user_id].append({
        "role": role, 
        "content": content,
        "timestamp": datetime.now().isoformat(),
        "importance": importance
    })

    # Ограничиваем длину истории с учетом важности сообщений
    if len(user_contexts[user_id]) > CONFIG["MAX_CONTEXT_LENGTH"] * 2:
        # Сортируем сообщения по важности (кроме системного в начале)
        system_messages = [msg for msg in user_contexts[user_id] if msg["role"] == "system"]
        other_messages = [msg for msg in user_contexts[user_id] if msg["role"] != "system"]
        
        # Сортируем по важности и времени
        other_messages.sort(key=lambda x: (x.get("importance", 0), x.get("timestamp", "")), reverse=True)
        
        # Оставляем только самые важные сообщения
        keep_count = CONFIG["MAX_CONTEXT_LENGTH"] * 2 - len(system_messages)
        user_contexts[user_id] = system_messages + other_messages[:keep_count]

def clear_user_context(user_id: int):
    """Очищает историю диалога с пользователем."""
    if user_id in user_contexts:
        # Сохраняем только системный промпт, если он есть
        system_messages = [msg for msg in user_contexts[user_id] if msg["role"] == "system"]
        user_contexts[user_id] = system_messages if system_messages else []

def update_context_importance(user_id: int, feedback: int):
    """Обновляет важность сообщений в контексте на основе обратной связи."""
    if user_id not in user_contexts or len(user_contexts[user_id]) < 2:
        return
    
    # Находим последние сообщения пользователя и ассистента
    last_messages = user_contexts[user_id][-2:]
    
    # Для положительной обратной связи увеличиваем важность, для отрицательной - уменьшаем
    importance_modifier = 1.2 if feedback > 0 else 0.8
    
    for msg in last_messages:
        if "importance" in msg:
            msg["importance"] = msg["importance"] * importance_modifier

def prepare_api_messages(context: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Подготавливает сообщения для API из контекста с учетом важности."""
    # Отбираем только необходимые поля для API
    api_messages = []
    
    for msg in context:
        if "role" in msg and "content" in msg:
            # Базовое сообщение для API
            api_msg = {"role": msg["role"], "content": msg["content"]}
            api_messages.append(api_msg)
    
    return api_messages

def is_greeting(text: str) -> Optional[str]:
    """Проверяет, является ли текст приветствием, и возвращает ответ, если да."""
    import random
    for pattern, responses in GREETINGS.items():
        if re.match(pattern, text.strip()):
            return random.choice(responses)
    return None

def record_model_performance(model: str, success: bool, response_time: float, topic: Optional[str] = None):
    """Записывает данные о производительности модели."""
    if model not in model_performance:
        model_performance[model] = {
            "successes": 0,
            "failures": 0,
            "avg_response_time": 0,
            "total_responses": 0,
            "topics": {}
        }
    
    # Обновляем общую статистику
    stats = model_performance[model]
    if success:
        stats["successes"] += 1
    else:
        stats["failures"] += 1
    
    # Обновляем среднее время ответа
    total_responses = stats["total_responses"]
    if total_responses > 0:
        current_avg = stats["avg_response_time"]
        stats["avg_response_time"] = (current_avg * total_responses + response_time) / (total_responses + 1)
    else:
        stats["avg_response_time"] = response_time
    
    stats["total_responses"] += 1
    
    # Обновляем статистику по темам, если указана тема
    if topic:
        if topic not in stats["topics"]:
            stats["topics"][topic] = {"successes": 0, "failures": 0}
        
        topic_stats = stats["topics"][topic]
        if success:
            topic_stats["successes"] += 1
        else:
            topic_stats["failures"] += 1

def record_request_stat(user_id: int, success: bool, model: str, topic: Optional[str] = None):
    """Записывает статистику запросов пользователя."""
    if user_id not in request_stats:
        request_stats[user_id] = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "models": {},
            "topics": {}
        }
    
    stats = request_stats[user_id]
    stats["total"] += 1
    
    if success:
        stats["successful"] += 1
    else:
        stats["failed"] += 1
    
    # Статистика по моделям
    if model not in stats["models"]:
        stats["models"][model] = {"count": 0, "successful": 0, "failed": 0}
    
    model_stats = stats["models"][model]
    model_stats["count"] += 1
    if success:
        model_stats["successful"] += 1
    else:
        model_stats["failed"] += 1
    
    # Статистика по темам
    if topic:
        if topic not in stats["topics"]:
            stats["topics"][topic] = {"count": 0, "successful": 0, "failed": 0}
        
        topic_stats = stats["topics"][topic]
        topic_stats["count"] += 1
        if success:
            topic_stats["successful"] += 1
        else:
            topic_stats["failed"] += 1

def get_historical_figure_response(figure_key: str, info: dict) -> str:
    """Формирует ответ с информацией об исторической личности."""
    response = f"# {info['full_name']} ({info['years']})\n\n"
    response += f"**Категория**: {info['category']}\n\n"
    response += f"**Описание**: {info['description']}\n\n"
    
    if "works" in info:
        response += "**Известные произведения**:\n"
        for i, work in enumerate(info["works"], 1):
            response += f"{i}. {work}\n"
    
    if "discoveries" in info:
        response += "**Известные открытия**:\n"
        for i, discovery in enumerate(info["discoveries"], 1):
            response += f"{i}. {discovery}\n"
    
    return response

async def create_backup_zip():
    """Создает полный бэкап данных в формате ZIP."""
    try:
        # Создаем имя файла с датой и временем
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.zip"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        # Создаем ZIP-архив
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Добавляем все JSON файлы из DATA_DIR
            for root, _, files in os.walk(DATA_DIR):
                for file in files:
                    if file.endswith('.json'):
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, DATA_DIR)
                        zipf.write(file_path, arcname)
        
        # Удаляем старые бэкапы, оставляя только 5 последних
        backups = glob.glob(os.path.join(BACKUP_DIR, "backup_*.zip"))
        backups.sort(key=os.path.getmtime)
        if len(backups) > 5:
            for old_backup in backups[:-5]:
                os.remove(old_backup)
        
        logger.info(f"Создан полный бэкап данных: {backup_filename}")
        return backup_path
    except Exception as e:
        logger.error(f"Ошибка при создании бэкапа: {e}")
        return None

def generate_error_report(error_info: Dict[str, Any], include_logs: bool = True) -> str:
    """Генерирует отчет об ошибке для отправки администраторам."""
    report = f"🚨 **Отчет об ошибке**\n\n"
    report += f"**Время**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    report += f"**Версия бота**: {BOT_VERSION}\n\n"
    
    report += f"**Функция**: {error_info.get('function', 'Неизвестно')}\n"
    report += f"**Ошибка**: {error_info.get('exception', 'Неизвестно')}\n\n"
    
    # Добавляем Traceback в сокращенном виде
    traceback_text = error_info.get('traceback', '')
    if traceback_text:
        # Ограничиваем длину traceback для отправки в сообщении
        max_traceback_length = 1000
        if len(traceback_text) > max_traceback_length:
            traceback_text = traceback_text[:max_traceback_length] + "...[сокращено]"
        report += f"**Traceback**:\n```\n{traceback_text}\n```\n\n"
    
    report += f"**Активных пользователей**: {len(bot_metrics.active_users)}\n"
    report += f"**Всего запросов**: {bot_metrics.requests_total}\n"
    
    return report

@safe_execution
async def process_image(photo: PhotoSize) -> Optional[str]:
    """Обрабатывает изображение и возвращает его в base64 кодировке."""
    try:
        file_info = await bot.get_file(photo.file_id)
        file_path = file_info.file_path

        if file_info.file_size > CONFIG["MAX_FILE_SIZE"]:
            return None

        # Получаем файл через Telegram API с использованием aiohttp
        file_url = f"https://api.telegram.org/file/bot{CONFIG['TOKEN']}/{file_path}"
        
        async with http_session.get(file_url, timeout=CONFIG["REQUEST_TIMEOUT"]) as response:
            if response.status != 200:
                logger.error(f"Ошибка получения файла: HTTP {response.status}")
                return None
                
            response_content = await response.read()

        # Кодируем файл в base64
        file_content = base64.b64encode(response_content).decode('utf-8')

        # Определяем тип файла
        file_extension = file_path.split('.')[-1].lower()
        if file_extension not in CONFIG["ALLOWED_FORMATS"]:
            logger.warning(f"Неподдерживаемый формат изображения: {file_extension}")
            return None

        return f"data:image/{file_extension};base64,{file_content}"

    except Exception as e:
        logger.error(f"Ошибка при обработке изображения: {e}")
        return None

@safe_execution
async def split_and_send_message(message: Message, text: str, parse_mode: Optional[str] = ParseMode.MARKDOWN):
    """Разделяет длинный текст на части и отправляет их."""
    max_length = CONFIG["MAX_MESSAGE_LENGTH"]

    # Очищаем Markdown если он используется
    if parse_mode == ParseMode.MARKDOWN:
        text = clean_markdown(text)

    if len(text) <= max_length:
        try:
            return await message.answer(text, parse_mode=parse_mode)
        except TelegramAPIError as e:
            logger.warning(f"Ошибка при отправке сообщения: {e}")
            # Пробуем отправить без форматирования
            try:
                return await message.answer(text, parse_mode=None)
            except Exception as e2:
                logger.error(f"Не удалось отправить сообщение даже без форматирования: {e2}")
                return None
        return None

    # Разбиваем на части с сохранением целостности блоков кода
    parts = []
    current_part = ""
    code_block = False

    for line in text.split('\n'):
        # Проверяем, является ли строка началом или концом блока кода
        if line.strip().startswith('```') and line.strip().count('```') % 2 != 0:
            code_block = not code_block

        # Если текущая часть + строка не превышает лимит
        if len(current_part + line + '\n') <= max_length:
            current_part += line + '\n'
        else:
            # Если мы находимся в блоке кода, завершаем его перед разрывом
            if code_block:
                current_part += '```\n'
                parts.append(current_part)
                current_part = '```' + line.split('```', 1)[-1] + '\n'
                # Восстанавливаем состояние блока кода
                if line.strip().count('```') % 2 != 0:
                    code_block = not code_block
            else:
                parts.append(current_part)
                current_part = line + '\n'

    # Добавляем последнюю часть
    if current_part:
        parts.append(current_part)

    # Отправляем все части
    last_message = None
    for i, part in enumerate(parts):
        try:
            last_message = await message.answer(part, parse_mode=parse_mode)
        except TelegramAPIError as e:
            logger.warning(f"Ошибка при отправке части сообщения: {e}")
            # Пробуем отправить без форматирования
            try:
                last_message = await message.answer(part, parse_mode=None)
            except Exception as e2:
                logger.error(f"Не удалось отправить часть сообщения даже без форматирования: {e2}")
        await asyncio.sleep(0.3)  # Небольшая задержка между сообщениями
    
    return last_message

@safe_execution
async def stream_and_send_response(message: Message, text: str, parse_mode: Optional[str] = ParseMode.MARKDOWN) -> Optional[Message]:
    """Потоковый вывод сообщения: текст появляется постепенно через регулярные обновления."""
    # Если текст короткий, отправляем его обычным способом
    if len(text) < 200:
        return await message.answer(text, parse_mode=parse_mode)
    
    # Очищаем Markdown если он используется
    if parse_mode == ParseMode.MARKDOWN:
        text = clean_markdown(text)
    
    # Разбиваем текст на токены для постепенного обновления
    # (здесь для простоты используем пробелы, но можно использовать более сложную токенизацию)
    tokens = []
    if len(text) > 4000:  # Для очень длинных текстов используем более крупные чанки
        tokens = [text[i:i+100] for i in range(0, len(text), 100)]
    else:
        tokens = [text[i:i+30] for i in range(0, len(text), 30)]
    
    if not tokens:
        return await message.answer(text, parse_mode=parse_mode)
    
    # Отправляем первую часть
    try:
        current_message = await message.answer(tokens[0], parse_mode=parse_mode)
    except TelegramAPIError as e:
        logger.warning(f"Ошибка при отправке первой части: {e}")
        return await message.answer(text, parse_mode=None)
    
    current_text = tokens[0]
    
    # Постепенно обновляем сообщение
    for i in range(1, len(tokens)):
        try:
            current_text += tokens[i]
            
            # Обновляем каждый 2-3 токен (не каждый, чтобы не превышать лимиты API)
            if i % 3 == 0 or i == len(tokens) - 1:
                await current_message.edit_text(current_text, parse_mode=parse_mode)
                # Небольшая пауза между обновлениями для эффекта печати
                await asyncio.sleep(0.2)
        except TelegramAPIError as e:
            logger.warning(f"Ошибка при обновлении сообщения: {e}")
            
            # Если сообщение стало слишком длинным, отправляем новое
            if "message is too long" in str(e).lower() or "message to edit not found" in str(e).lower():
                try:
                    # Отправляем оставшуюся часть текста
                    rest_of_text = text[len(current_text):]
                    if rest_of_text:
                        current_message = await message.answer(rest_of_text, parse_mode=parse_mode)
                        current_text = rest_of_text
                except Exception as e2:
                    logger.error(f"Не удалось отправить продолжение: {e2}")
                    # Если не получилось, отправляем обычным способом
                    return await split_and_send_message(message, text, parse_mode)
            else:
                # Другие ошибки - пробуем без форматирования
                try:
                    await current_message.edit_text(current_text, parse_mode=None)
                except Exception:
                    pass
    
    return current_message

async def create_model_selection_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора модели по категориям."""
    builder = InlineKeyboardBuilder()

    # Добавляем кнопки категорий
    for category in MODEL_CATEGORIES:
        builder.row(
            InlineKeyboardButton(
                text=f"📚 {category} ({len(MODEL_CATEGORIES[category])})",
                callback_data=f"category:{category}"
            )
        )
    
    # Добавляем кнопку для ввода конкретной модели
    builder.row(
        InlineKeyboardButton(
            text="🔍 Ввести название модели вручную",
            callback_data="enter_model_manually"
        )
    )
    
    # Показываем кнопку для избранных моделей
    builder.row(
        InlineKeyboardButton(
            text="⭐ Избранные модели",
            callback_data="favorite_models"
        )
    )

    return builder.as_markup()

async def create_favorite_models_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру с избранными моделями пользователя."""
    builder = InlineKeyboardBuilder()
    
    favorite_models = user_settings.get(str(user_id), {}).get("favorite_models", [])
    
    for model in favorite_models:
        builder.row(
            InlineKeyboardButton(
                text=format_model_name(model),
                callback_data=f"model:{model}"
            )
        )
    
    # Кнопка "Назад"
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к категориям",
            callback_data="back_to_categories"
        )
    )
    
    return builder.as_markup()

async def create_category_models_keyboard(category: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру с моделями определенной категории."""
    builder = InlineKeyboardBuilder()

    # Добавляем модели из выбранной категории
    for model in MODEL_CATEGORIES.get(category, []):
        builder.row(
            InlineKeyboardButton(
                text=format_model_name(model),
                callback_data=f"model:{model}"
            )
        )

    # Кнопка "Назад"
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к категориям",
            callback_data="back_to_categories"
        )
    )

    return builder.as_markup()

async def create_temperature_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора значения temperature."""
    builder = InlineKeyboardBuilder()

    # Значения temperature от 0.0 до 1.0 с шагом 0.2
    values = [
        ("0.0 (Наиболее точно)", "0.0"),
        ("0.2 (Точно)", "0.2"),
        ("0.4 (Сбалансировано)", "0.4"),
        ("0.6 (Творчески)", "0.6"),
        ("0.8 (Более творчески)", "0.8"),
        ("1.0 (Максимально творчески)", "1.0")
    ]

    for label, value in values:
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=f"temp:{value}"
            )
        )

    return builder.as_markup()

async def create_feedback_keyboard(message_id: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для обратной связи о качестве ответа."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="👍 Хороший ответ", callback_data=f"feedback:good:{message_id}"),
        InlineKeyboardButton(text="👎 Плохой ответ", callback_data=f"feedback:bad:{message_id}")
    )
    
    builder.row(
        InlineKeyboardButton(text="🔄 Перефразировать", callback_data=f"rephrase:{message_id}"),
        InlineKeyboardButton(text="📝 Подробнее", callback_data=f"elaborate:{message_id}")
    )
    
    return builder.as_markup()

async def create_file_processing_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора типа обработки файла."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="📄 Анализ текста", callback_data="file_process:analyze_text")
    )
    
    builder.row(
        InlineKeyboardButton(text="📊 Анализ данных", callback_data="file_process:analyze_data")
    )
    
    builder.row(
        InlineKeyboardButton(text="🔍 Извлечь информацию", callback_data="file_process:extract_info")
    )
    
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="file_process:cancel")
    )
    
    return builder.as_markup()

async def create_stream_mode_keyboard(current_mode: bool) -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора режима отображения ответов."""
    builder = InlineKeyboardBuilder()
    
    current_text = "✅ Включен" if current_mode else "❌ Выключен"
    
    builder.row(
        InlineKeyboardButton(
            text=f"Потоковый режим: {current_text}",
            callback_data="stream_info"
        )
    )
    
    builder.row(
        InlineKeyboardButton(
            text="🔄 Включить потоковый режим" if not current_mode else "🔄 Выключить потоковый режим",
            callback_data=f"toggle_stream:{not current_mode}"
        )
    )
    
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к настройкам",
            callback_data="back_to_settings"
        )
    )
    
    return builder.as_markup()

async def create_admin_spam_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для управления спам-фильтром."""
    builder = InlineKeyboardBuilder()
    
    current_status = "✅ Включена" if CONFIG["ENABLE_SPAM_PROTECTION"] else "❌ Выключена"
    
    builder.row(
        InlineKeyboardButton(
            text=f"Защита от спама: {current_status}",
            callback_data="spam_status"
        )
    )
    
    builder.row(
        InlineKeyboardButton(
            text="🔄 Включить защиту" if not CONFIG["ENABLE_SPAM_PROTECTION"] else "🔄 Выключить защиту",
            callback_data=f"toggle_spam:{not CONFIG['ENABLE_SPAM_PROTECTION']}"
        )
    )
    
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить спам-паттерн",
            callback_data="add_spam_pattern"
        ),
        InlineKeyboardButton(
            text="🔍 Посмотреть паттерны",
            callback_data="view_spam_patterns"
        )
    )
    
    builder.row(
        InlineKeyboardButton(
            text=f"👥 Заблокировано: {len(blocked_users)}",
            callback_data="view_blocked_users"
        ),
        InlineKeyboardButton(
            text="🧹 Очистить блок-лист",
            callback_data="clear_blocked_users"
        )
    )
    
    return builder.as_markup()

@safe_execution
@with_retry(max_retries=3, delay=1.0, backoff=2.0)
async def get_ai_response(user_id: int, message_text: str, image_data: Optional[str] = None) -> str:
    """Получает ответ от API на основе настроек пользователя."""
    # Сначала проверяем, не запрос ли это об известной исторической личности
    historical_match = match_query_with_historical_figure(message_text)
    if historical_match:
        figure_key, info = historical_match
        return get_historical_figure_response(figure_key, info)
    
    # Определяем тему вопроса для выбора оптимальной модели
    topic = detect_question_topic(message_text)
    
    # Получаем наиболее подходящую модель
    model = get_user_model(user_id, message_text)
    system_prompt = get_system_prompt(user_id)
    temperature = get_user_temperature(user_id)

    # Для сложных запросов не используем кэш
    is_complex_query = len(message_text) > 300
    
    # Проверяем кэш для экономии запросов к API (для не сложных запросов)
    if not is_complex_query:
        cache_key = f"{model}:{message_text}:{temperature}"
        cached_response = await get_cached_response(cache_key)
        if cached_response:
            return cached_response

    # Получаем контекст пользователя
    context = get_user_context(user_id)

    # Если контекст пуст, добавляем системное сообщение
    if not context:
        add_to_user_context(user_id, "system", system_prompt)
        context = get_user_context(user_id)

    # Создаем новое сообщение от пользователя
    user_message = {"role": "user", "content": message_text}

    # Если есть изображение, добавляем его в сообщение
    if image_data:
        user_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": message_text},
                {"type": "image_url", "image_url": {"url": image_data}}
            ]
        }

    # Добавляем сообщение пользователя в контекст
    add_to_user_context(user_id, "user", message_text)

    # Подготавливаем сообщения для API
    api_messages = prepare_api_messages(context)

    # Подготавливаем данные для API
    payload = {
        "model": model,
        "messages": api_messages,
        "temperature": temperature,
        "max_tokens": CONFIG["MAX_TOKENS"]
    }

    # Выполняем запрос к API с несколькими попытками
    start_time = time.time()
    for attempt in range(CONFIG["RETRY_ATTEMPTS"]):
        try:
            # Используем aiohttp вместо requests для асинхронных запросов
            async with http_session.post(
                f"{CONFIG['API_URL']}/chat/completions",
                headers={"Authorization": f"Bearer {CONFIG['API_KEY']}"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=CONFIG["REQUEST_TIMEOUT"])
            ) as response:
                if response.status != 200:
                    # Только если это последняя попытка, возвращаем текст ошибки
                    if attempt == CONFIG["RETRY_ATTEMPTS"] - 1 or not CONFIG["FALLBACK_MODE"]:
                        return f"❌ Ошибка при обработке запроса (HTTP {response.status}). Пожалуйста, попробуйте позже."
                    
                    # Записываем неудачную попытку
                    record_model_performance(model, False, time.time() - start_time, topic)
                    record_request_stat(user_id, False, model, topic)
                    
                    # Переключаемся на другую модель
                    available_models = [m for m in ALL_MODELS if m != model]
                    if available_models:
                        import random
                        model = random.choice(available_models)
                        payload["model"] = model
                        logger.info(f"Переключение на модель: {model}")
                        continue
                    else:
                        return "❌ Не удалось найти работающую модель. Пожалуйста, попробуйте позже."
                
                # Получаем данные ответа
                data = await response.json()

                if 'choices' in data and data['choices']:
                    ai_response = data['choices'][0]['message']['content']
                    response_time = time.time() - start_time

                    # Кэшируем ответ (только для не сложных запросов)
                    if not is_complex_query:
                        await set_cached_response(cache_key, ai_response)

                    # Добавляем ответ в контекст пользователя
                    add_to_user_context(user_id, "assistant", ai_response)
                    
                    # Записываем статистику производительности модели
                    record_model_performance(model, True, response_time, topic)
                    record_request_stat(user_id, True, model, topic)

                    return ai_response
                else:
                    # Если нет данных в ответе
                    if attempt == CONFIG["RETRY_ATTEMPTS"] - 1:
                        return "❌ Получен некорректный ответ от сервера. Пожалуйста, попробуйте позже."

        except asyncio.TimeoutError:
            logger.error(f"Таймаут при запросе к API для модели {model}")
            record_model_performance(model, False, CONFIG["REQUEST_TIMEOUT"], topic)
            record_request_stat(user_id, False, model, topic)
            
            # Если это последняя попытка
            if attempt == CONFIG["RETRY_ATTEMPTS"] - 1:
                return "❌ Запрос к серверу AI превысил лимит времени. Пожалуйста, попробуйте позже или задайте более короткий вопрос."
            
            # Переключаемся на другую модель
            if CONFIG["FALLBACK_MODE"]:
                # Выбираем модель с наименьшим средним временем ответа
                fastest_models = sorted(
                    [(m, model_performance[m]["avg_response_time"]) for m in model_performance if m != model],
                    key=lambda x: x[1]
                )
                
                if fastest_models:
                    model = fastest_models[0][0]
                    payload["model"] = model
                    logger.info(f"Переключение на более быструю модель: {model}")
                    continue
        
        except Exception as e:
            logger.error(f"Ошибка при запросе к API: {str(e)}")
            return f"❌ Произошла ошибка: {str(e)[:100]}... Пожалуйста, попробуйте позже."

    # Если все попытки не удались
    return "❌ Все модели временно недоступны. Пожалуйста, попробуйте позже."

@safe_execution
async def rephrase_answer(user_id: int, original_text: str, instruction: str) -> str:
    """Перефразирует или дополняет предыдущий ответ с заданной инструкцией."""
    model = get_user_model(user_id)
    temperature = get_user_temperature(user_id)
    
    # Создаем специальный запрос для перефразирования
    rephrase_prompt = f"{instruction}:\n\n{original_text}"
    
    # Получаем контекст пользователя без добавления этого запроса
    context = get_user_context(user_id)
    
    # Подготавливаем данные для API
    api_messages = prepare_api_messages(context)
    api_messages.append({"role": "user", "content": rephrase_prompt})
    
    payload = {
        "model": model,
        "messages": api_messages,
        "temperature": temperature,
        "max_tokens": CONFIG["MAX_TOKENS"]
    }
    
    try:
        # Используем aiohttp вместо синхронного requests
        async with http_session.post(
            f"{CONFIG['API_URL']}/chat/completions",
            headers={"Authorization": f"Bearer {CONFIG['API_KEY']}"},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=CONFIG["REQUEST_TIMEOUT"])
        ) as response:
            if response.status != 200:
                return f"❌ Ошибка при обработке запроса (HTTP {response.status}). Пожалуйста, попробуйте позже."
                
            data = await response.json()
            
            if 'choices' in data and data['choices']:
                return data['choices'][0]['message']['content']
            else:
                return "❌ Получен некорректный ответ от сервера. Пожалуйста, попробуйте позже."
        
    except Exception as e:
        logger.error(f"Ошибка при перефразировании: {e}")
        return f"❌ Ошибка при обработке запроса: {str(e)[:100]}... Пожалуйста, попробуйте позже."
    
    return "❌ Не удалось перефразировать ответ. Пожалуйста, задайте новый вопрос."

async def process_file(user_id: int, file_id: str, file_name: str, process_type: str) -> str:
    """Обрабатывает файл в зависимости от выбранного типа обработки."""
    try:
        # Получаем файл через Telegram Bot API
        file_info = await bot.get_file(file_id)
        file_path = file_info.file_path
        file_url = f"https://api.telegram.org/file/bot{CONFIG['TOKEN']}/{file_path}"
        
        # Скачиваем файл асинхронно
        async with http_session.get(file_url, timeout=aiohttp.ClientTimeout(total=CONFIG["REQUEST_TIMEOUT"])) as response:
            if response.status != 200:
                return f"❌ Ошибка при загрузке файла (HTTP {response.status}). Пожалуйста, попробуйте позже."
                
            response_content = await response.read()
        
        # Сохраняем файл во временную директорию
        user_media_path = os.path.join(USER_MEDIA_DIR, str(user_id))
        os.makedirs(user_media_path, exist_ok=True)
        
        local_file_path = os.path.join(user_media_path, file_name)
        async with aio_open(local_file_path, 'wb') as f:
            await f.write(response_content)
        
        # Подготавливаем промпт в зависимости от типа обработки
        file_extension = os.path.splitext(file_name)[1].lower()
        file_content = None
        
        # Для текстовых файлов читаем содержимое
        if file_extension in ['.txt', '.md', '.csv', '.json', '.html', '.xml', '.py', '.js', '.css']:
            try:
                async with aio_open(local_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    file_content = await f.read()
                    
                    # Ограничиваем размер содержимого
                    max_content_length = 20000 # Увеличено для обработки больших файлов
                    if len(file_content) > max_content_length:
                        file_content = file_content[:max_content_length] + f"\n\n[Файл обрезан, показаны первые {max_content_length} символов из {len(file_content)}]"
            except UnicodeDecodeError:
                return f"❌ Не удалось прочитать файл '{file_name}' как текстовый документ. Возможно, формат файла не поддерживается."
        
        # Формируем промпт в зависимости от типа обработки
        prompt = ""
        if process_type == "analyze_text":
            prompt = f"Проанализируй следующий текстовый файл '{file_name}' и предоставь детальный анализ его содержимого, структуры и ключевых моментов. Структурируй ответ с использованием подзаголовков и маркированных списков для лучшей читаемости:\n\n{file_content}"
        elif process_type == "analyze_data":
            prompt = f"Проанализируй данные из файла '{file_name}' и представь основные статистические показатели, закономерности и выводы. Приведи графический анализ в текстовом виде, если это возможно, и структурируй свой ответ по секциям:\n\n{file_content}"
        elif process_type == "extract_info":
            prompt = f"Извлеки из файла '{file_name}' всю важную информацию, такую как даты, контакты, ключевые факты, и структурируй её в удобном формате. Организуй информацию в категории и используй таблицы или списки:\n\n{file_content}"
        else:
            return "❌ Неизвестный тип обработки файла."
        
        # Если файл не текстовый, предупреждаем пользователя
        if not file_content:
            return f"⚠️ Файл {file_name} не является текстовым документом, который можно проанализировать напрямую. Пожалуйста, загрузите текстовый файл (TXT, MD, CSV, JSON и т.д.)."
        
        # Отправляем запрос к API
        model = get_user_model(user_id)
        temperature = get_user_temperature(user_id)
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Вы - эксперт по анализу и обработке данных из файлов различных форматов. Предоставляйте детальные, структурированные и точные ответы с использованием Markdown-форматирования для улучшения читаемости."},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": CONFIG["MAX_TOKENS"]
        }
        
        async with http_session.post(
            f"{CONFIG['API_URL']}/chat/completions",
            headers={"Authorization": f"Bearer {CONFIG['API_KEY']}"},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=CONFIG["REQUEST_TIMEOUT"] * 2)  # Увеличенный таймаут для обработки файлов
        ) as response:
            if response.status != 200:
                return f"❌ Ошибка при обработке файла (HTTP {response.status}). Пожалуйста, попробуйте позже."
                
            data = await response.json()
        
        # Очищаем файл после обработки
        try:
            os.remove(local_file_path)
        except Exception as e:
            logger.warning(f"Не удалось удалить временный файл {local_file_path}: {e}")
            
        if 'choices' in data and data['choices']:
            result = data['choices'][0]['message']['content']
            return result
        else:
            return "❌ Не удалось получить результат анализа файла. Пожалуйста, попробуйте позже."
    
    except Exception as e:
        logger.error(f"Ошибка при обработке файла: {e}\n{traceback.format_exc()}")
        return f"❌ Произошла ошибка при обработке файла: {str(e)[:100]}... Пожалуйста, попробуйте позже."

async def verify_bot_startup():
    """Проверяет успешность запуска бота и работоспособность ключевых компонентов."""
    issues = []
    
    # Проверка токена бота
    try:
        me = await bot.get_me()
        logger.info(f"Подключен к боту: @{me.username} (ID: {me.id})")
    except Exception as e:
        issues.append(f"Ошибка подключения к Telegram API: {e}")
    
    # Проверка директорий
    dirs_to_check = [DATA_DIR, LOG_DIR, CACHE_DIR, BACKUP_DIR, USER_MEDIA_DIR, STATS_DIR]
    for dir_path in dirs_to_check:
        if not os.path.exists(dir_path) or not os.access(dir_path, os.W_OK):
            issues.append(f"Директория {dir_path} не существует или недоступна для записи")
    
    # Проверка API ключа (без фактических вызовов)
    if not CONFIG["API_KEY"] or len(CONFIG["API_KEY"]) < 20:
        issues.append("API_KEY отсутствует или выглядит невалидным")
    
    # Проверка URL вебхука
    if CONFIG["USE_WEBHOOK"]:
        if not APP_URL or not APP_URL.startswith("http"):
            issues.append(f"Некорректный URL для webhook: {APP_URL}")
    
    # Отчет о проверке
    if issues:
        logger.warning("При запуске обнаружены проблемы:")
        for issue in issues:
            logger.warning(f" - {issue}")
            
        # Отправляем уведомление администраторам
        for admin_id in CONFIG["ADMIN_IDS"]:
            try:
                issue_text = "\n".join([f"- {issue}" for issue in issues])
                await bot.send_message(
                    admin_id,
                    f"⚠️ При запуске бота обнаружены проблемы:\n\n{issue_text}"
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление о проблемах администратору {admin_id}: {e}")
    else:
        logger.info("✅ Все проверки при запуске прошли успешно")
        
    return len(issues) == 0

async def perform_health_check():
    """Выполняет периодическую проверку работоспособности бота."""
    while True:
        try:
            # Проверка доступности API
            api_health = True
            try:
                # Простой запрос к API для проверки доступности
                async with http_session.get(
                    f"{CONFIG['API_URL']}/health",
                    headers={"Authorization": f"Bearer {CONFIG['API_KEY']}"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        api_health = False
                        logger.warning(f"API недоступен, код ответа: {response.status}")
            except Exception as e:
                api_health = False
                logger.warning(f"Ошибка при проверке доступности API: {e}")
            
            # Проверка свободного места на диске
            disk_health = True
            try:
                total, used, free = shutil.disk_usage(DATA_DIR)
                disk_percent_used = used / total * 100
                
                if disk_percent_used > 95:  # Если занято более 95% диска
                    disk_health = False
                    logger.warning(f"Критически мало свободного места на диске: {disk_percent_used:.1f}% использовано")
            except Exception as e:
                logger.warning(f"Ошибка при проверке свободного места на диске: {e}")
            
            # Если есть проблемы, отправляем уведомления администраторам
            if not (api_health and disk_health):
                for admin_id in CONFIG["ADMIN_IDS"]:
                    try:
                        message = "⚠️ Выявлены проблемы при проверке работоспособности:\n\n"
                        if not api_health:
                            message += "- API недоступен или возвращает ошибку\n"
                        if not disk_health:
                            message += f"- Критически мало свободного места на диске: {disk_percent_used:.1f}% использовано\n"
                        
                        await bot.send_message(admin_id, message)
                    except Exception as e:
                        logger.error(f"Не удалось отправить уведомление о проблемах администратору {admin_id}: {e}")
            
            # Создаем резервную копию данных раз в день
            if datetime.now().hour == 3:  # Создаем бэкап в 3 часа ночи
                backup_path = await create_backup_zip()
                if backup_path:
                    # Уведомляем администратора о создании бэкапа
                    for admin_id in CONFIG["ADMIN_IDS"]:
                        try:
                            await bot.send_message(
                                admin_id, 
                                f"✅ Создана резервная копия данных: {os.path.basename(backup_path)}"
                            )
                        except Exception as e:
                            logger.error(f"Не удалось отправить уведомление о бэкапе администратору {admin_id}: {e}")

        except Exception as e:
            logger.error(f"Ошибка при выполнении проверки работоспособности: {e}")
        
        # Запускаем проверку с заданным интервалом
        await asyncio.sleep(CONFIG["HEALTH_CHECK_INTERVAL"])

# Обработчики команд и сообщений
@router.message(CommandStart())
@safe_execution
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    user_name = message.from_user.first_name
    user_id = message.from_user.id

    # Создаем клавиатуру быстрого доступа
    keyboard = ReplyKeyboardBuilder()
    keyboard.add(KeyboardButton(text="🔄 Новый диалог"))
    keyboard.add(KeyboardButton(text="⚙️ Настройки"))
    keyboard.add(KeyboardButton(text="🤖 Выбрать модель"))
    keyboard.add(KeyboardButton(text="📄 Загрузить файл"))
    keyboard.adjust(2)

    welcome_text = (
        f"👋 Здравствуйте, {user_name}!\n\n"
        f"🤖 Я профессиональный AI-ассистент, работающий на основе передовых языковых моделей.\n\n"
        f"🔍 Я могу помочь вам с:\n"
        f"• Ответами на вопросы и объяснениями\n"
        f"• Написанием и анализом кода\n"
        f"• Созданием и редактированием текстов\n"
        f"• Анализом данных и рассуждениями\n"
        f"• Анализом изображений (для поддерживаемых моделей)\n"
        f"• Обработкой и анализом файлов\n\n"
        f"💡 Просто напишите ваш вопрос или задачу, и я постараюсь помочь!"
    )

    await message.answer(
        welcome_text,
        reply_markup=keyboard.as_markup(resize_keyboard=True)
    )

    # Инициализируем настройки пользователя, если их еще нет
    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "model": ALL_MODELS[0],
            "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
            "temperature": CONFIG["TEMPERATURE"],
            "requests_left": CONFIG["MAX_DAILY_REQUESTS"],
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today()),
            "is_premium": False,
            "premium_until": None,
            "language": "ru",
            "notifications_enabled": True,
            "auto_translate": False,
            "interface_mode": "standard",
            "stream_mode": CONFIG["STREAM_RESPONSES"]
        }
        await save_user_settings()
    
    # Обновляем дату последней активности
    user_settings[str(user_id)]["last_active"] = str(date.today())
    await save_user_settings()

@router.message(Command("help"))
@safe_execution
async def cmd_help(message: Message):
    """Показывает справку по командам бота."""
    help_text = (
        "🔍 **Справка по командам:**\n\n"
        "/start - Начать общение с ботом\n"
        "/newchat - Начать новый диалог\n"
        "/models - Выбрать AI модель\n"
        "/prompt - Настроить системный промпт\n"
        "/resetprompt - Сбросить системный промпт\n"
        "/temp - Настроить креативность (temperature)\n"
        "/settings - Показать текущие настройки\n"
        "/premium - Активировать премиум-режим\n"
        "/upload - Загрузить файл для анализа\n"
        "/stream - Включить/выключить потоковый режим ответов\n"
        "/help - Показать эту справку\n\n"
        "📝 **Форматирование:**\n"
        "Бот поддерживает Markdown для кода и текста:\n"
        "```\n# Заголовок\n**жирный текст**\n*курсив*\n`код`\n```\n"
        "📊 **Отправка изображений:**\n"
        "Вы можете отправить изображение с подписью, и я проанализирую его содержимое."
        "\n\n🧠 **Контекстная память:**\n"
        "Бот помнит историю вашего диалога и использует её для более точных ответов."
        "\n\n🔄 **Обратная связь:**\n"
        "После каждого ответа вы можете оценить его качество, что помогает улучшать работу бота."
        "\n\n📄 **Работа с файлами:**\n"
        "Отправьте документ или используйте команду /upload, чтобы загрузить файл для анализа."
        "\n\n⚡ **Потоковый режим:**\n"
        "В потоковом режиме ответы появляются постепенно, что создает эффект печати в реальном времени."
    )

    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

@router.message(Command("settings"))
@safe_execution
async def cmd_settings(message: Message):
    """Показывает текущие настройки пользователя."""
    user_id = message.from_user.id

    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "model": ALL_MODELS[0],
            "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
            "temperature": CONFIG["TEMPERATURE"],
            "requests_left": CONFIG["MAX_DAILY_REQUESTS"],
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today()),
            "is_premium": False,
            "premium_until": None,
            "language": "ru",
            "notifications_enabled": True,
            "auto_translate": False,
            "interface_mode": "standard",
            "stream_mode": CONFIG["STREAM_RESPONSES"]
        }
        await save_user_settings()

    settings = user_settings[str(user_id)]
    model = settings.get("model", ALL_MODELS[0])
    system_prompt = settings.get("system_prompt", CONFIG["DEFAULT_SYSTEM_PROMPT"])
    temperature = settings.get("temperature", CONFIG["TEMPERATURE"])
    stream_mode = settings.get("stream_mode", CONFIG["STREAM_RESPONSES"])
    
    # Проверяем премиум-статус
    premium_status = "✅ Активен"
    if settings.get("is_premium", False):
        premium_until = settings.get("premium_until")
        if premium_until:
            try:
                expiry_date = datetime.fromisoformat(premium_until)
                if expiry_date > datetime.now():
                    days_left = (expiry_date - datetime.now()).days
                    premium_status = f"✅ Активен (еще {days_left} дн.)"
                else:
                    premium_status = "❌ Неактивен (истек)"
                    settings["is_premium"] = False
                    await save_user_settings()
            except ValueError:
                premium_status = "❌ Неактивен"
        else:
            premium_status = "✅ Активен (бессрочно)"
    else:
        premium_status = "❌ Неактивен"
    
    # Для обычных пользователей показываем счетчик запросов
    requests_info = ""
    if not is_premium_user(user_id):
        requests_left = settings.get("requests_left", 0)
        requests_info = f"\n\n🔢 **Осталось запросов сегодня:** `{requests_left}`"

    # Создаем клавиатуру для настроек
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🔄 Сменить модель", callback_data="change_model"))
    keyboard.row(InlineKeyboardButton(text="📝 Изменить системный промпт", callback_data="change_prompt"))
    keyboard.row(InlineKeyboardButton(text="🎛️ Настроить креативность", callback_data="change_temp"))
    keyboard.row(InlineKeyboardButton(text="⚡ Настройка потокового режима", callback_data="stream_settings"))
    keyboard.row(InlineKeyboardButton(text="🔄 Начать новый диалог", callback_data="new_chat"))
    
    if not is_premium_user(user_id):
        keyboard.row(InlineKeyboardButton(text="⭐ Активировать премиум", callback_data="activate_premium"))

    settings_text = (
        "⚙️ **Текущие настройки:**\n\n"
        f"🤖 **Модель:** `{format_model_name(model)}`\n\n"
        f"🌡️ **Креативность:** `{temperature}`\n\n"
        f"⚡ **Потоковый режим:** {'✅ Включен' if stream_mode else '❌ Выключен'}\n\n"
        f"⭐ **Премиум-статус:** {premium_status}\n\n"
        f"📝 **Системный промпт:**\n```\n{system_prompt}\n```" + requests_info
    )

    await message.answer(settings_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard.as_markup())

@router.message(Command("models"))
@safe_execution
async def cmd_models(message: Message, state: FSMContext):
    """Показывает список доступных моделей."""
    await state.set_state(UserStates.waiting_for_model_selection)

    await message.answer(
        "📚 Выберите категорию моделей:",
        reply_markup=await create_model_selection_keyboard()
    )

@router.message(Command("prompt"))
@safe_execution
async def cmd_prompt(message: Message, state: FSMContext):
    """Позволяет пользователю задать свой системный промпт."""
    await state.set_state(UserStates.custom_system_prompt)

    current_prompt = get_system_prompt(message.from_user.id)

    await message.answer(
        f"📝 Текущий системный промпт:\n```\n{current_prompt}\n```\n\n"
        "Отправьте новый системный промпт, который будет использоваться в диалоге. "
        "Это инструкции для AI о том, как ему следует отвечать.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("resetprompt"))
@safe_execution
async def cmd_reset_prompt(message: Message):
    """Сбрасывает системный промпт на значение по умолчанию."""
    user_id = message.from_user.id

    if str(user_id) in user_settings:
        user_settings[str(user_id)]["system_prompt"] = CONFIG["DEFAULT_SYSTEM_PROMPT"]
        await save_user_settings()

    # Обновляем контекст пользователя, если он существует
    if user_id in user_contexts:
        # Ищем и обновляем системное сообщение
        for i, msg in enumerate(user_contexts[user_id]):
            if msg.get("role") == "system":
                user_contexts[user_id][i]["content"] = CONFIG["DEFAULT_SYSTEM_PROMPT"]
                break
        # Если системного сообщения нет, добавляем его
        else:
            user_contexts[user_id].insert(0, {
                "role": "system", 
                "content": CONFIG["DEFAULT_SYSTEM_PROMPT"],
                "importance": 1.0,
                "timestamp": datetime.now().isoformat()
            })
        
        # Сохраняем обновленный контекст
        await save_user_contexts()

    await message.answer(
        "✅ Системный промпт сброшен на значение по умолчанию.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("temp"))
@safe_execution
async def cmd_temperature(message: Message, state: FSMContext):
    """Позволяет пользователю настроить параметр temperature."""
    await state.set_state(UserStates.waiting_for_temperature)

    current_temp = get_user_temperature(message.from_user.id)

    await message.answer(
        f"🌡️ Текущее значение креативности (temperature): **{current_temp}**\n\n"
        "Более низкие значения делают ответы более предсказуемыми и точными, "
        "более высокие значения делают ответы более творческими и разнообразными.\n\n"
        "Выберите желаемый уровень креативности:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await create_temperature_keyboard()
    )

@router.message(Command("stream"))
@safe_execution
async def cmd_stream(message: Message):
    """Позволяет включить или выключить потоковый режим ответов."""
    user_id = message.from_user.id
    
    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "model": ALL_MODELS[0],
            "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
            "temperature": CONFIG["TEMPERATURE"],
            "requests_left": CONFIG["MAX_DAILY_REQUESTS"],
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today()),
            "is_premium": False,
            "premium_until": None,
            "language": "ru",
            "notifications_enabled": True,
            "auto_translate": False,
            "interface_mode": "standard",
            "stream_mode": CONFIG["STREAM_RESPONSES"]
        }
    
    current_mode = user_settings[str(user_id)].get("stream_mode", CONFIG["STREAM_RESPONSES"])
    
    await message.answer(
        "⚡ **Настройка потокового режима ответов**\n\n"
        "В потоковом режиме ответы появляются постепенно, что создает эффект печати в реальном времени.\n\n"
        "Эта функция особенно полезна для длинных ответов, чтобы видеть прогресс без ожидания завершения.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await create_stream_mode_keyboard(current_mode)
    )

@router.message(Command("newchat"))
@safe_execution
async def cmd_new_chat(message: Message):
    """Начинает новый диалог, очищая историю контекста."""
    user_id = message.from_user.id
    clear_user_context(user_id)

    # Добавляем системный промпт в начало нового диалога
    system_prompt = get_system_prompt(user_id)
    add_to_user_context(user_id, "system", system_prompt)

    await message.answer(
        "🔄 Начат новый диалог. Вся предыдущая история очищена.\n"
        "Задайте мне вопрос или опишите, с чем я могу вам помочь."
    )

@router.message(Command("premium"))
@safe_execution
async def cmd_premium(message: Message, state: FSMContext):
    """Позволяет активировать премиум-режим с помощью кода."""
    user_id = message.from_user.id
    
    # Проверяем, является ли пользователь уже премиум-пользователем
    if is_premium_user(user_id):
        # Определяем срок действия премиума
        premium_until = user_settings.get(str(user_id), {}).get("premium_until")
        if premium_until:
            try:
                expiry_date = datetime.fromisoformat(premium_until)
                days_left = (expiry_date - datetime.now()).days
                await message.answer(
                    f"⭐ У вас уже активирован премиум-режим!\n\n"
                    f"Срок действия: еще {days_left} дней.\n\n"
                    f"Премиум дает вам неограниченное количество запросов и доступ ко всем функциям бота."
                )
            except ValueError:
                await message.answer(
                    "⭐ У вас уже активирован премиум-режим!\n\n"
                    "Премиум дает вам неограниченное количество запросов и доступ ко всем функциям бота."
                )
        else:
            await message.answer(
                "⭐ У вас уже активирован бессрочный премиум-режим!\n\n"
                "Премиум дает вам неограниченное количество запросов и доступ ко всем функциям бота."
            )
        return
    
    # Переходим в состояние ожидания кода
    await state.set_state(UserStates.waiting_for_premium_code)
    
    await message.answer(
        "⭐ Для активации премиум-режима введите код активации.\n\n"
        "Премиум-режим дает вам:\n"
        "• Неограниченное количество запросов\n"
        "• Приоритетный доступ к наиболее мощным моделям\n"
        "• Доступ ко всем функциям бота без ограничений\n\n"
        "Для отмены введите 'отмена'."
    )

@router.message(Command("upload"))
@safe_execution
async def cmd_upload(message: Message):
    """Инструктирует пользователя, как загрузить файл для анализа."""
    await message.answer(
        "📄 Для анализа файла вы можете:\n\n"
        "1) Прикрепить файл напрямую к сообщению\n"
        "2) Загрузить документ через кнопку скрепки 📎\n\n"
        "Поддерживаемые форматы: TXT, MD, CSV, JSON, HTML, XML, PY, JS, CSS и другие текстовые файлы.\n\n"
        "После загрузки вы сможете выбрать тип анализа файла."
    )

@router.message(Command("spamfilter"))
@admin_only
@safe_execution
async def cmd_spam_filter(message: Message):
    """Управление спам-фильтром (только для администраторов)."""
    await message.answer(
        "🚫 **Управление защитой от спама**\n\n"
        "С помощью этого меню вы можете настраивать фильтрацию спама и рекламы в сообщениях пользователей.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await create_admin_spam_keyboard()
    )

@router.callback_query(lambda c: c.data == "new_chat")
@safe_execution
async def callback_new_chat(callback: CallbackQuery):
    """Обработчик кнопки "Новый диалог"."""
    user_id = callback.from_user.id
    clear_user_context(user_id)

    # Добавляем системный промпт в начало нового диалога
    system_prompt = get_system_prompt(user_id)
    add_to_user_context(user_id, "system", system_prompt)

    await callback.message.answer(
        "🔄 Начат новый диалог. Вся предыдущая история очищена.\n"
        "Задайте мне вопрос или опишите, с чем я могу вам помочь."
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "change_model")
@safe_execution
async def callback_change_model(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки смены модели."""
    await state.set_state(UserStates.waiting_for_model_selection)

    await callback.message.answer(
        "📚 Выберите категорию моделей:",
        reply_markup=await create_model_selection_keyboard()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "change_prompt")
@safe_execution
async def callback_change_prompt(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки изменения системного промпта."""
    await state.set_state(UserStates.custom_system_prompt)

    current_prompt = get_system_prompt(callback.from_user.id)

    await callback.message.answer(
        f"📝 Текущий системный промпт:\n```\n{current_prompt}\n```\n\n"
        "Отправьте новый системный промпт, который будет использоваться в диалоге. "
        "Это инструкции для AI о том, как ему следует отвечать.",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "change_temp")
@safe_execution
async def callback_change_temp(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки изменения температуры."""
    await state.set_state(UserStates.waiting_for_temperature)

    current_temp = get_user_temperature(callback.from_user.id)

    await callback.message.answer(
        f"🌡️ Текущее значение креативности (temperature): **{current_temp}**\n\n"
        "Более низкие значения делают ответы более предсказуемыми и точными, "
        "более высокие значения делают ответы более творческими и разнообразными.\n\n"
        "Выберите желаемый уровень креативности:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await create_temperature_keyboard()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "stream_settings")
@safe_execution
async def callback_stream_settings(callback: CallbackQuery):
    """Обработчик кнопки настройки потокового режима."""
    user_id = callback.from_user.id
    
    current_mode = user_settings.get(str(user_id), {}).get("stream_mode", CONFIG["STREAM_RESPONSES"])
    
    await callback.message.answer(
        "⚡ **Настройка потокового режима ответов**\n\n"
        "В потоковом режиме ответы появляются постепенно, что создает эффект печати в реальном времени.\n\n"
        "Эта функция особенно полезна для длинных ответов, чтобы видеть прогресс без ожидания завершения.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await create_stream_mode_keyboard(current_mode)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_settings")
@safe_execution
async def callback_back_to_settings(callback: CallbackQuery):
    """Обработчик кнопки возврата к настройкам."""
    await cmd_settings(callback.message)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("toggle_stream:"))
@safe_execution
async def callback_toggle_stream(callback: CallbackQuery):
    """Обработчик переключения потокового режима."""
    user_id = callback.from_user.id
    new_mode = callback.data.split(":", 1)[1] == "True"
    
    # Обновляем настройки пользователя
    if str(user_id) in user_settings:
        user_settings[str(user_id)]["stream_mode"] = new_mode
        await save_user_settings()
    
    # Отправляем подтверждение
    await callback.message.edit_text(
        "⚡ **Настройка потокового режима ответов**\n\n"
        f"Потоковый режим {'включен' if new_mode else 'выключен'}.\n\n"
        "В потоковом режиме ответы появляются постепенно, что создает эффект печати в реальном времени.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await create_stream_mode_keyboard(new_mode)
    )
    await callback.answer(f"Потоковый режим {'включен' if new_mode else 'выключен'}")

@router.callback_query(lambda c: c.data == "stream_info")
@safe_execution
async def callback_stream_info(callback: CallbackQuery):
    """Обработчик запроса информации о потоковом режиме."""
    await callback.answer(
        "В потоковом режиме текст ответа появляется постепенно, как будто его печатает человек. "
        "Это полезно для длинных ответов, чтобы вы могли начать читать, не дожидаясь полного завершения.", 
        show_alert=True
    )

@router.callback_query(lambda c: c.data == "spam_status")
@admin_only
@safe_execution
async def callback_spam_status(callback: CallbackQuery):
    """Обработчик запроса статуса спам-фильтра."""
    await callback.answer(
        f"Защита от спама {'включена' if CONFIG['ENABLE_SPAM_PROTECTION'] else 'выключена'}. "
        f"Заблокировано попыток спама: {bot_metrics.spam_blocked}. "
        f"В черном списке: {len(blocked_users)} пользователей.",
        show_alert=True
    )

@router.callback_query(lambda c: c.data.startswith("toggle_spam:"))
@admin_only
@safe_execution
async def callback_toggle_spam(callback: CallbackQuery):
    """Обработчик переключения спам-фильтра."""
    new_state = callback.data.split(":", 1)[1] == "True"
    
    # Обновляем настройки
    CONFIG["ENABLE_SPAM_PROTECTION"] = new_state
    
    # Отправляем подтверждение
    await callback.message.edit_text(
        "🚫 **Управление защитой от спама**\n\n"
        f"Защита от спама {'включена' if new_state else 'выключена'}.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await create_admin_spam_keyboard()
    )
    await callback.answer(f"Защита от спама {'включена' if new_state else 'выключена'}")

@router.callback_query(lambda c: c.data == "add_spam_pattern")
@admin_only
@safe_execution
async def callback_add_spam_pattern(callback: CallbackQuery, state: FSMContext):
    """Обработчик добавления нового спам-паттерна."""
    await state.set_state(UserStates.waiting_for_spam_pattern)
    
    await callback.message.answer(
        "🔍 **Добавление спам-паттерна**\n\n"
        "Введите регулярное выражение для нового спам-паттерна.\n"
        "Пример: `(?i)заработ[а-я]+ деньги`\n\n"
        "Для отмены введите 'отмена'.",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "view_spam_patterns")
@admin_only
@safe_execution
async def callback_view_spam_patterns(callback: CallbackQuery):
    """Обработчик просмотра спам-паттернов."""
    patterns_text = "🔍 **Текущие спам-паттерны:**\n\n"
    
    for i, pattern in enumerate(SPAM_PATTERNS, 1):
        patterns_text += f"{i}. `{pattern}`\n"
    
    # Если список слишком длинный, разбиваем на части
    if len(patterns_text) > 4000:
        parts = [patterns_text[i:i+4000] for i in range(0, len(patterns_text), 4000)]
        for part in parts:
            await callback.message.answer(part, parse_mode=ParseMode.MARKDOWN)
    else:
        await callback.message.answer(patterns_text, parse_mode=ParseMode.MARKDOWN)
    
    await callback.answer()

@router.callback_query(lambda c: c.data == "view_blocked_users")
@admin_only
@safe_execution
async def callback_view_blocked_users(callback: CallbackQuery):
    """Обработчик просмотра заблокированных пользователей."""
    if not blocked_users:
        await callback.message.answer("👥 Список заблокированных пользователей пуст.")
        await callback.answer()
        return
    
    users_text = "👥 **Заблокированные пользователи:**\n\n"
    for i, user_id in enumerate(blocked_users, 1):
        users_text += f"{i}. `{user_id}`\n"
    
    await callback.message.answer(users_text, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()

@router.callback_query(lambda c: c.data == "clear_blocked_users")
@admin_only
@safe_execution
async def callback_clear_blocked_users(callback: CallbackQuery):
    """Обработчик очистки списка заблокированных пользователей."""
    global blocked_users
    blocked_users.clear()
    await save_blocked_users()
    
    await callback.message.answer("🧹 Список заблокированных пользователей очищен.")
    await callback.answer()

@router.callback_query(lambda c: c.data == "activate_premium")
@safe_execution
async def callback_activate_premium(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки активации премиума."""
    user_id = callback.from_user.id
    
    # Проверяем, является ли пользователь уже премиум-пользователем
    if is_premium_user(user_id):
        await callback.answer("У вас уже активирован премиум-режим!")
        return
    
    # Переходим в состояние ожидания кода
    await state.set_state(UserStates.waiting_for_premium_code)
    
    await callback.message.answer(
        "⭐ Для активации премиум-режима введите код активации.\n\n"
        "Премиум-режим дает вам:\n"
        "• Неограниченное количество запросов\n"
        "• Приоритетный доступ к наиболее мощным моделям\n"
        "• Доступ ко всем функциям бота без ограничений\n\n"
        "Для отмены введите 'отмена'."
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("category:"))
@safe_execution
async def callback_select_category(callback: CallbackQuery):
    """Обработчик выбора категории моделей."""
    category = callback.data.split(":", 1)[1]

    await callback.message.edit_text(
        f"📚 Выберите модель из категории «{category}»:",
        reply_markup=await create_category_models_keyboard(category)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_categories")
@safe_execution
async def callback_back_to_categories(callback: CallbackQuery):
    """Обработчик кнопки "Назад к категориям"."""
    await callback.message.edit_text(
        "📚 Выберите категорию моделей:",
        reply_markup=await create_model_selection_keyboard()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "favorite_models")
@safe_execution
async def callback_favorite_models(callback: CallbackQuery):
    """Обработчик кнопки "Избранные модели"."""
    user_id = callback.from_user.id
    
    # Проверяем, есть ли у пользователя избранные модели
    favorite_models = user_settings.get(str(user_id), {}).get("favorite_models", [])
    
    if not favorite_models:
        await callback.answer("У вас пока нет избранных моделей. Выберите модель для добавления в избранное.")
        # Возвращаемся к категориям
        await callback.message.edit_text(
            "📚 Выберите категорию моделей:",
            reply_markup=await create_model_selection_keyboard()
        )
        return
    
    await callback.message.edit_text(
        "⭐ Выберите одну из ваших избранных моделей:",
        reply_markup=await create_favorite_models_keyboard(user_id)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "enter_model_manually")
@safe_execution
async def callback_enter_model_manually(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки ввода названия модели вручную."""
    await state.set_state(UserStates.waiting_for_direct_model)
    
    await callback.message.edit_text(
        "🔍 Введите название модели в формате `provider/model-name`.\n\n"
        "Например: `meta-llama/Llama-3.3-70B-Instruct` или `Qwen/QwQ-32B`\n\n"
        "Для отмены напишите 'отмена'."
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("file_process:"))
@safe_execution
async def callback_file_processing(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора типа обработки файла."""
    user_id = callback.from_user.id
    process_type = callback.data.split(":", 1)[1]
    
    # Если пользователь отменил выбор
    if process_type == "cancel":
        await state.clear()
        await callback.message.edit_text("⚠️ Обработка файла отменена.")
        await callback.answer()
        return
    
    # Получаем данные о файле из состояния
    data = await state.get_data()
    file_id = data.get("file_id")
    file_name = data.get("file_name")
    
    if not file_id or not file_name:
        await callback.message.edit_text("⚠️ Информация о файле утеряна. Пожалуйста, загрузите файл заново.")
        await state.clear()
        await callback.answer()
        return
    
    # Удаляем кнопки с типами обработки
    await callback.message.edit_text(
        f"⏳ Начинаю обработку файла '{file_name}'...\n\n"
        f"Тип обработки: {process_type.replace('_', ' ').title()}\n\n"
        f"Пожалуйста, подождите, это может занять некоторое время."
    )
    
    # Отправляем сообщение "AI думает..."
    await send_thinking_animation(callback.message.chat.id)
    
    # Обрабатываем файл
    result = await process_file(user_id, file_id, file_name, process_type)
    
    # Удаляем сообщение "AI думает..."
    await remove_thinking_animation(callback.message.chat.id)
    
    # Определяем, нужно ли использовать потоковый режим для ответа
    use_stream = get_user_stream_mode(user_id) and len(result) > 500
    
    # Отправляем результат обработки
    if use_stream:
        await stream_and_send_response(callback.message, result)
    else:
        await split_and_send_message(callback.message, result)
    
    # Очищаем состояние
    await state.clear()
    await callback.answer()

@router.message(StateFilter(UserStates.waiting_for_spam_pattern))
@admin_only
@safe_execution
async def process_spam_pattern(message: Message, state: FSMContext):
    """Обрабатывает ввод нового спам-паттерна."""
    pattern = message.text.strip()
    
    # Проверка на отмену
    if pattern.lower() in ['отмена', 'cancel', 'отмен', 'стоп', 'stop']:
        await state.clear()
        await message.answer("❌ Добавление спам-паттерна отменено.")
        return
    
    try:
        # Проверяем валидность регулярного выражения
        re.compile(pattern)
        
        # Добавляем паттерн в список
        SPAM_PATTERNS.append(pattern)
        
        # Сохраняем обновленные паттерны
        await save_spam_patterns()
        
        await message.answer(
            f"✅ Спам-паттерн успешно добавлен:\n\n`{pattern}`",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Возвращаемся к нормальному состоянию
        await state.clear()
    except re.error as e:
        # Если регулярное выражение некорректно
        await message.answer(
            f"❌ Некорректное регулярное выражение: {str(e)}\n\n"
            "Пожалуйста, проверьте синтаксис и попробуйте снова, или напишите 'отмена' для выхода."
        )

@router.message(StateFilter(UserStates.waiting_for_direct_model))
@safe_execution
async def process_direct_model(message: Message, state: FSMContext):
    """Обрабатывает ввод названия модели вручную."""
    model_name = message.text.strip()
    
    # Проверка на отмену
    if model_name.lower() in ['отмена', 'cancel', 'отмен', 'стоп', 'stop']:
        await state.clear()
        await message.answer("❌ Выбор модели отменен. Оставлена текущая модель.")
        return
    
    # Проверяем формат модели
    if '/' not in model_name:
        await message.answer(
            "❌ Неверный формат названия модели. Необходимо указать в формате `provider/model-name`.\n"
            "Пример: meta-llama/Llama-3.3-70B-Instruct\n\n"
            "Попробуйте еще раз или напишите 'отмена' для отмены."
        )
        return
    
    # Сохраняем выбранную модель
    user_id = message.from_user.id
    
    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
            "temperature": CONFIG["TEMPERATURE"],
            "requests_left": CONFIG["MAX_DAILY_REQUESTS"],
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today()),
            "is_premium": False,
            "premium_until": None,
            "language": "ru",
            "notifications_enabled": True,
            "auto_translate": False,
            "interface_mode": "standard",
            "stream_mode": CONFIG["STREAM_RESPONSES"]
        }
    
    # Сохраняем предыдущую модель
    previous_model = user_settings[str(user_id)].get("model", ALL_MODELS[0])
    
    # Устанавливаем новую модель
    user_settings[str(user_id)]["model"] = model_name
    
    # Добавляем модель в избранное, если её там еще нет
    favorite_models = user_settings[str(user_id)].get("favorite_models", [])
    if model_name not in favorite_models:
        favorite_models.append(model_name)
        # Ограничиваем количество избранных моделей
        if len(favorite_models) > 5:
            favorite_models.pop(0)
        user_settings[str(user_id)]["favorite_models"] = favorite_models
    
    await save_user_settings()
    
    # Возвращаемся к нормальному состоянию
    await state.clear()
    
    await message.answer(
        f"✅ Модель успешно изменена на: **{model_name}**\n\n"
        f"⚠️ Обратите внимание, что если указанная модель не существует или недоступна, "
        f"бот автоматически вернется к одной из доступных моделей при следующем запросе.\n\n"
        f"Модель также добавлена в ваш список избранных для быстрого доступа в будущем.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(StateFilter(UserStates.waiting_for_premium_code))
@safe_execution
async def process_premium_code(message: Message, state: FSMContext):
    """Обрабатывает ввод промо-кода для активации премиума."""
    code = message.text.strip()
    user_id = message.from_user.id
    
    # Проверка на отмену
    if code.lower() in ['отмена', 'cancel', 'отмен', 'стоп', 'stop']:
        await state.clear()
        await message.answer("❌ Активация премиум-режима отменена.")
        return
    
    # Загружаем премиум-коды, если еще не загружены
    if not premium_codes:
        await load_premium_codes()
    
    # Проверяем валидность кода
    if code in premium_codes:
        # Активируем премиум для пользователя (на 30 дней)
        if await activate_premium(user_id, 30):
            # Удаляем использованный код
            premium_codes.remove(code)
            await save_premium_codes()
            
            await message.answer(
                "🎉 Поздравляем! Премиум-режим успешно активирован на 30 дней!\n\n"
                "Теперь вы имеете доступ ко всем функциям бота без ограничений и неограниченное количество запросов."
            )
        else:
            await message.answer(
                "❌ Произошла ошибка при активации премиум-режима. Пожалуйста, попробуйте позже или обратитесь к администратору."
            )
    else:
        await message.answer(
            "❌ Неверный код активации. Пожалуйста, проверьте код и попробуйте снова, или напишите 'отмена' для выхода."
        )
        # Не очищаем состояние, чтобы пользователь мог попробовать еще раз
        return
    
    # Возвращаемся к нормальному состоянию
    await state.clear()

@router.callback_query(lambda c: c.data.startswith("model:"))
@safe_execution
async def callback_select_model(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора модели."""
    user_id = callback.from_user.id
    model = callback.data.split(":", 1)[1]

    # Сохраняем выбранную модель в настройках пользователя
    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
            "temperature": CONFIG["TEMPERATURE"],
            "requests_left": CONFIG["MAX_DAILY_REQUESTS"],
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today()),
            "is_premium": False,
            "premium_until": None,
            "language": "ru",
            "notifications_enabled": True,
            "auto_translate": False,
            "interface_mode": "standard",
            "stream_mode": CONFIG["STREAM_RESPONSES"]
        }

    user_settings[str(user_id)]["model"] = model
    
    # Добавляем модель в избранное, если её там еще нет
    favorite_models = user_settings[str(user_id)].get("favorite_models", [])
    if model not in favorite_models:
        favorite_models.append(model)
        # Ограничиваем количество избранных моделей
        if len(favorite_models) > 5:
            favorite_models.pop(0)
        user_settings[str(user_id)]["favorite_models"] = favorite_models
    
    await save_user_settings()

    # Возвращаемся к нормальному состоянию
    await state.clear()

    await callback.message.edit_text(
        f"✅ Модель успешно изменена на: **{format_model_name(model)}**\n\n"
        "Модель также добавлена в ваши избранные для быстрого доступа в будущем.\n\n"
        "Теперь вы можете задать мне любой вопрос!",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer("Модель установлена!")

@router.callback_query(lambda c: c.data.startswith("temp:"))
@safe_execution
async def callback_select_temperature(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора значения temperature."""
    user_id = callback.from_user.id
    temperature = float(callback.data.split(":", 1)[1])

    # Сохраняем выбранное значение temperature
    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "model": ALL_MODELS[0],
            "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
            "requests_left": CONFIG["MAX_DAILY_REQUESTS"],
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today()),
            "is_premium": False,
            "premium_until": None,
            "language": "ru",
            "notifications_enabled": True,
            "auto_translate": False,
            "interface_mode": "standard",
            "stream_mode": CONFIG["STREAM_RESPONSES"]
        }

    user_settings[str(user_id)]["temperature"] = temperature
    await save_user_settings()

    # Возвращаемся к нормальному состоянию
    await state.clear()

    await callback.message.edit_text(
        f"✅ Значение креативности успешно изменено на: **{temperature}**\n\n"
        "Теперь вы можете продолжить диалог!",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer("Настройка сохранена!")

@router.callback_query(lambda c: c.data.startswith("feedback:"))
@safe_execution
async def callback_feedback(callback: CallbackQuery):
    """Обработчик отзыва о качестве ответа."""
    parts = callback.data.split(":")
    feedback_type = parts[1]
    message_id = parts[2] if len(parts) > 2 else None
    
    user_id = callback.from_user.id
    
    if feedback_type == "good":
        # Положительный отзыв
        feedback_value = 1
        await callback.answer("Спасибо за положительный отзыв!")
    else:
        # Отрицательный отзыв
        feedback_value = -1
        await callback.answer("Спасибо за отзыв! Я постараюсь улучшить свои ответы.")
    
    # Сохраняем отзыв
    if user_id not in user_feedback:
        user_feedback[user_id] = {}
    
    user_feedback[user_id][message_id] = feedback_value
    
    # Обновляем важность сообщений в контексте
    update_context_importance(user_id, feedback_value)
    
    # Удаляем кнопки отзыва
    try:
        await callback.message.edit_reply_markup()
    except Exception as e:
        logger.warning(f"Не удалось удалить кнопки отзыва: {e}")

@router.callback_query(lambda c: c.data.startswith("rephrase:"))
@safe_execution
async def callback_rephrase(callback: CallbackQuery):
    """Обработчик запроса на перефразирование ответа."""
    message_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    await callback.answer("Перефразирую ответ...")
    
    # Находим оригинальный ответ
    original_text = callback.message.text
    
    # Показываем, что бот "печатает"
    await bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
    
    # Показываем сообщение "AI думает..."
    thinking_msg_id = await send_thinking_animation(callback.message.chat.id)
    
    # Получаем перефразированный ответ
    new_answer = await rephrase_answer(
        user_id,
        original_text,
        "Перефразируй этот ответ другими словами, сохраняя то же содержание, но выражая его иначе"
    )
    
    # Удаляем сообщение "AI думает..."
    if thinking_msg_id:
        await remove_thinking_animation(callback.message.chat.id)
    
    # Определяем, нужно ли использовать потоковый режим для ответа
    use_stream = get_user_stream_mode(user_id) and len(new_answer) > 500
    
    # Отправляем новый ответ с кнопками обратной связи
    if use_stream:
        sent_message = await stream_and_send_response(callback.message, new_answer)
    else:
        sent_message = await split_and_send_message(callback.message, new_answer)
    
    # Добавляем кнопки обратной связи к последнему сообщению
    if sent_message:
        feedback_id = str(uuid.uuid4())
        try:
            await sent_message.edit_reply_markup(reply_markup=await create_feedback_keyboard(feedback_id))
        except Exception as e:
            logger.warning(f"Не удалось добавить кнопки обратной связи: {e}")
    
    # Удаляем кнопки у старого сообщения
    try:
        await callback.message.edit_reply_markup()
    except Exception as e:
        logger.warning(f"Не удалось удалить кнопки: {e}")

@router.callback_query(lambda c: c.data.startswith("elaborate:"))
@safe_execution
async def callback_elaborate(callback: CallbackQuery):
    """Обработчик запроса на более подробный ответ."""
    message_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    await callback.answer("Подготавливаю более подробный ответ...")
    
    # Находим оригинальный ответ
    original_text = callback.message.text
    
    # Показываем, что бот "печатает"
    await bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
    
    # Показываем сообщение "AI думает..."
    thinking_msg_id = await send_thinking_animation(callback.message.chat.id)
    
    # Получаем более подробный ответ
    new_answer = await rephrase_answer(
        user_id,
        original_text,
        "Расширь этот ответ, добавив больше подробностей, примеров и объяснений. Сделай ответ более полным и информативным."
    )
    
    # Удаляем сообщение "AI думает..."
    if thinking_msg_id:
        await remove_thinking_animation(callback.message.chat.id)
    
    # Определяем, нужно ли использовать потоковый режим для ответа
    use_stream = get_user_stream_mode(user_id) and len(new_answer) > 500
    
    # Отправляем новый ответ с кнопками обратной связи
    if use_stream:
        sent_message = await stream_and_send_response(callback.message, new_answer)
    else:
        sent_message = await split_and_send_message(callback.message, new_answer)
    
    # Добавляем кнопки обратной связи к последнему сообщению
    if sent_message:
        feedback_id = str(uuid.uuid4())
        try:
            await sent_message.edit_reply_markup(reply_markup=await create_feedback_keyboard(feedback_id))
        except Exception as e:
            logger.warning(f"Не удалось добавить кнопки обратной связи: {e}")
    
    # Удаляем кнопки у старого сообщения
    try:
        await callback.message.edit_reply_markup()
    except Exception as e:
        logger.warning(f"Не удалось удалить кнопки: {e}")

@router.message(StateFilter(UserStates.custom_system_prompt))
@safe_execution
async def process_custom_prompt(message: Message, state: FSMContext):
    """Обрабатывает ввод пользовательского системного промпта."""
    user_id = message.from_user.id
    new_prompt = message.text

    # Проверяем, что промпт не пустой
    if not new_prompt or len(new_prompt) < 5:
        await message.answer(
            "❌ Промпт слишком короткий. Пожалуйста, введите более подробный системный промпт."
        )
        return

    # Сохраняем промпт в настройках
    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "model": ALL_MODELS[0],
            "temperature": CONFIG["TEMPERATURE"],
            "requests_left": CONFIG["MAX_DAILY_REQUESTS"],
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today()),
            "is_premium": False,
            "premium_until": None,
            "language": "ru",
            "notifications_enabled": True,
            "auto_translate": False,
            "interface_mode": "standard",
            "stream_mode": CONFIG["STREAM_RESPONSES"]
        }

    user_settings[str(user_id)]["system_prompt"] = new_prompt
    await save_user_settings()

    # Обновляем контекст пользователя
    if user_id in user_contexts:
        # Ищем и обновляем системное сообщение
        for i, msg in enumerate(user_contexts[user_id]):
            if msg.get("role") == "system":
                user_contexts[user_id][i]["content"] = new_prompt
                break
        # Если системного сообщения нет, добавляем его
        else:
            user_contexts[user_id].insert(0, {
                "role": "system", 
                "content": new_prompt,
                "importance": 1.0,
                "timestamp": datetime.now().isoformat()
            })
    else:
        # Создаем новый контекст с системным промптом
        user_contexts[user_id] = [{
            "role": "system", 
            "content": new_prompt,
            "importance": 1.0,
            "timestamp": datetime.now().isoformat()
        }]
    
    # Сохраняем обновленный контекст
    await save_user_contexts()

    # Возвращаемся к нормальному состоянию
    await state.clear()

    await message.answer(
        "✅ Системный промпт успешно изменен!\n\n"
        "Теперь вы можете продолжить диалог с учетом новых инструкций."
    )

@router.message(StateFilter(UserStates.waiting_for_image_caption))
@safe_execution
async def process_image_caption(message: Message, state: FSMContext):
    """Обрабатывает подпись к изображению."""
    # Получаем файл из состояния
    data = await state.get_data()
    image_data = data.get("image_data")
    
    if not image_data:
        await message.answer("⚠️ Изображение не найдено. Пожалуйста, отправьте изображение заново.")
        await state.clear()
        return
    
    # Получаем подпись от пользователя
    caption = message.text
    
    # Если пользователь отменил
    if caption.lower() in ['отмена', 'cancel', 'стоп', 'stop']:
        await message.answer("❌ Обработка изображения отменена.")
        await state.clear()
        return
    
    # Добавляем сообщение пользователя (обрабатываем как обычное сообщение)
    user_id = message.from_user.id
    
    # Показываем, что бот "печатает"
    await bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
    
    # Показываем сообщение "AI думает..."
    thinking_msg_id = await send_thinking_animation(message.chat.id)
    
    # Получаем ответ от AI
    ai_response = await get_ai_response(user_id, caption, image_data)
    
    # Удаляем сообщение "AI думает..."
    if thinking_msg_id:
        await remove_thinking_animation(message.chat.id)
    
    # Отправляем ответ
    ai_response = clean_markdown(ai_response)
    
    # Определяем, нужно ли использовать потоковый режим для ответа
    use_stream = get_user_stream_mode(user_id) and len(ai_response) > 500
    
    if use_stream:
        sent_message = await stream_and_send_response(message, ai_response)
    else:
        sent_message = await message.answer(ai_response, parse_mode=ParseMode.MARKDOWN)
    
    # Добавляем кнопки обратной связи
    feedback_id = str(uuid.uuid4())
    try:
        await sent_message.edit_reply_markup(reply_markup=await create_feedback_keyboard(feedback_id))
    except Exception as e:
        logger.warning(f"Не удалось добавить кнопки обратной связи: {e}")
    
    # Очищаем состояние
    await state.clear()

@router.message(StateFilter(UserStates.waiting_for_admin_broadcast))
@admin_only
@safe_execution
async def process_broadcast_message(message: Message, state: FSMContext):
    """Обрабатывает сообщение для рассылки от администратора."""
    broadcast_text = message.text
    
    # Если пользователь отменил
    if broadcast_text.lower() in ['отмена', 'cancel', 'стоп', 'stop']:
        await message.answer("✅ Рассылка отменена.")
        await state.clear()
        return
    
    # Запрашиваем подтверждение
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="broadcast_confirm"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="broadcast_cancel")
    )
    
    # Сохраняем текст рассылки в состоянии
    await state.update_data(broadcast_text=broadcast_text)
    
    await message.answer(
        f"📢 Текст рассылки:\n\n{broadcast_text}\n\n"
        f"Подтвердите отправку всем пользователям бота.",
        reply_markup=keyboard.as_markup()
    )

@router.callback_query(lambda c: c.data == "broadcast_confirm")
@safe_execution
async def callback_broadcast_confirm(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения рассылки."""
    # Получаем текст рассылки из состояния
    data = await state.get_data()
    broadcast_text = data.get("broadcast_text")
    
    if not broadcast_text:
        await callback.message.edit_text("⚠️ Текст рассылки не найден. Пожалуйста, начните процесс заново.")
        await state.clear()
        await callback.answer()
        return
    
    # Удаляем кнопки подтверждения
    await callback.message.edit_text(
        f"📢 Начинаю рассылку сообщения:\n\n{broadcast_text}\n\n"
        f"Пожалуйста, дождитесь завершения."
    )
    
    # Получаем всех уникальных пользователей
    all_users = set()
    for user_id in user_settings:
        try:
            all_users.add(int(user_id))
        except (ValueError, TypeError):
            continue
    
    # Счетчики для статистики
    success_count = 0
    fail_count = 0
    
    # Отправляем сообщение всем пользователям
    for user_id in all_users:
        try:
            await bot.send_message(user_id, broadcast_text)
            success_count += 1
            
            # Делаем небольшую паузу между отправками, чтобы не превысить лимиты Telegram
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
            fail_count += 1
    
    # Отправляем отчет администратору
    await callback.message.answer(
        f"✅ Рассылка завершена!\n\n"
        f"📊 Статистика:\n"
        f"- Всего пользователей: {len(all_users)}\n"
        f"- Успешно доставлено: {success_count}\n"
        f"- Ошибок доставки: {fail_count}"
    )
    
    # Очищаем состояние
    await state.clear()
    await callback.answer()

@router.callback_query(lambda c: c.data == "broadcast_cancel")
@safe_execution
async def callback_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены рассылки."""
    await callback.message.edit_text("✅ Рассылка отменена.")
    await state.clear()
    await callback.answer()

@router.message(F.text == "🔄 Новый диалог")
@safe_execution
async def handle_new_chat_button(message: Message):
    """Обработчик кнопки "Новый диалог" на клавиатуре."""
    user_id = message.from_user.id
    clear_user_context(user_id)

    # Добавляем системный промпт в начало нового диалога
    system_prompt = get_system_prompt(user_id)
    add_to_user_context(user_id, "system", system_prompt)

    await message.answer(
        "🔄 Начат новый диалог. Вся предыдущая история очищена.\n"
        "Задайте мне вопрос или опишите, с чем я могу вам помочь."
    )

@router.message(F.text == "⚙️ Настройки")
@safe_execution
async def handle_settings_button(message: Message):
    """Обработчик кнопки "Настройки" на клавиатуре."""
    await cmd_settings(message)

@router.message(F.text == "🤖 Выбрать модель")
@safe_execution
async def handle_models_button(message: Message, state: FSMContext):
    """Обработчик кнопки "Выбрать модель" на клавиатуре."""
    await cmd_models(message, state)

@router.message(F.text == "📄 Загрузить файл")
@safe_execution
async def handle_upload_button(message: Message):
    """Обработчик кнопки "Загрузить файл" на клавиатуре."""
    await cmd_upload(message)

@router.message(F.document)
@safe_execution
@spam_filter
async def handle_document(message: Message, state: FSMContext):
    """Обрабатывает загрузку документа."""
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Обновляем дату последней активности пользователя
    if str(user_id) in user_settings:
        user_settings[str(user_id)]["last_active"] = str(date.today())
        await save_user_settings()
    
    # Проверяем лимиты для обычных пользователей
    if not (is_premium_user(user_id) or username == "qqq5599"):
        # Проверяем и обновляем количество запросов
        today = date.today().strftime("%Y-%m-%d")
        if str(user_id) in user_settings:
            if user_settings[str(user_id)].get("last_reset") != today:
                user_settings[str(user_id)]["requests_left"] = CONFIG["MAX_DAILY_REQUESTS"]
                user_settings[str(user_id)]["last_reset"] = today
                await save_user_settings()
            
            if user_settings[str(user_id)].get("requests_left", 0) <= 0:
                await message.answer("❌ Лимит запросов на сегодня исчерпан. Пожалуйста, попробуйте завтра или активируйте премиум-режим.")
                return
            
            user_settings[str(user_id)]["requests_left"] -= 1
            await save_user_settings()
    
    # Получаем информацию о файле
    file_id = message.document.file_id
    file_name = message.document.file_name or "document.txt"
    file_size = message.document.file_size
    
    # Проверяем размер файла
    if file_size > CONFIG["MAX_FILE_SIZE"]:
        await message.answer(
            f"❌ Файл слишком большой. Максимальный размер: {CONFIG['MAX_FILE_SIZE'] / (1024 * 1024):.1f} МБ."
        )
        return
    
    # Сохраняем информацию о файле в состоянии
    await state.set_state(UserStates.waiting_for_file_processing)
    await state.update_data(file_id=file_id, file_name=file_name)
    
    # Предлагаем типы обработки файла
    await message.answer(
        f"📄 Файл '{file_name}' получен!\n\n"
        f"Выберите тип обработки файла:",
        reply_markup=await create_file_processing_keyboard()
    )

@router.message(F.photo)
@safe_execution
@spam_filter
async def handle_photo(message: Message, state: FSMContext):
    """Обрабатывает сообщения с фотографиями."""
    user_id = message.from_user.id
    username = message.from_user.username

    # Обновляем дату последней активности пользователя
    if str(user_id) in user_settings:
        user_settings[str(user_id)]["last_active"] = str(date.today())
        await save_user_settings()

    # Проверяем лимиты для пользователей (кроме премиум и qqq5599)
    if not (is_premium_user(user_id) or username == "qqq5599"):
        if str(user_id) in user_settings:
            today = date.today().strftime("%Y-%m-%d")
            if user_settings[str(user_id)].get("last_reset") != today:
                user_settings[str(user_id)]["requests_left"] = CONFIG["MAX_DAILY_REQUESTS"]
                user_settings[str(user_id)]["last_reset"] = today
                await save_user_settings()
            
            if user_settings[str(user_id)].get("requests_left", 0) <= 0:
                await message.answer("❌ Лимит запросов на сегодня исчерпан. Пожалуйста, попробуйте завтра или активируйте премиум-режим.")
                return
            
            user_settings[str(user_id)]["requests_left"] -= 1
            await save_user_settings()

    # Получаем фото наилучшего качества
    photo = message.photo[-1]

    # Получаем подпись к фото или запрашиваем её
    caption = message.caption
    if not caption:
        # Получаем base64 изображения
        image_data = await process_image(photo)
        if not image_data:
            await message.answer(
                "❌ Не удалось обработать изображение. Убедитесь, что оно в формате JPG, JPEG, PNG или WEBP "
                "и его размер не превышает 10 МБ."
            )
            return
            
        # Сохраняем изображение в состоянии и запрашиваем подпись
        await state.set_state(UserStates.waiting_for_image_caption)
        await state.update_data(image_data=image_data)
        
        await message.answer(
            "🖼️ Изображение успешно загружено! Пожалуйста, опишите, что вы хотите узнать об этом изображении.\n\n"
            "Например:\n"
            "- Что изображено на этой фотографии?\n"
            "- Опиши детали этого изображения\n"
            "- Какие объекты присутствуют на фото?\n\n"
            "Или введите 'отмена' для отмены."
        )
        return

    # Проверяем, поддерживает ли текущая модель анализ изображений
    current_model = get_user_model(user_id)
    supports_vision = any(vision_model in current_model for vision_model in ["Vision", "VL", "vision"])

    if not supports_vision:
        # Автоматически переключимся на модель с поддержкой изображений
        vision_models = MODEL_CATEGORIES["С возможностью анализа изображений"]
        if vision_models:
            new_model = vision_models[0]

            # Сохраняем предыдущую модель для возврата
            if str(user_id) not in user_settings:
                user_settings[str(user_id)] = {
                    "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
                    "temperature": CONFIG["TEMPERATURE"],
                    "requests_left": CONFIG["MAX_DAILY_REQUESTS"],
                    "last_reset": str(date.today()),
                    "preferred_topics": [],
                    "favorite_models": [],
                    "last_active": str(date.today()),
                    "is_premium": False,
                    "premium_until": None,
                    "language": "ru",
                    "notifications_enabled": True,
                    "auto_translate": False,
                    "interface_mode": "standard",
                    "stream_mode": CONFIG["STREAM_RESPONSES"]
                }

            # Запоминаем предыдущую модель
            previous_model = user_settings[str(user_id)].get("model", ALL_MODELS[0])
            user_settings[str(user_id)]["previous_model"] = previous_model

            # Устанавливаем модель с поддержкой изображений
            user_settings[str(user_id)]["model"] = new_model
            await save_user_settings()

            await message.answer(
                f"🔄 Временно переключаюсь на модель с поддержкой анализа изображений: "
                f"**{format_model_name(new_model)}**",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message.answer(
                "❌ Текущая модель не поддерживает анализ изображений, и нет доступных моделей с такой функциональностью."
            )
            return

    # Показываем индикатор обработки
    await bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
    
    # Показываем сообщение "AI думает..."
    thinking_msg_id = await send_thinking_animation(message.chat.id)

    # Обрабатываем изображение
    image_data = await process_image(photo)

    if not image_data:
        # Удаляем сообщение "AI думает..."
        if thinking_msg_id:
            await remove_thinking_animation(message.chat.id)
            
        await message.answer(
            "❌ Не удалось обработать изображение. Убедитесь, что оно в формате JPG, JPEG, PNG или WEBP "
            "и его размер не превышает 10 МБ."
        )
        return

    # Получаем ответ от AI
    await bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
    ai_response = await get_ai_response(user_id, caption, image_data)

    # Удаляем сообщение "AI думает..."
    if thinking_msg_id:
        await remove_thinking_animation(message.chat.id)

    # Если временно переключили модель, возвращаемся к предыдущей
    if not supports_vision and str(user_id) in user_settings and "previous_model" in user_settings[str(user_id)]:
        previous_model = user_settings[str(user_id)]["previous_model"]
        user_settings[str(user_id)]["model"] = previous_model
        del user_settings[str(user_id)]["previous_model"]
        await save_user_settings()

        # Отправляем ответ
        ai_response = clean_markdown(ai_response)
        
        # Определяем, нужно ли использовать потоковый режим для ответа
        use_stream = get_user_stream_mode(user_id) and len(ai_response) > 500
        
        if use_stream:
            sent_message = await stream_and_send_response(message, ai_response)
        else:
            sent_message = await message.answer(ai_response, parse_mode=ParseMode.MARKDOWN)
        
        # Добавляем кнопки обратной связи
        feedback_id = str(uuid.uuid4())
        try:
            await sent_message.edit_reply_markup(reply_markup=await create_feedback_keyboard(feedback_id))
        except Exception as e:
            logger.warning(f"Не удалось добавить кнопки обратной связи: {e}")

        await message.answer(
            f"🔄 Вернулся к предыдущей модели: **{format_model_name(previous_model)}**",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # Отправляем ответ
        ai_response = clean_markdown(ai_response)
        
        # Определяем, нужно ли использовать потоковый режим для ответа
        use_stream = get_user_stream_mode(user_id) and len(ai_response) > 500
        
        if use_stream:
            sent_message = await stream_and_send_response(message, ai_response)
        else:
            sent_message = await message.answer(ai_response, parse_mode=ParseMode.MARKDOWN)
        
        # Добавляем кнопки обратной связи
        feedback_id = str(uuid.uuid4())
        try:
            await sent_message.edit_reply_markup(reply_markup=await create_feedback_keyboard(feedback_id))
        except Exception as e:
            logger.warning(f"Не удалось добавить кнопки обратной связи: {e}")

# Admin command - generate premium code
@router.message(Command("gencode"))
@admin_only
@safe_execution
async def cmd_generate_code(message: Message):
    """Генерирует премиум-код для активации (только для администраторов)."""
    # Загружаем премиум-коды, если еще не загружены
    if not premium_codes:
        await load_premium_codes()
    
    # Генерируем новый код
    new_code = generate_premium_code()
    await save_premium_codes()
    
    await message.answer(
        f"✅ Новый премиум-код создан: `{new_code}`\n\n"
        f"Этот код можно использовать для активации премиум-режима на 30 дней.",
        parse_mode=ParseMode.MARKDOWN
    )

# Admin command - send broadcast
@router.message(Command("broadcast"))
@admin_only
@safe_execution
async def cmd_broadcast(message: Message, state: FSMContext):
    """Отправляет сообщение всем пользователям бота (только для администраторов)."""
    await state.set_state(UserStates.waiting_for_admin_broadcast)
    
    await message.answer(
        "📢 Режим рассылки сообщений.\n\n"
        "Введите текст, который будет отправлен всем пользователям бота.\n\n"
        "Для отмены напишите 'отмена'."
    )

# Admin command - get statistics
@router.message(Command("stats"))
@admin_only
@safe_execution
async def cmd_stats(message: Message):
    """Показывает статистику бота (только для администраторов)."""
    stats = bot_metrics.get_stats()
    
    stats_text = (
        f"📊 **Статистика бота (v{BOT_VERSION})**\n\n"
        f"⏱️ **Время работы**: {stats['uptime_formatted']}\n"
        f"👥 **Активных пользователей**: {stats['users']['active_count']}\n\n"
        f"🔢 **Запросы**:\n"
        f"- Всего: {stats['requests']['total']}\n"
        f"- Успешных: {stats['requests']['success']}\n"
        f"- Неудачных: {stats['requests']['failed']}\n"
        f"- Процент успеха: {stats['requests']['success_rate']:.1f}%\n"
        f"- Сложных запросов: {stats['complex_queries']}\n\n"
        f"🚫 **Спам-фильтр**:\n"
        f"- Заблокировано сообщений: {stats['spam_blocked']}\n"
        f"- Блок-лист пользователей: {len(blocked_users)}\n\n"
        f"⏱️ **Время ответа**:\n"
        f"- Среднее: {stats['response_time']['average_ms']:.0f} мс\n"
        f"- Минимальное: {stats['response_time']['min_ms']:.0f} мс\n"
        f"- Максимальное: {stats['response_time']['max_ms']:.0f} мс\n\n"
    )
    
    # Добавляем топ-3 модели по использованию
    stats_text += "📈 **Топ модели**:\n"
    top_models = list(stats['models'].items())[:3]
    for i, (model, count) in enumerate(top_models, 1):
        model_name = model.split('/')[-1]
        stats_text += f"{i}. {model_name}: {count} запросов\n"
    
    stats_text += "\n🔍 **Топ темы**:\n"
    top_topics = list(stats['topics'].items())[:3]
    for i, (topic, count) in enumerate(top_topics, 1):
        stats_text += f"{i}. {topic.capitalize()}: {count} запросов\n"
    
    # Добавляем топ ошибок
    stats_text += "\n❌ **Частые ошибки**:\n"
    for error, count in list(stats['top_errors'].items())[:3]:
        # Сокращаем слишком длинные сообщения об ошибках
        error_text = error[:50] + "..." if len(error) > 50 else error
        stats_text += f"- {error_text}: {count} раз\n"
    
    await message.answer(stats_text, parse_mode=ParseMode.MARKDOWN)

# Admin command - create backup
@router.message(Command("backup"))
@admin_only
@safe_execution
async def cmd_backup(message: Message):
    """Создает резервную копию данных (только для администраторов)."""
    await message.answer("⏳ Создаю резервную копию данных...")
    
    backup_path = await create_backup_zip()
    if backup_path:
        # Отправляем файл бэкапа
        try:
            await message.answer_document(
                FSInputFile(backup_path, filename=os.path.basename(backup_path)),
                caption=f"✅ Резервная копия данных создана {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as e:
            await message.answer(f"⚠️ Резервная копия создана, но не удалось отправить файл: {e}")
    else:
        await message.answer("❌ Не удалось создать резервную копию данных.")

# Admin command - maintenance mode
@router.message(Command("maintenance"))
@admin_only
@safe_execution
async def cmd_maintenance(message: Message):
    """Включает или выключает режим технического обслуживания (только для администраторов)."""
    # Переключаем режим обслуживания
    CONFIG["MAINTENANCE_MODE"] = not CONFIG["MAINTENANCE_MODE"]
    
    if CONFIG["MAINTENANCE_MODE"]:
        await message.answer(
            "🔧 Режим технического обслуживания **ВКЛЮЧЕН**\n\n"
            "Бот будет отвечать только администраторам. Всем остальным пользователям будет показано сообщение о техническом обслуживании.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.answer(
            "✅ Режим технического обслуживания **ВЫКЛЮЧЕН**\n\n"
            "Бот снова доступен для всех пользователей.",
            parse_mode=ParseMode.MARKDOWN
        )

@router.message()
@safe_execution
@rate_limit
@spam_filter
async def handle_message(message: Message, state: FSMContext):
    """Обрабатывает все остальные текстовые сообщения."""
    # Проверяем режим обслуживания
    if CONFIG["MAINTENANCE_MODE"] and message.from_user.id not in CONFIG["ADMIN_IDS"]:
        await message.answer(
            "🔧 Бот находится на техническом обслуживании.\n\n"
            "Пожалуйста, попробуйте позже. Приносим извинения за временные неудобства."
        )
        return
    
    # Проверяем, не является ли сообщение простым приветствием
    greeting_response = is_greeting(message.text)
    if greeting_response:
        await message.answer(greeting_response)
        return

    user_id = message.from_user.id
    username = message.from_user.username

    # Обновляем дату последней активности пользователя
    if str(user_id) in user_settings:
        user_settings[str(user_id)]["last_active"] = str(date.today())
        await save_user_settings()

    # Проверяем и обновляем количество запросов
    if not (is_premium_user(user_id) or username == "qqq5599"):
        today = date.today().strftime("%Y-%m-%d")
        if str(user_id) not in user_settings:
            # Инициализируем настройки для нового пользователя
            user_settings[str(user_id)] = {
                "model": ALL_MODELS[0],
                "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
                "temperature": CONFIG["TEMPERATURE"],
                "requests_left": CONFIG["MAX_DAILY_REQUESTS"],
                "last_reset": today,
                "preferred_topics": [],
                "favorite_models": [],
                "last_active": today,
                "is_premium": False,
                "premium_until": None,
                "language": "ru",
                "notifications_enabled": True,
                "auto_translate": False,
                "interface_mode": "standard",
                "stream_mode": CONFIG["STREAM_RESPONSES"]
            }
            await save_user_settings()
        elif user_settings[str(user_id)].get("last_reset") != today:
            user_settings[str(user_id)]["requests_left"] = CONFIG["MAX_DAILY_REQUESTS"]
            user_settings[str(user_id)]["last_reset"] = today
            await save_user_settings()

        if user_settings[str(user_id)].get("requests_left", 0) <= 0:
            # Создаем клавиатуру для активации премиума
            keyboard = InlineKeyboardBuilder()
            keyboard.row(InlineKeyboardButton(
                text="⭐ Активировать премиум", 
                callback_data="activate_premium"
            ))
            
            await message.answer(
                "❌ Лимит запросов на сегодня исчерпан.\n\n"
                "Чтобы получить неограниченный доступ, активируйте премиум-режим!",
                reply_markup=keyboard.as_markup()
            )
            return

        user_settings[str(user_id)]["requests_left"] -= 1
        await save_user_settings()

    # Показываем, что бот "печатает"
    await bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
    
    # Показываем сообщение "AI думает..."
    thinking_msg_id = await send_thinking_animation(message.chat.id)

    # Определяем тему вопроса для возможного выбора специализированной модели
    topic = detect_question_topic(message.text)
    if topic:
        logger.info(f"Определена тема вопроса: {topic}")

    # Получаем ответ от AI
    start_time = time.time()
    ai_response = await get_ai_response(user_id, message.text)
    response_time = time.time() - start_time
    
    # Удаляем сообщение "AI думает..."
    if thinking_msg_id:
        await remove_thinking_animation(message.chat.id)
        
    logger.info(f"Получен ответ за {response_time:.2f} секунд")

    # Определяем, нужно ли использовать потоковый режим для ответа
    use_stream = get_user_stream_mode(user_id) and len(ai_response) > 500
    
    # Отправляем ответ с разбивкой на части при необходимости
    try:
        # Очищаем Markdown перед отправкой
        ai_response = clean_markdown(ai_response)
        
        # Отправляем сообщение в зависимости от режима
        if use_stream:
            sent_message = await stream_and_send_response(message, ai_response)
        else:
            # Отправляем сообщение обычным способом
            sent_message = await message.answer(ai_response, parse_mode=ParseMode.MARKDOWN)
        
        # Добавляем кнопки обратной связи
        feedback_id = str(uuid.uuid4())
        try:
            await sent_message.edit_reply_markup(reply_markup=await create_feedback_keyboard(feedback_id))
        except Exception as e:
            logger.warning(f"Не удалось добавить кнопки обратной связи: {e}")
    
    except TelegramAPIError as e:
        logger.error(f"Ошибка при отправке ответа: {e}")
        
        # Пробуем отправить без форматирования
        try:
            sent_message = await message.answer(ai_response, parse_mode=None)
            
            # Добавляем кнопки обратной связи
            feedback_id = str(uuid.uuid4())
            try:
                await sent_message.edit_reply_markup(reply_markup=await create_feedback_keyboard(feedback_id))
            except Exception as inner_e:
                logger.warning(f"Не удалось добавить кнопки обратной связи: {inner_e}")
        
        except Exception as e2:
            logger.error(f"Не удалось отправить сообщение даже без форматирования: {e2}")
            
            # В крайнем случае, разбиваем на части и отправляем
            try:
                last_message = await split_and_send_message(message, ai_response, parse_mode=None)
                
                # Добавляем кнопки обратной связи к последнему сообщению
                if last_message:
                    feedback_id = str(uuid.uuid4())
                    try:
                        await last_message.edit_reply_markup(reply_markup=await create_feedback_keyboard(feedback_id))
                    except Exception as e3:
                        logger.warning(f"Не удалось добавить кнопки обратной связи: {e3}")
            
            except Exception as e3:
                logger.error(f"Все попытки отправить сообщение провалились: {e3}")
                await message.answer("❌ Произошла ошибка при отправке ответа. Пожалуйста, попробуйте еще раз.")

# Задача для периодической очистки устаревших данных
async def cleanup_old_data():
    """Периодически очищает устаревшие данные для оптимизации работы."""
    while True:
        try:
            logger.info("Запуск очистки устаревших данных")
            
            # Очищаем устаревший кэш моделей
            current_time = time.time()
            for key in list(model_cache.keys()):
                if current_time - model_cache[key]["timestamp"] > CONFIG["CACHE_TIMEOUT"]:
                    del model_cache[key]
            
            # Очищаем файлы временного хранилища пользователей
            for user_folder in glob.glob(os.path.join(USER_MEDIA_DIR, "*")):
                try:
                    # Удаляем файлы старше 24 часов
                    for user_file in glob.glob(os.path.join(user_folder, "*")):
                        file_time = os.path.getmtime(user_file)
                        if current_time - file_time > 86400:  # 24 часа
                            os.remove(user_file)
                            logger.debug(f"Удален устаревший файл: {user_file}")
                except Exception as e:
                    logger.warning(f"Ошибка при очистке файлов пользователя: {e}")
            
            # Архивируем контексты неактивных пользователей
            today = date.today()
            inactive_threshold = 30  # Дней
            
            for user_id, settings in list(user_settings.items()):
                if "last_active" in settings:
                    try:
                        last_active = date.fromisoformat(settings["last_active"])
                        days_inactive = (today - last_active).days
                        
                        if days_inactive > inactive_threshold:
                            # Архивируем контекст, если он существует
                            if int(user_id) in user_contexts and user_contexts[int(user_id)]:
                                # Создаем архивную папку если её нет
                                archive_dir = os.path.join(CONFIG["PERSISTENT_STORAGE"], "archived_contexts")
                                os.makedirs(archive_dir, exist_ok=True)
                                
                                # Сохраняем контекст в архив (асинхронно)
                                archive_file = os.path.join(archive_dir, f"context_{user_id}_{last_active}.json")
                                async with aio_open(archive_file, 'w', encoding='utf-8') as f:
                                    await f.write(json.dumps(user_contexts[int(user_id)], ensure_ascii=False, indent=2))
                                
                                # Удаляем контекст из оперативной памяти
                                del user_contexts[int(user_id)]
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Ошибка при обработке даты для пользователя {user_id}: {e}")
            
            # Сохраняем очищенные контексты
            await save_user_contexts()
            
            # Очищаем старые файлы метрик
            await bot_metrics._cleanup_old_metrics(48)  # Оставляем метрики за 48 часов
            
            logger.info("Очистка устаревших данных завершена")
        
        except Exception as e:
            logger.error(f"Ошибка при очистке устаревших данных: {e}\n{traceback.format_exc()}")
        
        # Запускаем очистку раз в день
        await asyncio.sleep(86400)  # 24 часа

# Обработчик для webhook
async def handle_webhook(request):
    """Обрабатывает вебхук от Telegram."""
    if request.match_info.get('token') != CONFIG["TOKEN"]:
        return web.Response(status=403)
    
    try:
        # Получаем обновление от Telegram
        update_data = await request.json()
        
        # Передаем обновление диспетчеру
        await dp.feed_update(bot=bot, update=update_data)
        
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {e}\n{traceback.format_exc()}")
        return web.Response(status=500)

# Добавляем простой обработчик для домашней страницы
async def handle_home(request):
    """Обработчик домашней страницы для проверки работоспособности."""
    return web.Response(text="Telegram Bot Server is running.")

# Обработчик для проверки здоровья сервиса
async def handle_health(request):
    """Обработчик для проверки статуса сервиса."""
    response = {
        "status": "online",
        "version": BOT_VERSION,
        "uptime": time.time() - start_time,
        "maintenance_mode": CONFIG["MAINTENANCE_MODE"],
        "timestamp": time.time()
    }
    return web.json_response(response)

# Обработчик для получения статистики бота
async def handle_stats(request):
    """Обработчик для получения статистики бота."""
    # Простая защита на основе ключа
    auth_key = request.query.get('key')
    if auth_key != CONFIG.get("STATS_API_KEY", "statskey"):
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    stats = bot_metrics.get_stats()
    return web.json_response(stats)

# Функция инициализации и запуска бота
async def main():
    """Инициализация и запуск бота."""
    global start_time, http_session
    start_time = time.time()
    
    # Создаем HTTP сессию для асинхронных запросов
    http_session = aiohttp.ClientSession()
    
    try:
        # Загружаем настройки и данные
        await load_user_settings()
        await load_user_contexts()
        await load_model_performance()
        await load_premium_codes()
        await load_blocked_users()
        await load_spam_patterns()
        
        # Проверяем успешность запуска
        startup_success = await verify_bot_startup()
        if not startup_success:
            logger.warning("Бот запущен с предупреждениями. Некоторые функции могут работать некорректно.")

        # Инициализируем метрики
        await bot_metrics.initialize()

        # Настраиваем маршруты для веб-сервера
        app = web.Application()
        app.router.add_get('/', handle_home)
        app.router.add_get('/health', handle_health)
        app.router.add_get('/stats', handle_stats)
        app.router.add_post(f'/webhook/{CONFIG["TOKEN"]}', handle_webhook)

        if CONFIG["USE_WEBHOOK"]:
            # Настраиваем вебхук
            webhook_url = f"{APP_URL}/webhook/{CONFIG['TOKEN']}"
            await bot.set_webhook(url=webhook_url, secret_token=CONFIG["WEBHOOK_SECRET_TOKEN"])
            logger.info(f"Webhook set to {webhook_url}")
            
            # Запускаем фоновые задачи
            asyncio.create_task(cleanup_old_data())
            asyncio.create_task(perform_health_check())
            
            # Выводим информацию о запуске
            logger.info(f"Бот запущен в режиме webhook! Используется {len(ALL_MODELS)} моделей.")
            
            # Запускаем веб-сервер
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', PORT)
            await site.start()
            
            logger.info(f"Веб-сервер запущен на порту {PORT}")
            
            # Ждем вечно
            while True:
                await asyncio.sleep(3600)
        else:
            # Очищаем веб-хуки и запускаем бота в режиме polling
            await bot.delete_webhook(drop_pending_updates=True)

            # Запускаем фоновые задачи
            asyncio.create_task(cleanup_old_data())
            asyncio.create_task(perform_health_check())

            # Выводим информацию о запуске
            logger.info(f"Бот запущен в режиме polling! Используется {len(ALL_MODELS)} моделей.")

            # Запускаем сервер для Render
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', PORT)
            await site.start()
            
            logger.info(f"Веб-сервер запущен на порту {PORT}")

            # Запускаем поллинг
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    
    finally:
        # Закрываем HTTP сессию при завершении работы
        if http_session is not None:
            await http_session.close()

# Обрабатываем неожиданные завершения и перезапускаем бота
async def start_bot_with_recovery():
    """Запускает бота с автоматическим восстановлением при сбоях."""
    max_restarts = 5
    restart_count = 0
    restart_delay = 5  # начальная задержка в секундах
    
    while restart_count < max_restarts:
        try:
            await main()
            # Если main() завершился нормально, выходим из цикла
            break
        except Exception as e:
            restart_count += 1
            logger.critical(
                f"Критическая ошибка в работе бота: {e}\n{traceback.format_exc()}\n"
                f"Перезапуск {restart_count}/{max_restarts} через {restart_delay} секунд"
            )
            
            # Отправляем уведомление администраторам
            for admin_id in CONFIG["ADMIN_IDS"]:
                try:
                    await bot.send_message(
                        admin_id,
                        f"🚨 Критическая ошибка бота:\n{str(e)[:500]}\n\nПерезапуск {restart_count}/{max_restarts}"
                    )
                except Exception as notify_error:
                    logger.error(f"Не удалось уведомить администратора {admin_id}: {notify_error}")
            
            # Увеличиваем задержку с каждым перезапуском (экспоненциальный backoff)
            await asyncio.sleep(restart_delay)
            restart_delay *= 2  # увеличиваем задержку в 2 раза с каждым перезапуском
            
    if restart_count >= max_restarts:
        logger.critical(f"Бот не может быть запущен после {max_restarts} попыток. Завершение работы.")
        # Финальное уведомление администраторам перед выходом
        for admin_id in CONFIG["ADMIN_IDS"]:
            try:
                await bot.send_message(
                    admin_id, 
                    f"🚨 Критическая ошибка: бот не может быть запущен после {max_restarts} попыток."
                )
            except Exception:
                pass

if __name__ == "__main__":
    # Создаем и запускаем event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Запускаем бота с восстановлением
        loop.run_until_complete(start_bot_with_recovery())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
