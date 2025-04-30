import asyncio
import logging
import json
import os
import re
import time
import requests
from datetime import datetime, date
from typing import Dict, List, Optional, Union

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

# Конфигурация и константы
CONFIG = {
    "API_URL": "https://api.intelligence.io.solutions/api/v1",
    "TOKEN": os.getenv("TELEGRAM_TOKEN", "7839597384:AAFlm4v3qcudhJfiFfshz1HW6xpKhtqlV5g"),
    "API_KEY": os.getenv("AI_API_KEY", "io-v2-eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJvd25lciI6Ijc3YmJkZTE2LTIwZmQtNDI0OS1hNDUxLTRhNjFjZWZmNzFkZSIsImV4cCI6NDg5OTU5MDk1MH0.hfjAFzMcTse2YZF4D_y2849zQaI62EascTdAeHI_C4OEPixfFAaU-iqugvuO-8gD7c1iDhNG0c1wpq4v_9Nn6w"),
    "DEFAULT_SYSTEM_PROMPT": "Вы - полезный AI-ассистент. Предоставляйте точные и информативные ответы. Для технических вопросов и примеров кода используйте Markdown-форматирование.",
    "MAX_MESSAGE_LENGTH": 4096,
    "MAX_CONTEXT_LENGTH": 15,  # Максимальное количество сообщений в истории
    "TEMPERATURE": 0.3,  # Уровень креативности (ниже = более предсказуемо)
    "MAX_TOKENS": 4000,  # Максимальная длина ответа
    "RETRY_ATTEMPTS": 3,  # Количество попыток переключения модели при ошибке
    "ADMIN_IDS": [12345678],  # ID администраторов (заменить на ваши ID)
    "ALLOWED_FORMATS": ["jpg", "jpeg", "png", "webp"],  # Поддерживаемые форматы изображений
    "MAX_FILE_SIZE": 10 * 1024 * 1024,  # Максимальный размер файла (10 МБ)
    "CACHE_TIMEOUT": 3600,  # Время жизни кэша в секундах (1 час)
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

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler("bot.log")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)
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

# Кэш и переменные для моделей
model_cache = {}  # Кэш ответов моделей
user_settings = {}  # Настройки пользователей
user_contexts = {}  # История диалогов с пользователями

# Функции-помощники
def format_model_name(model_name: str) -> str:
    """Форматирует имя модели для отображения."""
    return model_name.split('/')[-1]

def save_user_settings():
    """Сохраняет настройки пользователей в JSON-файл."""
    with open('user_settings.json', 'w', encoding='utf-8') as f:
        json.dump(user_settings, f, ensure_ascii=False, indent=2)

def load_user_settings():
    """Загружает настройки пользователей из JSON-файла."""
    global user_settings
    try:
        with open('user_settings.json', 'r', encoding='utf-8') as f:
            user_settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        user_settings = {}
        save_user_settings()

    # Миграция старых настроек
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

    save_user_settings()

async def show_typing_action(chat_id: int, duration: float = 2.0):
    """Показывает индикатор набора текста с указанной продолжительностью."""
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(duration)

def get_user_model(user_id: int) -> str:
    """Возвращает модель, выбранную пользователем, или модель по умолчанию."""
    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "model": ALL_MODELS[0],
            "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
            "temperature": CONFIG["TEMPERATURE"]
        }
        save_user_settings()
    return user_settings[str(user_id)].get("model", ALL_MODELS[0])

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

def add_to_user_context(user_id: int, role: str, content: str):
    """Добавляет сообщение в историю диалога с пользователем."""
    if user_id not in user_contexts:
        user_contexts[user_id] = []

    # Добавляем новое сообщение
    user_contexts[user_id].append({"role": role, "content": content})

    # Ограничиваем длину истории
    if len(user_contexts[user_id]) > CONFIG["MAX_CONTEXT_LENGTH"] * 2:  # *2 чтобы учесть пары вопрос-ответ
        # Оставляем первое сообщение (обычно системное) и последние N сообщений
        user_contexts[user_id] = [user_contexts[user_id][0]] + user_contexts[user_id][-(CONFIG["MAX_CONTEXT_LENGTH"]*2-1):]

