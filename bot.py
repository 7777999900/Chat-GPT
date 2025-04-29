import logging
from telegram import Update, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация бота
TELEGRAM_TOKEN = "8153698800:AAEtpJ5IlLTG9TIvpU4iM8EYagDkfdqGeeY"  # Замените на свой токен
IONET_API_KEY = "io-v2-eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJvd25lciI6Ijc3YmJkZTE2LTIwZmQtNDI0OS1hNDUxLTRhNjFjZWZmNzFkZSIsImV4cCI6NDg5OTQyMDY5OX0.H8-y9vk5MF4T46gcVD_6NeEGP-4WaZUcqcNV5LJclahCOm8oC79no0Nv5hbIBj3ZW0XLI9uoRErKzd_K41N4_g"  # Замените на свой ключ API от io.net
OWNER_USERNAME = "qqq5599"  # Имя владельца (без символа @)
DEFAULT_DAILY_LIMIT = 10  # Лимит сообщений в день для обычных пользователей

# Доступные модели
AVAILABLE_MODELS = {
    "llama4_maverick": {"name": "Llama-4 Maverick 17B", "id": "llama-4-maverick-17b"},
    "qwq": {"name": "QwQ 32B", "id": "qwq-32b"},
    "deepseek_r1": {"name": "DeepSeek R1", "id": "deepseek-r1"},
    "deepseek_r1_distill": {"name": "DeepSeek R1 Distill Llama 70B", "id": "deepseek-r1-distill-llama-70b"},
    "llama_3_3": {"name": "Llama 3.3 70B Instruct", "id": "llama-3.3-70b-instruct"},
    "dbrx": {"name": "DBRX Instruct", "id": "dbrx-instruct"},
    "sky_t1": {"name": "Sky T1 32B Preview", "id": "sky-t1-32b-preview"},
    "mistral_large": {"name": "Mistral Large Instruct", "id": "mistral-large-instruct"},
    "watt_tool": {"name": "Watt Tool 70B", "id": "watt-tool-70b"},
    "bespoke_stratos": {"name": "Bespoke Stratos 32B", "id": "bespoke-stratos-32b"},
}

# Доступные роли для бота
AVAILABLE_ROLES = {
    "assistant": "Универсальный ассистент, готовый помочь с любыми вопросами.",
    "teacher": "Ассистент-преподаватель: объясняет материал чётко и понятно, приводя примеры.",
    "programmer": "Ассистент-программист: объясняет технические аспекты, делая акцент на оптимизации и примерах кода.",
    "marketer": "Ассистент-маркетолог: предлагает маркетинговые стратегии, идеи и анализирует задачи.",
    "psychologist": "Ассистент-психолог: даёт рекомендации с учётом эмпатии и профессиональных знаний.",
    "analyst": "Ассистент-аналитик: строит логические выводы и структурирует информацию.",
    "writer": "Ассистент-писатель: помогает с созданием и редактированием текстов, стилистикой и структурой.",
    "translator": "Ассистент-переводчик: переводит тексты с одного языка на другой.",
    "scientist": "Ассистент-ученый: даёт научно обоснованные ответы, опираясь на академические знания."
}

# Стили общения
AVAILABLE_STYLES = {
    "balanced": "Сбалансированный (обычный стиль общения)",
    "concise": "Краткий (короткие и четкие ответы)",
    "detailed": "Подробный (развернутые и детальные ответы)",
    "professional": "Профессиональный (формальный стиль с использованием специальной терминологии)",
    "casual": "Неформальный (разговорный стиль, как при общении с другом)",
    "academic": "Академический (научный стиль с цитированием и точными формулировками)"
}

# Языки ответов
AVAILABLE_LANGUAGES = {
    "auto": "Автоопределение (ответ на языке запроса)",
    "russian": "Русский",
    "english": "Английский",
    "ukrainian": "Украинский",
    "german": "Немецкий",
    "french": "Французский",
    "spanish": "Испанский"
}

