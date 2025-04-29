import asyncio
import logging
import json
import os
import re
import time
import requests
import traceback
import threading
import uuid
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Union, Any, Tuple
from functools import wraps
from aiohttp import web
from urllib.parse import urlencode

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

# Получаем порт из переменной окружения или используем 8080 по умолчанию
PORT = int(os.environ.get("PORT", 8080))
APP_URL = os.environ.get("APP_URL", "")

# Конфигурация путей для хранения данных на Render
# На бесплатном плане можно писать только в /tmp (временное хранилище) 
# или в директорию проекта /opt/render/project/src/
DATA_DIR = "/tmp" if os.path.exists("/opt/render") else "data"
os.makedirs(DATA_DIR, exist_ok=True)

# Настройка логирования с учетом ограничений Render
LOG_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Конфигурация и константы
CONFIG = {
    "API_URL": "https://api.intelligence.io.solutions/api/v1",
    "TOKEN": os.environ.get("TELEGRAM_TOKEN", "7839597384:AAFlm4v3qcudhJfiFfshz1HW6xpKhtqlV5g"),
    "API_KEY": os.environ.get("AI_API_KEY", "io-v2-eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJvd25lciI6ImJlMjYwYjFhLWI0OWMtNDU2MC04ODZiLTMwYTBmMGFlNGZlNSIsImV4cCI6NDg5OTUwNzg0MH0.Z46h1WZ-2jsXyg43r2M0okgeLoSEzrq-ULHRMS-EW6r3ccxYkXTZ5mNJO5Aw1qBAkRI5NX9t8zXc1sbUxt8WzA"),
    "DEFAULT_SYSTEM_PROMPT": "Вы - полезный AI-ассистент с энциклопедическими знаниями. Предоставляйте точные и информативные ответы. Вы обладаете обширными знаниями о различных исторических личностях, включая писателей, ученых и философов, таких как Пушкин, Толстой, Гоголь, Эйнштейн, Тесла, Ньютон, Сократ, и многих других. Для технических вопросов и примеров кода используйте Markdown-форматирование.",
    "MAX_MESSAGE_LENGTH": 4096,
    "MAX_CONTEXT_LENGTH": 20,  # Количество сообщений в истории
    "TEMPERATURE": 0.3,  # Уровень креативности (ниже = более предсказуемо)
    "MAX_TOKENS": 4000,  # Максимальная длина ответа
    "RETRY_ATTEMPTS": 5,  # Количество попыток при ошибке
    "ADMIN_IDS": [12345678],  # ID администраторов
    "ALLOWED_FORMATS": ["jpg", "jpeg", "png", "webp"],  # Поддерживаемые форматы изображений
    "MAX_FILE_SIZE": 10 * 1024 * 1024,  # Максимальный размер файла (10 МБ)
    "CACHE_TIMEOUT": 3600,  # Время жизни кэша в секундах (1 час)
    "FALLBACK_MODE": True,  # Автоматически переключаться на другие модели при ошибке
    "PERSISTENT_STORAGE": DATA_DIR,  # Директория для хранения данных (адаптировано для Render)
    "CONTEXT_DECAY": 0.9,  # Коэффициент важности старых сообщений в контексте (1.0 = все сообщения равнозначны)
    "REQUEST_TIMEOUT": 60,  # Таймаут запросов к API
    "USE_WEBHOOK": True if APP_URL else False,  # Использовать webhook вместо polling если указан APP_URL
    "MAX_INLINE_KEYBOARDS": 5,  # Максимальное количество кнопок в ряду для inline клавиатуры
}

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
}

# Шаблоны для распознавания запросов об исторических личностях
HISTORICAL_PATTERN = r"(?i)(?:кто (?:так(ой|ая|ое|ие)|был|явля(?:ет|л)ся|известен как)|расскаж(?:и|ите) (?:о|про|мне о|мне про)|что (?:ты |вы )?знаешь (?:о|про)|информаци[яю] (?:о|про))\s+([А-Яа-яЁё]+)"

# Настройка логирования с защитой от ошибок файловой системы
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