def clear_user_context(user_id: int):
    """Очищает историю диалога с пользователем."""
    if user_id in user_contexts:
        # Сохраняем только системный промпт, если он есть
        system_messages = [msg for msg in user_contexts[user_id] if msg["role"] == "system"]
        user_contexts[user_id] = system_messages if system_messages else []

def is_greeting(text: str) -> Optional[str]:
    """Проверяет, является ли текст приветствием, и возвращает ответ, если да."""
    import random
    for pattern, responses in GREETINGS.items():
        if re.match(pattern, text.strip()):
            return random.choice(responses)
    return None

async def process_image(photo: PhotoSize) -> Optional[str]:
    """Обрабатывает изображение и возвращает его в base64 кодировке."""
    try:
        file_info = await bot.get_file(photo.file_id)
        file_path = file_info.file_path

        if file_info.file_size > CONFIG["MAX_FILE_SIZE"]:
            return None

        # Получаем файл через Telegram API
        file_url = f"https://api.telegram.org/file/bot{CONFIG['TOKEN']}/{file_path}"
        response = requests.get(file_url)

        if response.status_code != 200:
            return None

        # Кодируем файл в base64
        import base64
        file_content = base64.b64encode(response.content).decode('utf-8')

        # Определяем тип файла
        file_extension = file_path.split('.')[-1].lower()
        if file_extension not in CONFIG["ALLOWED_FORMATS"]:
            return None

        return f"data:image/{file_extension};base64,{file_content}"

    except Exception as e:
        logger.error(f"Ошибка при обработке изображения: {e}")
        return None

async def split_and_send_message(message: Message, text: str, parse_mode: Optional[str] = ParseMode.MARKDOWN):
    """Разделяет длинный текст на части и отправляет их."""
    max_length = CONFIG["MAX_MESSAGE_LENGTH"]

    if len(text) <= max_length:
        await message.answer(text, parse_mode=parse_mode)
        return

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
    for part in parts:
        await message.answer(part, parse_mode=parse_mode)
        await asyncio.sleep(0.3)  # Небольшая задержка между сообщениями

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

async def get_ai_response(user_id: int, message_text: str, image_data: Optional[str] = None) -> str:
    """Получает ответ от API на основе настроек пользователя."""
    model = get_user_model(user_id)
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

    # Подготавливаем данные для API
    payload = {
        "model": model,
        "messages": context,
        "temperature": temperature,
        "max_tokens": CONFIG["MAX_TOKENS"]
    }

    # Выполняем запрос к API с несколькими попытками
    for attempt in range(CONFIG["RETRY_ATTEMPTS"]):
        try:
            response = requests.post(
                f"{CONFIG['API_URL']}/chat/completions",
                headers={"Authorization": f"Bearer {CONFIG['API_KEY']}"},
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            if 'choices' in data and data['choices']:
                ai_response = data['choices'][0]['message']['content']

                # Кэшируем ответ
                model_cache[cache_key] = {
                    "response": ai_response,
                    "timestamp": time.time()
                }

                # Добавляем ответ в контекст пользователя
                add_to_user_context(user_id, "assistant", ai_response)

                return ai_response

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP ошибка: {e}, модель: {model}, попытка {attempt+1}/{CONFIG['RETRY_ATTEMPTS']}")

            # Если это последняя попытка, возвращаем сообщение об ошибке
            if attempt == CONFIG["RETRY_ATTEMPTS"] - 1:
                error_message = f"❌ Ошибка при обработке запроса (HTTP {e.response.status_code}). Пожалуйста, попробуйте позже."
                return error_message

            # Переключаемся на другую модель
            current_index = ALL_MODELS.index(model)
            next_index = (current_index + 1) % len(ALL_MODELS)
            model = ALL_MODELS[next_index]
            payload["model"] = model
            logger.info(f"Переключение на модель: {model}")

            # Обновляем полезную нагрузку с новой моделью
            continue

        except Exception as e:
            logger.error(f"Ошибка при запросе к API: {str(e)}")
            return f"❌ Произошла ошибка: {str(e)[:100]}... Пожалуйста, попробуйте позже."

    # Если все попытки не удались
    return "❌ Все модели временно недоступны. Пожалуйста, попробуйте позже."

# Обработчики команд и сообщений
@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    user_name = message.from_user.first_name

    # Создаем клавиатуру быстрого доступа
    keyboard = ReplyKeyboardBuilder()
    keyboard.add(KeyboardButton(text="🔄 Новый диалог"))
    keyboard.add(KeyboardButton(text="⚙️ Настройки"))
    keyboard.adjust(2)

    welcome_text = (
        f"👋 Здравствуйте, {user_name}!\n\n"
        f"🤖 Я профессиональный AI-ассистент, работающий на основе передовых языковых моделей.\n\n"
        f"🔍 Я могу помочь вам с:\n"
        f"• Ответами на вопросы и объяснениями\n"
        f"• Написанием и анализом кода\n"
        f"• Созданием и редактированием текстов\n"
        f"• Анализом данных и рассуждениями\n\n"
        f"💡 Просто напишите ваш вопрос или задачу, и я постараюсь помочь!"
    )

    await message.answer(
        welcome_text,
        reply_markup=keyboard.as_markup(resize_keyboard=True)
    )

    # Инициализируем настройки пользователя, если их еще нет
    user_id = message.from_user.id
    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "model": ALL_MODELS[0],
            "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
            "temperature": CONFIG["TEMPERATURE"],
            "requests_left": 10,
            "last_reset": str(date.today())
        }
        save_user_settings()