# Данные пользователей
user_data = {}

# Статистика использования API
api_stats = {
    "io_net": {"success": 0, "failures": 0, "last_success": None},
    "backup": {"success": 0, "failures": 0, "last_success": None}
}

# Состояние приложения
app_state = {
    "startup_time": datetime.now(),
    "messages_processed": 0,
    "active_users": set(),
    "last_error": None
}

def load_data():
    """Загрузка данных пользователей из файла"""
    global user_data
    try:
        if os.path.exists("bot_data.json"):
            with open("bot_data.json", "r", encoding="utf-8") as f:
                user_data = json.load(f)
            logger.info(f"Данные пользователей успешно загружены. Всего записей: {len(user_data)}")
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных: {e}")
        user_data = {}

def save_data():
    """Сохранение данных пользователей в файл"""
    try:
        with open("bot_data.json", "w", encoding="utf-8") as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
        logger.info("Данные пользователей успешно сохранены")
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {e}")

def backup_data():
    """Создание резервной копии данных пользователей"""
    try:
        backup_file = f"bot_data.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Создана резервная копия данных: {backup_file}")
        
        # Удаление старых резервных копий (оставляем только 5 последних)
        backup_files = [f for f in os.listdir() if f.startswith("bot_data.") and f.endswith(".bak")]
        backup_files.sort(reverse=True)
        for old_backup in backup_files[5:]:
            os.remove(old_backup)
            logger.info(f"Удалена устаревшая резервная копия: {old_backup}")
    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии: {e}")