try:
    # Создаем файловый обработчик логов
    log_file_path = os.path.join(LOG_DIR, f"bot_{date.today().strftime('%Y-%m-%d')}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
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

# Кэш и переменные для моделей
model_cache = {}  # Кэш ответов моделей
user_settings = {}  # Настройки пользователей
user_contexts = {}  # История диалогов с пользователями
user_feedback = {}  # Отзывы пользователей о качестве ответов
model_performance = {}  # Статистика производительности моделей (для адаптивного выбора)
request_stats = {}  # Статистика запросов

# Декоратор для сохранения контекста при исключениях
def safe_execution(f):
    @wraps(f)
    async def wrapped(*args, **kwargs):
        try:
            return await f(*args, **kwargs)
        except Exception as e:
            # Получаем информацию о вызывающей функции
            error_context = {
                'function': f.__name__,
                'args': args,
                'kwargs': kwargs,
                'exception': str(e),
                'traceback': traceback.format_exc()
            }
            
            # Логируем ошибку с полным контекстом
            logger.error(f"Ошибка в {f.__name__}: {str(e)}\n{traceback.format_exc()}")
            
            # Если среди аргументов есть сообщение, отправляем уведомление
            for arg in args:
                if isinstance(arg, Message):
                    try:
                        await arg.answer("Произошла техническая ошибка. Попробуйте еще раз или обратитесь к администратору.")
                    except Exception:
                        pass
                    break
            return None
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

def save_data_to_json(data: Any, filename: str) -> bool:
    """Безопасно сохраняет данные в JSON-файл с защитой от потери данных."""
    filepath = os.path.join(CONFIG["PERSISTENT_STORAGE"], filename)
    temp_filepath = f"{filepath}.tmp"
    backup_filepath = f"{filepath}.bak"
    
    try:
        # Сначала записываем во временный файл
        with open(temp_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Затем копируем текущий файл в бекап, если он существует
        if os.path.exists(filepath):
            os.replace(filepath, backup_filepath)
        
        # И наконец, перемещаем временный файл на место основного
        os.replace(temp_filepath, filepath)
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении файла {filename}: {e}")
        return False

def load_data_from_json(filename: str, default_data: Any = None) -> Any:
    """Безопасно загружает данные из JSON-файла с восстановлением из резервной копии."""
    filepath = os.path.join(CONFIG["PERSISTENT_STORAGE"], filename)
    backup_filepath = f"{filepath}.bak"
    
    try:
        # Пытаемся прочитать основной файл
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Не удалось загрузить {filename}: {e}. Попытка восстановления из бекапа.")
        
        try:
            # Пытаемся восстановить из бекапа
            if os.path.exists(backup_filepath):
                with open(backup_filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as be:
            logger.error(f"Не удалось восстановить из бекапа {filename}: {be}")
        
        # Возвращаем данные по умолчанию, если загрузка и восстановление не удались
        return default_data if default_data is not None else {}

def save_user_settings():
    """Сохраняет настройки пользователей в JSON-файл."""
    save_data_to_json(user_settings, 'user_settings.json')

def load_user_settings():
    """Загружает настройки пользователей из JSON-файла."""
    global user_settings
    user_settings = load_data_from_json('user_settings.json', {})

    # Миграция старых настроек и добавление новых полей
    for user_id, settings in user_settings.items():
        if "requests_left" not in settings:
            user_settings[user_id]["requests_left"] = 10
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

    save_user_settings()

def save_user_contexts():
    """Сохраняет контексты пользователей в JSON-файл."""
    # Преобразуем ключи (int) в строки для JSON
    serializable_contexts = {str(k): v for k, v in user_contexts.items()}
    save_data_to_json(serializable_contexts, 'user_contexts.json')

def load_user_contexts():
    """Загружает контексты пользователей из JSON-файла."""
    global user_contexts
    serialized_contexts = load_data_from_json('user_contexts.json', {})
    # Преобразуем ключи обратно в int
    user_contexts = {int(k): v for k, v in serialized_contexts.items()}

def save_model_performance():
    """Сохраняет данные о производительности моделей."""
    save_data_to_json(model_performance, 'model_performance.json')

def load_model_performance():
    """Загружает данные о производительности моделей."""
    global model_performance
    model_performance = load_data_from_json('model_performance.json', {})
    
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
    
    save_model_performance()

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
            "requests_left": 10,
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": []
        }
        save_user_settings()
    
    # Базовая модель пользователя
    base_model = user_settings[str(user_id)].get("model", ALL_MODELS[0])
    
    # Если текст сообщения не предоставлен, возвращаем базовую модель
    if not message_text:
        return base_model
    
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
        save_user_settings()
    
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
    
    # Сохраняем обновленный контекст
    save_user_contexts()

def clear_user_context(user_id: int):
    """Очищает историю диалога с пользователем."""
    if user_id in user_contexts:
        # Сохраняем только системный промпт, если он есть
        system_messages = [msg for msg in user_contexts[user_id] if msg["role"] == "system"]
        user_contexts[user_id] = system_messages if system_messages else []
        
        # Сохраняем обновленный контекст
        save_user_contexts()

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
    
    # Сохраняем обновленный контекст
    save_user_contexts()

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
    
    # Сохраняем обновленную статистику
    save_model_performance()

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

@safe_execution
async def process_image(photo: PhotoSize) -> Optional[str]:
    """Обрабатывает изображение и возвращает его в base64 кодировке."""
    try:
        file_info = await bot.get_file(photo.file_id)
        file_path = file_info.file_path

        if file_info.file_size > CONFIG["MAX_FILE_SIZE"]:
            return None

        # Получаем файл через Telegram API
        file_url = f"https://api.telegram.org/file/bot{CONFIG['TOKEN']}/{file_path}"
        response = requests.get(file_url, timeout=CONFIG["REQUEST_TIMEOUT"])

        if response.status_code != 200:
            logger.error(f"Ошибка получения файла: HTTP {response.status_code}")
            return None

        # Кодируем файл в base64
        import base64
        file_content = base64.b64encode(response.content).decode('utf-8')

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
    
    # Показываем избранные модели, если они есть
    favorite_models = user_settings.get(str(message.from_user.id), {}).get("favorite_models", [])
    if favorite_models:
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

@safe_execution
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

    # Проверяем кэш для экономии запросов к API
    cache_key = f"{model}:{message_text}:{temperature}"
    if cache_key in model_cache and time.time() - model_cache[cache_key]["timestamp"] < CONFIG["CACHE_TIMEOUT"]:
        return model_cache[cache_key]["response"]

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
            response = requests.post(
                f"{CONFIG['API_URL']}/chat/completions",
                headers={"Authorization": f"Bearer {CONFIG['API_KEY']}"},
                json=payload,
                timeout=CONFIG["REQUEST_TIMEOUT"]
            )
            response.raise_for_status()
            data = response.json()

            if 'choices' in data and data['choices']:
                ai_response = data['choices'][0]['message']['content']
                response_time = time.time() - start_time

                # Кэшируем ответ
                model_cache[cache_key] = {
                    "response": ai_response,
                    "timestamp": time.time()
                }

                # Добавляем ответ в контекст пользователя
                add_to_user_context(user_id, "assistant", ai_response)
                
                # Записываем статистику производительности модели
                record_model_performance(model, True, response_time, topic)
                record_request_stat(user_id, True, model, topic)

                return ai_response

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP ошибка: {e}, модель: {model}, попытка {attempt+1}/{CONFIG['RETRY_ATTEMPTS']}")
            
            # Записываем неудачную попытку
            record_model_performance(model, False, time.time() - start_time, topic)
            record_request_stat(user_id, False, model, topic)

            # Если это последняя попытка или автоматическое переключение отключено
            if attempt == CONFIG["RETRY_ATTEMPTS"] - 1 or not CONFIG["FALLBACK_MODE"]:
                error_message = (
                    f"❌ Ошибка при обработке запроса (HTTP {e.response.status_code}). Пожалуйста, попробуйте позже."
                )
                return error_message

            # Переключаемся на другую модель
            # Исключаем текущую модель из списка
            available_models = [m for m in ALL_MODELS if m != model]
            
            if available_models:
                # Предпочитаем модели, которые успешно работали с этой темой
                if topic and model_performance:
                    potential_models = []
                    for m in available_models:
                        if m in model_performance and topic in model_performance[m]["topics"]:
                            topic_stats = model_performance[m]["topics"][topic]
                            if topic_stats["successes"] > topic_stats["failures"]:
                                potential_models.append(m)
                    
                    if potential_models:
                        # Выбираем случайную модель из подходящих
                        import random
                        model = random.choice(potential_models)
                    else:
                        # Если нет подходящих для темы, берем случайную из доступных
                        model = random.choice(available_models)
                else:
                    # Без учета темы выбираем случайную модель
                    import random
                    model = random.choice(available_models)
                
                payload["model"] = model
                logger.info(f"Переключение на модель: {model}")
                continue
            else:
                return "❌ Не удалось найти работающую модель. Пожалуйста, попробуйте позже."

        except requests.exceptions.Timeout:
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
        response = requests.post(
            f"{CONFIG['API_URL']}/chat/completions",
            headers={"Authorization": f"Bearer {CONFIG['API_KEY']}"},
            json=payload,
            timeout=CONFIG["REQUEST_TIMEOUT"]
        )
        response.raise_for_status()
        data = response.json()
        
        if 'choices' in data and data['choices']:
            return data['choices'][0]['message']['content']
        
    except Exception as e:
        logger.error(f"Ошибка при перефразировании: {e}")
        return f"❌ Ошибка при обработке запроса: {str(e)[:100]}... Пожалуйста, попробуйте позже."
    
    return "❌ Не удалось перефразировать ответ. Пожалуйста, задайте новый вопрос."

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
    keyboard.adjust(2)

    welcome_text = (
        f"👋 Здравствуйте, {user_name}!\n\n"
        f"🤖 Я профессиональный AI-ассистент, работающий на основе передовых языковых моделей.\n\n"
        f"🔍 Я могу помочь вам с:\n"
        f"• Ответами на вопросы и объяснениями\n"
        f"• Написанием и анализом кода\n"
        f"• Созданием и редактированием текстов\n"
        f"• Анализом данных и рассуждениями\n"
        f"• Анализом изображений (для поддерживаемых моделей)\n\n"
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
            "requests_left": 10,
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today())
        }
        save_user_settings()
    
    # Обновляем дату последней активности
    user_settings[str(user_id)]["last_active"] = str(date.today())
    save_user_settings()

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
            "requests_left": 10,
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today())
        }
        save_user_settings()

    settings = user_settings[str(user_id)]
    model = settings.get("model", ALL_MODELS[0])
    system_prompt = settings.get("system_prompt", CONFIG["DEFAULT_SYSTEM_PROMPT"])
    temperature = settings.get("temperature", CONFIG["TEMPERATURE"])
    
    # Для обычных пользователей показываем счетчик запросов
    requests_info = ""
    username = message.from_user.username
    if not (username and username.lower() == "qqq5599"):
        requests_left = settings.get("requests_left", 0)
        requests_info = f"\n\n🔢 **Осталось запросов сегодня:** `{requests_left}`"

    # Создаем клавиатуру для настроек
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🔄 Сменить модель", callback_data="change_model"))
    keyboard.row(InlineKeyboardButton(text="📝 Изменить системный промпт", callback_data="change_prompt"))
    keyboard.row(InlineKeyboardButton(text="🎛️ Настроить креативность", callback_data="change_temp"))
    keyboard.row(InlineKeyboardButton(text="🔄 Начать новый диалог", callback_data="new_chat"))

    settings_text = (
        "⚙️ **Текущие настройки:**\n\n"
        f"🤖 **Модель:** `{format_model_name(model)}`\n\n"
        f"🌡️ **Креативность:** `{temperature}`\n\n"
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
        save_user_settings()

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
        save_user_contexts()

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
            "requests_left": 10,
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today())
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
    
    save_user_settings()
    
    # Возвращаемся к нормальному состоянию
    await state.clear()
    
    await message.answer(
        f"✅ Модель успешно изменена на: **{model_name}**\n\n"
        f"⚠️ Обратите внимание, что если указанная модель не существует или недоступна, "
        f"бот автоматически вернется к одной из доступных моделей при следующем запросе.\n\n"
        f"Модель также добавлена в ваш список избранных для быстрого доступа в будущем.",
        parse_mode=ParseMode.MARKDOWN
    )

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
            "requests_left": 10,
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today())
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
    
    save_user_settings()

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
            "requests_left": 10,
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today())
        }

    user_settings[str(user_id)]["temperature"] = temperature
    save_user_settings()

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
    
    # Получаем перефразированный ответ
    new_answer = await rephrase_answer(
        user_id,
        original_text,
        "Перефразируй этот ответ другими словами, сохраняя то же содержание, но выражая его иначе"
    )
    
    # Отправляем новый ответ с кнопками обратной связи
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
    
    # Получаем более подробный ответ
    new_answer = await rephrase_answer(
        user_id,
        original_text,
        "Расширь этот ответ, добавив больше подробностей, примеров и объяснений. Сделай ответ более полным и информативным."
    )
    
    # Отправляем новый ответ с кнопками обратной связи
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
            "requests_left": 10,
            "last_reset": str(date.today()),
            "preferred_topics": [],
            "favorite_models": [],
            "last_active": str(date.today())
        }

    user_settings[str(user_id)]["system_prompt"] = new_prompt
    save_user_settings()

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
    save_user_contexts()

    # Возвращаемся к нормальному состоянию
    await state.clear()

    await message.answer(
        "✅ Системный промпт успешно изменен!\n\n"
        "Теперь вы можете продолжить диалог с учетом новых инструкций."
    )

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