@router.message(Command("help"))
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
    )

    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Показывает текущие настройки пользователя."""
    user_id = message.from_user.id

    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "model": ALL_MODELS[0],
            "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
            "temperature": CONFIG["TEMPERATURE"],
            "requests_left": 10,
            "last_reset": str(date.today())
        }
        save_user_settings()

    settings = user_settings[str(user_id)]
    model = settings.get("model", ALL_MODELS[0])
    system_prompt = settings.get("system_prompt", CONFIG["DEFAULT_SYSTEM_PROMPT"])
    temperature = settings.get("temperature", CONFIG["TEMPERATURE"])

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
        f"📝 **Системный промпт:**\n```\n{system_prompt}\n```"
    )

    await message.answer(settings_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard.as_markup())

@router.message(Command("models"))
async def cmd_models(message: Message, state: FSMContext):
    """Показывает список доступных моделей."""
    await state.set_state(UserStates.waiting_for_model_selection)

    await message.answer(
        "📚 Выберите категорию моделей:",
        reply_markup=await create_model_selection_keyboard()
    )

@router.message(Command("prompt"))
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
            if msg["role"] == "system":
                user_contexts[user_id][i]["content"] = CONFIG["DEFAULT_SYSTEM_PROMPT"]
                break
        # Если системного сообщения нет, добавляем его
        else:
            user_contexts[user_id].insert(0, {"role": "system", "content": CONFIG["DEFAULT_SYSTEM_PROMPT"]})

    await message.answer(
        "✅ Системный промпт сброшен на значение по умолчанию.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("temp"))
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
async def callback_change_model(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки смены модели."""
    await state.set_state(UserStates.waiting_for_model_selection)

    await callback.message.answer(
        "📚 Выберите категорию моделей:",
        reply_markup=await create_model_selection_keyboard()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "change_prompt")
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
async def callback_select_category(callback: CallbackQuery):
    """Обработчик выбора категории моделей."""
    category = callback.data.split(":", 1)[1]

    await callback.message.edit_text(
        f"📚 Выберите модель из категории «{category}»:",
        reply_markup=await create_category_models_keyboard(category)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_categories")
async def callback_back_to_categories(callback: CallbackQuery):
    """Обработчик кнопки "Назад к категориям"."""
    await callback.message.edit_text(
        "📚 Выберите категорию моделей:",
        reply_markup=await create_model_selection_keyboard()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("model:"))
async def callback_select_model(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора модели."""
    user_id = callback.from_user.id
    model = callback.data.split(":", 1)[1]

    # Сохраняем выбранную модель в настройках пользователя
    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"],
            "temperature": CONFIG["TEMPERATURE"]
        }

    user_settings[str(user_id)]["model"] = model
    save_user_settings()

    # Возвращаемся к нормальному состоянию
    await state.clear()

    await callback.message.edit_text(
        f"✅ Модель успешно изменена на: **{format_model_name(model)}**\n\n"
        "Теперь вы можете задать мне любой вопрос!",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer("Модель установлена!")

@router.callback_query(lambda c: c.data.startswith("temp:"))
async def callback_select_temperature(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора значения temperature."""
    user_id = callback.from_user.id
    temperature = float(callback.data.split(":", 1)[1])

    # Сохраняем выбранное значение temperature
    if str(user_id) not in user_settings:
        user_settings[str(user_id)] = {
            "model": ALL_MODELS[0],
            "system_prompt": CONFIG["DEFAULT_SYSTEM_PROMPT"]
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

@router.message(StateFilter(UserStates.custom_system_prompt))
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
            "temperature": CONFIG["TEMPERATURE"]
        }

    user_settings[str(user_id)]["system_prompt"] = new_prompt
    save_user_settings()

    # Обновляем контекст пользователя
    if user_id in user_contexts:
        # Ищем и обновляем системное сообщение
        for i, msg in enumerate(user_contexts[user_id]):
            if msg["role"] == "system":
                user_contexts[user_id][i]["content"] = new_prompt
                break
        # Если системного сообщения нет, добавляем его
        else:
            user_contexts[user_id].insert(0, {"role": "system", "content": new_prompt})
    else:
        # Создаем новый контекст с системным промптом
        user_contexts[user_id] = [{"role": "system", "content": new_prompt}]

    # Возвращаемся к нормальному состоянию
    await state.clear()

    await message.answer(
        "✅ Системный промпт успешно изменен!\n\n"
        "Теперь вы можете продолжить диалог с учетом новых инструкций."
    )

@router.message(F.text == "🔄 Новый диалог")
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

@router.message(F.photo)
async def handle_photo(message: Message):
    """Обрабатывает сообщения с фотографиями."""
    user_id = message.from_user.id

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
                    "temperature": CONFIG["TEMPERATURE"]
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
        await split_and_send_message(message, ai_response)

        await message.answer(
            f"🔄 Вернулся к предыдущей модели: **{format_model_name(previous_model)}**",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # Отправляем ответ
        await split_and_send_message(message, ai_response)

@router.message()
async def handle_message(message: Message, state: FSMContext):
    """Обрабатывает все остальные текстовые сообщения."""
    # Проверяем, не является ли сообщение простым приветствием
    greeting_response = is_greeting(message.text)
    if greeting_response:
        await message.answer(greeting_response)
        return

    user_id = str(message.from_user.id)

    # Проверяем и обновляем количество запросов
    if user_id == "qqq5599":
        pass  # Безлимит
    else:
        today = date.today().strftime("%Y-%m-%d")
        if user_settings[user_id]["last_reset"] != today:
            user_settings[user_id]["requests_left"] = 10
            user_settings[user_id]["last_reset"] = today
            save_user_settings()

        if user_settings[user_id]["requests_left"] <= 0:
            await message.answer("❌ Лимит запросов на сегодня исчерпан. Пожалуйста, попробуйте завтра.")
            return

        user_settings[user_id]["requests_left"] -= 1
        save_user_settings()

    # Показываем, что бот "печатает"
    await bot.send_chat_action(chat_id=message.from_user.id, action=ChatAction.TYPING)

    # Получаем ответ от AI
    ai_response = await get_ai_response(message.from_user.id, message.text)

    # Отправляем ответ с разбивкой на части при необходимости
    await split_and_send_message(message, ai_response)

# Функция инициализации и запуска бота
async def main():
    """Инициализация и запуск бота."""
    # Загружаем настройки пользователей
    load_user_settings()

    # Очищаем веб-хуки и запускаем бота
    await bot.delete_webhook(drop_pending_updates=True)

    # Выводим информацию о запуске
    logger.info(f"Бот запущен! Используется {len(ALL_MODELS)} моделей.")

    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запускаем бота в асинхронном режиме
    asyncio.run(main())