async def check_user_limit(user_id, username):
    """Проверка лимита запросов пользователя"""
    # Владелец бота имеет безлимитный доступ
    if username == OWNER_USERNAME or username in get_vip_users():
        return True, "∞"  # Бесконечность
    
    today = datetime.now().strftime("%Y-%m-%d")
    user_id_str = str(user_id)
    
    if user_id_str not in user_data:
        user_data[user_id_str] = {
            "date": today,
            "count": 0,
            "model": "llama4_maverick",  # Модель по умолчанию
            "role": "assistant",  # Роль по умолчанию
            "style": "balanced",  # Стиль по умолчанию
            "language": "auto",   # Язык по умолчанию
            "history": [],        # История сообщений
            "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    else:
        # Обновление времени последней активности
        user_data[user_id_str]["last_activity"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Сброс счетчика, если это новый день
    if user_data[user_id_str]["date"] != today:
        user_data[user_id_str] = {
            "date": today,
            "count": 0,
            "model": user_data[user_id_str]["model"],
            "role": user_data[user_id_str]["role"],
            "style": user_data[user_id_str]["style"],
            "language": user_data[user_id_str]["language"],
            "history": user_data[user_id_str]["history"],
            "first_seen": user_data[user_id_str]["first_seen"],
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_data()
    
    # Проверка лимита
    if user_data[user_id_str]["count"] < DEFAULT_DAILY_LIMIT:
        user_data[user_id_str]["count"] += 1
        save_data()
        remaining = DEFAULT_DAILY_LIMIT - user_data[user_id_str]["count"]
        return True, str(remaining)
    
    return False, 0

def get_vip_users():
    """Получение списка VIP-пользователей (кроме владельца)"""
    vip_users = []
    try:
        if os.path.exists("vip_users.txt"):
            with open("vip_users.txt", "r", encoding="utf-8") as f:
                vip_users = [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"Ошибка при загрузке списка VIP-пользователей: {e}")
    
    return vip_users

async def get_ai_response(prompt, model_id, role, style, language="auto", history=None, user_name="Пользователь"):
    """Получение ответа от модели через io.net API или резервный API с повторными попытками"""
    if history is None:
        history = []
    
    # Обработка языка ответа
    lang_instruction = ""
    if language != "auto":
        lang = AVAILABLE_LANGUAGES.get(language, "русский")
        lang_instruction = f" Отвечай только на {lang} языке, независимо от языка запроса."
    
    # Формирование системного промпта на основе роли и стиля
    system_prompt = f"Ты - {AVAILABLE_ROLES[role]}{lang_instruction}"
    
    if style == "concise":
        system_prompt += " Отвечай кратко и по существу, избегая длинных объяснений."
    elif style == "detailed":
        system_prompt += " Давай подробные и развернутые ответы с детальными объяснениями."
    elif style == "professional":
        system_prompt += " Используй профессиональный и формальный стиль общения с соответствующей терминологией."
    elif style == "casual":
        system_prompt += " Общайся в неформальном, дружелюбном стиле, как при разговоре с хорошим знакомым."
    elif style == "academic":
        system_prompt += " Используй академический стиль, приводи ссылки на источники и точные формулировки."
    
    # Добавление информации о пользователе в промпт
    system_prompt += f" Ты общаешься с пользователем по имени {user_name}."
    
    # Формирование сообщений для API
    messages = [{"role": "system", "content": system_prompt}]
    
    # Добавление истории сообщений (последние 10 сообщений)
    for msg in history[-10:]:
        messages.append(msg)
    
    # Добавление текущего сообщения пользователя
    messages.append({"role": "user", "content": prompt})
    
    # Попытка использования основного API
    io_net_response = await try_io_net_api(model_id, messages)
    if io_net_response:
        return io_net_response
    
    # Если основной API не работает, пробуем резервный API
    backup_response = await try_backup_api(messages)
    if backup_response:
        return backup_response
    
    # Если все API не работают, возвращаем сообщение об ошибке
    return "Извините, в данный момент все API-сервисы недоступны. Пожалуйста, попробуйте позже или обратитесь к администратору."

async def try_io_net_api(model_id, messages, max_retries=3):
    """Попытка получить ответ от io.net API с несколькими повторными попытками"""
    model_id_to_use = AVAILABLE_MODELS[model_id]["id"]
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {IONET_API_KEY}"
                }
                
                payload = {
                    "model": model_id_to_use,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2000
                }
                
                async with session.post(
                    "https://api.io.net/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60  # Увеличенный таймаут
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        api_stats["io_net"]["success"] += 1
                        api_stats["io_net"]["last_success"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        return data["choices"][0]["message"]["content"]
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка API io.net (попытка {attempt+1}/{max_retries}): {response.status}, {error_text}")
                        api_stats["io_net"]["failures"] += 1
                        
                        # Пауза перед повторной попыткой
                        await asyncio.sleep(1 * (attempt + 1))
        except Exception as e:
            logger.error(f"Исключение при запросе к API io.net (попытка {attempt+1}/{max_retries}): {e}")
            api_stats["io_net"]["failures"] += 1
            
            # Пауза перед повторной попыткой
            await asyncio.sleep(1 * (attempt + 1))
    
    return None

async def try_backup_api(messages, max_retries=3):
    """Попытка получить ответ от резервного API (Anthropic Claude)"""
    # Настройка ключа API Claude (в реальном приложении должен быть задан)
    CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
    
    if not CLAUDE_API_KEY:
        logger.warning("Резервный API не настроен (отсутствует ключ CLAUDE_API_KEY)")
        return None
    
    for attempt in range(max_retries):
        try:
            headers = {
                "Content-Type": "application/json",
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01"
            }
            
            # Преобразование формата сообщений для Anthropic API
            claude_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    # Claude использует system в начале, поэтому обрабатываем отдельно
                    system_message = msg["content"]
                else:
                    claude_messages.append({
                        "role": "user" if msg["role"] == "user" else "assistant",
                        "content": msg["content"]
                    })
            
            payload = {
                "model": "claude-3-opus-20240229",  # Используем Claude 3 Opus как резервную модель
                "messages": claude_messages,
                "system": system_message if 'system_message' in locals() else "",
                "temperature": 0.7,
                "max_tokens": 2000
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.anthropic.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60  # Увеличенный таймаут
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        api_stats["backup"]["success"] += 1
                        api_stats["backup"]["last_success"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        return data["content"]
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка резервного API (попытка {attempt+1}/{max_retries}): {response.status}, {error_text}")
                        api_stats["backup"]["failures"] += 1
                        
                        # Пауза перед повторной попыткой
                        await asyncio.sleep(1 * (attempt + 1))
        except Exception as e:
            logger.error(f"Исключение при запросе к резервному API (попытка {attempt+1}/{max_retries}): {e}")
            api_stats["backup"]["failures"] += 1
            
            # Пауза перед повторной попыткой
            await asyncio.sleep(1 * (attempt + 1))
    
    return None

async def start(update: Update, context: CallbackContext):
    """Обработчик команды /start"""
    user = update.effective_user
    user_id_str = str(user.id)
    app_state["active_users"].add(user_id_str)
    
    # Приветственное сообщение
    welcome_message = (
        f"👋 Привет, {user.first_name}!\n\n"
        f"Я - бот с мощным искусственным интеллектом, готовый ответить на твои вопросы.\n\n"
        f"Доступные команды:\n"
        f"• /models - выбрать модель ИИ\n"
        f"• /role - выбрать роль ассистента\n"
        f"• /style - выбрать стиль общения\n"
        f"• /language - выбрать язык ответов\n"
        f"• /stats - узнать статистику использования\n"
        f"• /plan - информация о лимитах и подписке\n"
        f"• /clear - очистить историю сообщений\n"
        f"• /help - показать справку\n"
        f"• /feedback - отправить отзыв\n\n"
    )
    
    if user.username == OWNER_USERNAME or user.username in get_vip_users():
        welcome_message += "🔑 У вас безлимитный доступ как у VIP-пользователя."
    else:
        # Проверка или создание записи для нового пользователя
        if user_id_str not in user_data:
            today = datetime.now().strftime("%Y-%m-%d")
            user_data[user_id_str] = {
                "date": today,
                "count": 0,
                "model": "llama4_maverick",
                "role": "assistant",
                "style": "balanced",
                "language": "auto",
                "history": [],
                "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_data()
        
        welcome_message += f"📝 У вас {DEFAULT_DAILY_LIMIT} бесплатных запросов в день. Для получения дополнительных возможностей введите /plan"
    
    # Создание кнопок быстрого доступа
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="quick_stats"),
         InlineKeyboardButton("⚙️ Настройки", callback_data="quick_settings")],
        [InlineKeyboardButton("❓ Помощь", callback_data="quick_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    
    # Логирование события
    logger.info(f"Пользователь {user.id} ({user.username or 'без username'}) запустил бота")

async def select_model(update: Update, context: CallbackContext):
    """Обработчик команды /models для выбора модели"""
    keyboard = []
    
    # Создание кнопок для каждой модели
    for model_id, model_info in AVAILABLE_MODELS.items():
        keyboard.append([InlineKeyboardButton(model_info["name"], callback_data=f"model_{model_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите модель ИИ для общения:", reply_markup=reply_markup)

async def select_role(update: Update, context: CallbackContext):
    """Обработчик команды /role для выбора роли"""
    keyboard = []
    
    # Создание кнопок для каждой роли
    for role_id, role_desc in AVAILABLE_ROLES.items():
        button_text = role_desc.split(":")[0] if ":" in role_desc else role_desc[:30] + "..."
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"role_{role_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите роль для ассистента:", reply_markup=reply_markup)

async def select_style(update: Update, context: CallbackContext):
    """Обработчик команды /style для выбора стиля общения"""
    keyboard = []
    
    # Создание кнопок для каждого стиля
    for style_id, style_desc in AVAILABLE_STYLES.items():
        keyboard.append([InlineKeyboardButton(style_desc, callback_data=f"style_{style_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите стиль общения:", reply_markup=reply_markup)

async def select_language(update: Update, context: CallbackContext):
    """Обработчик команды /language для выбора языка ответов"""
    keyboard = []
    
    # Создание кнопок для каждого языка
    for lang_id, lang_desc in AVAILABLE_LANGUAGES.items():
        keyboard.append([InlineKeyboardButton(lang_desc, callback_data=f"lang_{lang_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите язык ответов:", reply_markup=reply_markup)

async def clear_history(update: Update, context: CallbackContext):
    """Обработчик команды /clear для очистки истории сообщений"""
    user = update.effective_user
    user_id_str = str(user.id)
    
    if user_id_str in user_data:
        user_data[user_id_str]["history"] = []
        save_data()
        await update.message.reply_text("✅ История сообщений успешно очищена!")
    else:
        await update.message.reply_text("У вас пока нет истории сообщений.")

async def show_help(update: Update, context: CallbackContext):
    """Обработчик команды /help для отображения справки"""
    help_text = (
        "🤖 *Справка по использованию бота*\n\n"
        "*Основные команды:*\n"
        "• /start - запустить бота и увидеть приветственное сообщение\n"
        "• /models - выбрать модель ИИ для общения\n"
        "• /role - выбрать роль ассистента\n"
        "• /style - выбрать стиль общения\n"
        "• /language - выбрать язык ответов\n"
        "• /stats - узнать статистику использования\n"
        "• /plan - информация о лимитах и подписке\n"
        "• /clear - очистить историю сообщений\n\n"
        "*Как пользоваться ботом:*\n"
        "1. Просто отправьте сообщение, и бот ответит, используя выбранную модель, роль и стиль\n"
        "2. История сообщений сохраняется автоматически, что позволяет боту поддерживать контекст разговора\n"
        "3. При необходимости вы можете очистить историю командой /clear\n\n"
        "*Для владельцев VIP-аккаунтов:*\n"
        "• Безлимитное количество запросов\n"
        "• Доступ ко всем моделям ИИ\n"
        "• Расширенные возможности настройки\n\n"
        "По всем вопросам обращайтесь к @" + OWNER_USERNAME
    )
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def show_stats(update: Update, context: CallbackContext):
    """Обработчик команды /stats для отображения статистики"""
    user = update.effective_user
    user_id_str = str(user.id)
    
    if user_id_str not in user_data:
        await update.message.reply_text("У вас пока нет статистики использования.")
        return
    
    user_info = user_data[user_id_str]
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Сброс счетчика, если это новый день
    if user_info["date"] != today:
        user_info["date"] = today
        user_info["count"] = 0
        save_data()
    
    # Информация о выбранной модели
    model_name = AVAILABLE_MODELS[user_info["model"]]["name"]
    
    # Информация о выбранной роли
    role_desc = AVAILABLE_ROLES[user_info["role"]]
    role_name = role_desc.split(":")[0] if ":" in role_desc else role_desc[:30]
    
    # Информация о выбранном стиле
    style_name = AVAILABLE_STYLES[user_info["style"]]
    
    # Информация о языке ответов
    language_name = AVAILABLE_LANGUAGES.get(user_info.get("language", "auto"), "Автоопределение")
    
    # Количество оставшихся запросов
    if user.username == OWNER_USERNAME or user.username in get_vip_users():
        remaining = "∞"  # Бесконечность для VIP-пользователей
    else:
        remaining = DEFAULT_DAILY_LIMIT - user_info["count"]
        if remaining < 0:
            remaining = 0
    
    # Общее количество запросов
    total_messages = len(user_info.get("history", [])) // 2  # Делим на 2, т.к. история содержит и вопросы, и ответы
    
    # Дата первого и последнего использования
    first_seen = user_info.get("first_seen", "Неизвестно")
    last_activity = user_info.get("last_activity", "Неизвестно")
    
    stats_message = (
        f"📊 *Ваша статистика:*\n\n"
        f"👤 Пользователь: {user.first_name}\n"
        f"📆 Дата: {today}\n"
        f"🔢 Использовано запросов сегодня: {user_info['count']}\n"
        f"⏳ Осталось запросов: {remaining}\n"
        f"📝 Всего сообщений: {total_messages}\n"
        f"🕒 Первое использование: {first_seen}\n"
        f"🕒 Последняя активность: {last_activity}\n\n"
        f"🤖 Текущая модель: {model_name}\n"
        f"👑 Роль ассистента: {role_name}\n"
        f"💬 Стиль общения: {style_name}\n"
        f"🌐 Язык ответов: {language_name}\n"
    )
    
    # Кнопки для быстрого изменения настроек
    keyboard = [
        [InlineKeyboardButton("🔄 Изменить модель", callback_data="quick_model"),
         InlineKeyboardButton("👤 Изменить роль", callback_data="quick_role")],
        [InlineKeyboardButton("💬 Изменить стиль", callback_data="quick_style"),
         InlineKeyboardButton("🌐 Изменить язык", callback_data="quick_language")],
        [InlineKeyboardButton("🗑️ Очистить историю", callback_data="quick_clear")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(stats_message, parse_mode="Markdown", reply_markup=reply_markup)

async def show_plan(update: Update, context: CallbackContext):
    """Обработчик команды /plan для отображения информации о тарифе"""
    user = update.effective_user
    
    if user.username == OWNER_USERNAME:
        plan_message = (
            "🔑 *VIP-статус (Владелец)*\n\n"
            "У вас есть безлимитный доступ как у владельца бота.\n"
            "Вы можете отправлять неограниченное количество запросов и использовать все функции."
        )
    elif user.username in get_vip_users():
        plan_message = (
            "🔑 *VIP-статус*\n\n"
            "У вас есть безлимитный доступ как у VIP-пользователя.\n"
            "Вы можете отправлять неограниченное количество запросов и использовать все функции."
        )
    else:
        plan_message = (
            "📝 *Ваш текущий тариф: Базовый*\n\n"
            f"• {DEFAULT_DAILY_LIMIT} бесплатных запросов в день\n"
            "• Доступ ко всем моделям ИИ\n"
            "• Выбор роли и стиля общения\n\n"
            "💼 *Премиум тариф*\n\n"
            "• Безлимитные запросы\n"
            "• Приоритетная обработка сообщений\n"
            "• Расширенные возможности персонализации\n"
            "• Поддержка контекста длинных разговоров\n"
            "• Возможность использования бота в групповых чатах\n\n"
            "Для получения информации о премиум-тарифе свяжитесь с @" + OWNER_USERNAME
        )
        
        # Добавление кнопки для связи с владельцем
        keyboard = [[InlineKeyboardButton("💬 Связаться с владельцем", url=f"https://t.me/{OWNER_USERNAME}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(plan_message, parse_mode="Markdown", reply_markup=reply_markup)
        return
    
    await update.message.reply_text(plan_message, parse_mode="Markdown")

async def feedback(update: Update, context: CallbackContext):
    """Обработчик команды /feedback для отправки отзыва"""
    await update.message.reply_text(
        "📫 Чтобы отправить отзыв или сообщить о проблеме, напишите сообщение, начиная с /feedback, например:\n\n"
        "/feedback Мне очень нравится этот бот! Хотелось бы добавить..."
    )
    
    # Проверяем, есть ли текст после команды
    if context.args:
        feedback_text = " ".join(context.args)
        user = update.effective_user
        
        # Отправка отзыва владельцу бота
        feedback_message = (
            f"📬 *Новый отзыв*\n\n"
            f"От: {user.first_name} (@{user.username or 'без username'})\n"
            f"ID: {user.id}\n"
            f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Сообщение:\n{feedback_text}"
        )
        
        # Сохранение отзыва в файл
        try:
            with open("feedback.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {user.id} (@{user.username or 'без username'}): {feedback_text}\n")
        except Exception as e:
            logger.error(f"Ошибка при сохранении отзыва: {e}")
        
        logger.info(f"Получен отзыв от {user.id}: {feedback_text}")
        
        await update.message.reply_text("✅ Спасибо за ваш отзыв! Мы обязательно его рассмотрим.")

async def button_click(update: Update, context: CallbackContext):
    """Обработчик нажатий на инлайн-кнопки"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id_str = str(user.id)
    
    if user_id_str not in user_data:
        today = datetime.now().strftime("%Y-%m-%d")
        user_data[user_id_str] = {
            "date": today,
            "count": 0,
            "model": "llama4_maverick",
            "role": "assistant",
            "style": "balanced",
            "language": "auto",
            "history": [],
            "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    data = query.data
    
    if data.startswith("model_"):
        model_id = data.split("_")[1]
        if model_id in AVAILABLE_MODELS:
            user_data[user_id_str]["model"] = model_id
            save_data()
            await query.edit_message_text(f"✅ Выбрана модель: {AVAILABLE_MODELS[model_id]['name']}")
    
    elif data.startswith("role_"):
        role_id = data.split("_")[1]
        if role_id in AVAILABLE_ROLES:
            user_data[user_id_str]["role"] = role_id
            save_data()
            role_desc = AVAILABLE_ROLES[role_id]
            role_name = role_desc.split(":")[0] if ":" in role_desc else role_desc[:30]
            await query.edit_message_text(f"✅ Выбрана роль: {role_name}")
    
    elif data.startswith("style_"):
        style_id = data.split("_")[1]
        if style_id in AVAILABLE_STYLES:
            user_data[user_id_str]["style"] = style_id
            save_data()
            await query.edit_message_text(f"✅ Выбран стиль общения: {AVAILABLE_STYLES[style_id]}")
    
    elif data.startswith("lang_"):
        lang_id = data.split("_")[1]
        if lang_id in AVAILABLE_LANGUAGES:
            user_data[user_id_str]["language"] = lang_id
            save_data()
            await query.edit_message_text(f"✅ Выбран язык ответов: {AVAILABLE_LANGUAGES[lang_id]}")
    
    elif data == "quick_stats":
        await show_stats(query, context)
    elif data == "quick_settings":
        await query.edit_message_text("⚙️ Выберите настройку, которую хотите изменить:")
        keyboard = [
            [InlineKeyboardButton("🤖 Модель", callback_data="quick_model"),
             InlineKeyboardButton("👑 Роль", callback_data="quick_role")],
            [InlineKeyboardButton("💬 Стиль", callback_data="quick_style"),
             InlineKeyboardButton("🌐 Язык", callback_data="quick_language")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    elif data == "quick_help":
        await show_help(query, context)
    elif data == "quick_model":
        await select_model(query, context)
    elif data == "quick_role":
        await select_role(query, context)
    elif data == "quick_style":
        await select_style(query, context)
    elif data == "quick_language":
        await select_language(query, context)
    elif data == "quick_clear":
        if user_id_str in user_data:
            user_data[user_id_str]["history"] = []
            save_data()
            await query.edit_message_text("✅ История сообщений успешно очищена!")

async def handle_message(update: Update, context: CallbackContext):
    """Обработчик всех входящих сообщений"""
    user = update.effective_user
    user_id_str = str(user.id)
    app_state["active_users"].add(user_id_str)
    app_state["messages_processed"] += 1
    
    # Проверка лимита
    has_limit, remaining = await check_user_limit(user.id, user.username)
    
    if not has_limit:
        keyboard = [[InlineKeyboardButton("💬 Связаться с владельцем", url=f"https://t.me/{OWNER_USERNAME}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ Вы использовали все доступные запросы на сегодня.\n\n"
            "Лимит обновится завтра или вы можете узнать о премиум-тарифе, введя /plan",
            reply_markup=reply_markup
        )
        return
    
    # Отправка уведомления о том, что бот печатает
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Получение текста сообщения
    message_text = update.message.text
    
    # Получение данных пользователя
    if user_id_str not in user_data:
        today = datetime.now().strftime("%Y-%m-%d")
        user_data[user_id_str] = {
            "date": today,
            "count": 1,  # Сразу считаем первый запрос
            "model": "llama4_maverick",
            "role": "assistant",
            "style": "balanced",
            "language": "auto",
            "history": [],
            "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    else:
        user_data[user_id_str]["last_activity"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Получение выбранной модели, роли и стиля
    model_id = user_data[user_id_str]["model"]
    role = user_data[user_id_str]["role"]
    style = user_data[user_id_str]["style"]
    language = user_data[user_id_str].get("language", "auto")
    
    # Добавление сообщения пользователя в историю
    user_data[user_id_str]["history"].append({"role": "user", "content": message_text})
    
    try:
        # Отправка запроса к модели ИИ
        response = await get_ai_response(
            message_text,
            model_id,
            role,
            style,
            language,
            user_data[user_id_str]["history"],
            user.first_name
        )
        
        # Добавление ответа ассистента в историю
        user_data[user_id_str]["history"].append({"role": "assistant", "content": response})
        
        # Ограничение истории до 20 сообщений, чтобы не перегружать память
        if len(user_data[user_id_str]["history"]) > 20:
            user_data[user_id_str]["history"] = user_data[user_id_str]["history"][-20:]
        
        # Сохранение данных
        save_data()
        
        # Отправка ответа пользователю
        if user.username != OWNER_USERNAME and user.username not in get_vip_users():
            footer = f"\n\n[Осталось запросов: {remaining}]"
        else:
            footer = "\n\n[Безлимитный режим]"
        
        # Разделение длинных сообщений
        max_length = 4000  # Максимальная длина сообщения в Telegram
        if len(response) + len(footer) <= max_length:
            await update.message.reply_text(response + footer)
        else:
            # Разделение длинного сообщения на части
            parts = [response[i:i+max_length] for i in range(0, len(response), max_length)]
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    await update.message.reply_text(part + footer)
                else:
                    await update.message.reply_text(part)
    except Exception as e:
        error_message = f"Произошла ошибка при обработке запроса: {str(e)}"
        logger.error(error_message)
        app_state["last_error"] = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: {str(e)}"
        traceback.print_exc()
        
        await update.message.reply_text(
            "😔 Извините, произошла ошибка при обработке вашего запроса. "
            "Пожалуйста, попробуйте еще раз позже или обратитесь к администратору."
        )

def get_vip_users():
    """Получение списка VIP-пользователей (кроме владельца)"""
    vip_users = []
    try:
        if os.path.exists("vip_users.txt"):
            with open("vip_users.txt", "r", encoding="utf-8") as f:
                vip_users = [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"Ошибка при загрузке списка VIP-пользователей: {e}")
    
    return vip_users

def main():
    """Основная функция для запуска бота"""
    # Регистрация обработчиков сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Загрузка данных
    load_data()
    
    # Создание приложения Telegram
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("models", select_model))
    application.add_handler(CommandHandler("role", select_role))
    application.add_handler(CommandHandler("style", select_style))
    application.add_handler(CommandHandler("language", select_language))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CommandHandler("plan", show_plan))
    application.add_handler(CommandHandler("feedback", feedback))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(CommandHandler("help", show_help))
    
    # Регистрация обработчика инлайн-кнопок
    application.add_handler(CallbackQueryHandler(button_click))
    
    # Регистрация обработчика сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Создание периодической задачи для резервного копирования данных
    async def backup_job(context: CallbackContext):
        backup_data()
    
    # Запуск бота
    logger.info("Запуск бота...")
    
    try:
        # Запуск периодической задачи для резервного копирования (каждые 6 часов)
        application.job_queue.run_repeating(backup_job, interval=21600, first=10800)
        
        # Запуск бота в режиме опроса
        application.run_polling()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        traceback.print_exc()
    finally:
        # Сохранение данных при завершении
        save_data()
        backup_data()

if __name__ == "__main__":
    main()