@router.message(F.photo)
@safe_execution
async def handle_photo(message: Message):
    """Обрабатывает сообщения с фотографиями."""
    user_id = message.from_user.id
    username = message.from_user.username

    # Обновляем дату последней активности пользователя
    if str(user_id) in user_settings:
        user_settings[str(user_id)]["last_active"] = str(date.today())
        save_user_settings()

    # Проверяем лимиты для пользователей (кроме qqq5599)
    if not (username and username.lower() == "qqq5599"):
        if str(user_id) in user_settings:
            today = date.today().strftime("%Y-%m-%d")
            if user_settings[str(user_id)].get("last_reset") != today:
                user_settings[str(user_id)]["requests_left"] = 10
                user_settings[str(user_id)]["last_reset"] = today
                save_user_settings()
            
            if user_settings[str(user_id)].get("requests_left", 0) <= 0:
                await message.answer("❌ Лимит запросов на сегодня исчерпан. Пожалуйста, попробуйте завтра.")
                return
            
            user_settings[str(user_id)]["requests_left"] -= 1
            save_user_settings()

    # Получаем фото наилучшего качества
    photo = message.photo[-1]

    # Получаем подпись к фото или используем дефолтный текст
    caption = message.caption or "Что на этом изображении?"

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
                    "requests_left": 10,
                    "last_reset": str(date.today()),
                    "preferred_topics": [],
                    "favorite_models": [],
                    "last_active": str(date.today())
                }

            # Запоминаем предыдущую модель
            previous_model = user_settings[str(user_id)].get("model", ALL_MODELS[0])
            user_settings[str(user_id)]["previous_model"] = previous_model

            # Устанавливаем модель с поддержкой изображений
            user_settings[str(user_id)]["model"] = new_model
            save_user_settings()

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

    # Обрабатываем изображение
    image_data = await process_image(photo)

    if not image_data:
        await message.answer(
            "❌ Не удалось обработать изображение. Убедитесь, что оно в формате JPG, JPEG, PNG или WEBP "
            "и его размер не превышает 10 МБ."
        )
        return

    # Получаем ответ от AI
    await bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
    ai_response = await get_ai_response(user_id, caption, image_data)

    # Если временно переключили модель, возвращаемся к предыдущей
    if not supports_vision and str(user_id) in user_settings and "previous_model" in user_settings[str(user_id)]:
        previous_model = user_settings[str(user_id)]["previous_model"]
        user_settings[str(user_id)]["model"] = previous_model
        del user_settings[str(user_id)]["previous_model"]
        save_user_settings()

        # Отправляем ответ
        ai_response = clean_markdown(ai_response)
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
        sent_message = await message.answer(ai_response, parse_mode=ParseMode.MARKDOWN)
        
        # Добавляем кнопки обратной связи
        feedback_id = str(uuid.uuid4())
        try:
            await sent_message.edit_reply_markup(reply_markup=await create_feedback_keyboard(feedback_id))
        except Exception as e:
            logger.warning(f"Не удалось добавить кнопки обратной связи: {e}")

@router.message()
@safe_execution
async def handle_message(message: Message, state: FSMContext):
    """Обрабатывает все остальные текстовые сообщения."""
    # Проверяем, не является ли сообщение простым приветствием
    greeting_response = is_greeting(message.text)
    if greeting_response:
        await message.answer(greeting_response)
        return

    user_id = str(message.from_user.id)
    username = message.from_user.username

    # Обновляем дату последней активности пользователя
    if user_id in user_settings:
        user_settings[user_id]["last_active"] = str(date.today())
        save_user_settings()

    # Проверяем и обновляем количество запросов
    if username and username.lower() == "qqq5599":
        # Пользователь с именем qqq5599 имеет безлимитный доступ
        pass  # Безлимит
    else:
        today = date.today().strftime("%Y-%m-%d")
        if user_id not in user_settings:
            # Инициализируем настройки для нового пользователя
            user_settings[user_id] = {
                "model": ALL_MODELS[0],
                "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
                "temperature": CONFIG["TEMPERATURE"],
                "requests_left": 10,
                "last_reset": today,
                "preferred_topics": [],
                "favorite_models": [],
                "last_active": today
            }
            save_user_settings()
        elif user_settings[user_id].get("last_reset") != today:
            user_settings[user_id]["requests_left"] = 10
            user_settings[user_id]["last_reset"] = today
            save_user_settings()

        if user_settings[user_id].get("requests_left", 0) <= 0:
            await message.answer("❌ Лимит запросов на сегодня исчерпан. Пожалуйста, попробуйте завтра.")
            return

        user_settings[user_id]["requests_left"] -= 1
        save_user_settings()

    # Показываем, что бот "печатает"
    await bot.send_chat_action(chat_id=int(user_id), action=ChatAction.TYPING)

    # Определяем тему вопроса для возможного выбора специализированной модели
    topic = detect_question_topic(message.text)
    if topic:
        logger.info(f"Определена тема вопроса: {topic}")

    # Получаем ответ от AI
    start_time = time.time()
    ai_response = await get_ai_response(int(user_id), message.text)
    response_time = time.time() - start_time
    
    logger.info(f"Получен ответ за {response_time:.2f} секунд")

    # Отправляем ответ с разбивкой на части при необходимости
    try:
        # Очищаем Markdown перед отправкой
        ai_response = clean_markdown(ai_response)
        
        # Отправляем сообщение
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
                                
                                # Сохраняем контекст в архив
                                archive_file = os.path.join(archive_dir, f"context_{user_id}_{last_active}.json")
                                with open(archive_file, 'w', encoding='utf-8') as f:
                                    json.dump(user_contexts[int(user_id)], f, ensure_ascii=False, indent=2)
                                
                                # Удаляем контекст из оперативной памяти
                                del user_contexts[int(user_id)]
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Ошибка при обработке даты для пользователя {user_id}: {e}")
            
            # Сохраняем очищенные контексты
            save_user_contexts()
            
            logger.info("Очистка устаревших данных завершена")
        
        except Exception as e:
            logger.error(f"Ошибка при очистке устаревших данных: {e}\n{traceback.format_exc()}")
        
        # Запускаем очистку раз в день
        await asyncio.sleep(86400)  # 24 часа

# Определяем веб-приложение для API
app = web.Application()

# Обработчик для webhook
async def handle_webhook(request):
    """Обрабатывает вебхук от Telegram."""
    if request.match_info.get('token') != CONFIG["TOKEN"]:
        return web.Response(status=403)
    
    request_body_bin = await request.read()
    request_body = request_body_bin.decode('utf-8')
    
    try:
        update = json.loads(request_body)
        update_id = update['update_id']
        
        # Обработка обновления
        await dp.feed_update(bot=bot, update=update)
        
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {e}")
        return web.Response(status=500)

# Добавляем простой обработчик для домашней страницы
async def handle_home(request):
    text = "Telegram Bot Server is running."
    return web.Response(text=text)

# Обработчик для проверки здоровья сервиса
async def handle_health(request):
    """Обработчик для проверки статуса сервиса."""
    response = {
        "status": "online",
        "version": "1.0.0",
        "uptime": time.time() - start_time,
        "timestamp": time.time()
    }
    return web.json_response(response)

# Настраиваем маршруты
app.router.add_get('/', handle_home)
app.router.add_get('/health', handle_health)
app.router.add_post('/webhook/{token}', handle_webhook)

# Функция инициализации и запуска бота
async def main():
    """Инициализация и запуск бота."""
    global start_time
    start_time = time.time()
    
    # Загружаем настройки и данные
    load_user_settings()
    load_user_contexts()
    load_model_performance()

    if CONFIG["USE_WEBHOOK"]:
        # Настраиваем вебхук
        webhook_url = f"{APP_URL}/webhook/{CONFIG['TOKEN']}"
        await bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook set to {webhook_url}")
        
        # Запускаем задачу очистки устаревших данных
        asyncio.create_task(cleanup_old_data())
        
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
        # Традиционный подход с long polling
        # Очищаем веб-хуки и запускаем бота
        await bot.delete_webhook(drop_pending_updates=True)

        # Запускаем задачу очистки устаревших данных
        asyncio.create_task(cleanup_old_data())

        # Выводим информацию о запуске
        logger.info(f"Бот запущен в режиме polling! Используется {len(ALL_MODELS)} моделей.")

        # Запускаем сервер для Render
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()
        
        logger.info(f"Веб-сервер запущен на порту {PORT}")

        # Запускаем бота
        await dp.start_polling(bot)

if __name__ == "__main__":
    # Запускаем бота в асинхронном режиме
    asyncio.run(main())
