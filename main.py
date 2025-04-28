import logging
import os
import json
import aiohttp
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
DATA_FILE = "bot_data.json"  # Файл для хранения данных пользователей

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
    "bespoke_stratos": {"name": "Bespoke Stratos 32B", "id": "bespoke-stratos-32b"}
}

# Доступные роли для бота
AVAILABLE_ROLES = {
    "assistant": "Универсальный ассистент, готовый помочь с любыми вопросами.",
    "teacher": "Ассистент-преподаватель: объясняет материал чётко и понятно, приводя примеры.",
    "programmer": "Ассистент-программист: объясняет технические аспекты, делая акцент на оптимизации и примерах кода.",
    "marketer": "Ассистент-маркетолог: предлагает маркетинговые стратегии, идеи и анализирует задачи.",
    "psychologist": "Ассистент-психолог: даёт рекомендации с учётом эмпатии и профессиональных знаний.",
    "analyst": "Ассистент-аналитик: строит логические выводы и структурирует информацию."
}

# Стили общения
AVAILABLE_STYLES = {
    "balanced": "Сбалансированный (обычный стиль общения)",
    "concise": "Краткий (короткие и четкие ответы)",
    "detailed": "Подробный (развернутые и детальные ответы)"
}

# Данные пользователей
user_data = {}

def load_data():
    """Загрузка данных пользователей из файла"""
    global user_data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                user_data = json.load(f)
            logger.info("Данные пользователей успешно загружены")
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных: {e}")
        user_data = {}

def save_data():
    """Сохранение данных пользователей в файл"""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
        logger.info("Данные пользователей успешно сохранены")
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {e}")

async def check_user_limit(user_id, username):
    """Проверка лимита запросов пользователя"""
    # Владелец бота имеет безлимитный доступ
    if username == OWNER_USERNAME:
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
            "history": []  # История сообщений
        }
    
    # Сброс счетчика, если это новый день
    if user_data[user_id_str]["date"] != today:
        user_data[user_id_str]["date"] = today
        user_data[user_id_str]["count"] = 0
    
    # Проверка лимита
    if user_data[user_id_str]["count"] < DEFAULT_DAILY_LIMIT:
        user_data[user_id_str]["count"] += 1
        save_data()
        remaining = DEFAULT_DAILY_LIMIT - user_data[user_id_str]["count"]
        return True, remaining
    
    return False, 0

async def get_ai_response(prompt, model_id, role, style, history=None):
    """Получение ответа от модели через io.net API"""
    if history is None:
        history = []
    
    # Формирование системного промпта на основе роли и стиля
    system_prompt = f"Ты - {AVAILABLE_ROLES[role]}"
    
    if style == "concise":
        system_prompt += " Отвечай кратко и по существу, избегая длинных объяснений."
    elif style == "detailed":
        system_prompt += " Давай подробные и развернутые ответы с детальными объяснениями."
    
    # Формирование сообщений для API
    messages = [{"role": "system", "content": system_prompt}]
    
    # Добавление истории сообщений (последние 10 сообщений)
    for msg in history[-10:]:
        messages.append(msg)
    
    # Добавление текущего сообщения пользователя
    messages.append({"role": "user", "content": prompt})
    
    async with aiohttp.ClientSession() as session:
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {IONET_API_KEY}"
            }
            
            payload = {
                "model": AVAILABLE_MODELS[model_id]["id"],
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 2000
            }
            
            async with session.post(
                "https://api.io.net/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка API: {response.status}, {error_text}")
                    return f"Произошла ошибка при запросе к API (статус {response.status}). Пожалуйста, попробуйте позже."
        except Exception as e:
            logger.error(f"Ошибка при запросе к API: {e}")
            return "Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."

async def start(update: Update, context: CallbackContext):
    """Обработчик команды /start"""
    user = update.effective_user
    user_id_str = str(user.id)
    
    # Приветственное сообщение
    welcome_message = (
        f"👋 Привет, {user.first_name}!\n\n"
        f"Я - бот с мощным искусственным интеллектом, готовый ответить на твои вопросы.\n\n"
        f"Доступные команды:\n"
        f"• /models - выбрать модель ИИ\n"
        f"• /role - выбрать роль ассистента\n"
        f"• /style - выбрать стиль общения\n"
        f"• /stats - узнать статистику использования\n"
        f"• /plan - информация о лимитах и подписке\n"
        f"• /feedback - отправить отзыв\n\n"
    )
    
    if user.username == OWNER_USERNAME:
        welcome_message += "🔑 У вас безлимитный доступ как у владельца бота."
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
                "history": []
            }
            save_data()
        
        welcome_message += f"📝 У вас {DEFAULT_DAILY_LIMIT} бесплатных запросов в день. Для получения дополнительных возможностей введите /plan"
    
    await update.message.reply_text(welcome_message)

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
    
    # Количество оставшихся запросов
    if user.username == OWNER_USERNAME:
        remaining = "∞"  # Бесконечность для владельца
    else:
        remaining = DEFAULT_DAILY_LIMIT - user_info["count"]
        if remaining < 0:
            remaining = 0
    
    stats_message = (
        f"📊 *Ваша статистика:*\n\n"
        f"👤 Пользователь: {user.first_name}\n"
        f"📆 Дата: {today}\n"
        f"🔢 Использовано запросов сегодня: {user_info['count']}\n"
        f"⏳ Осталось запросов: {remaining}\n\n"
        f"🤖 Текущая модель: {model_name}\n"
        f"👑 Роль ассистента: {role_name}\n"
        f"💬 Стиль общения: {style_name}\n"
    )
    
    await update.message.reply_text(stats_message, parse_mode="Markdown")

async def show_plan(update: Update, context: CallbackContext):
    """Обработчик команды /plan для отображения информации о тарифе"""
    user = update.effective_user
    
    if user.username == OWNER_USERNAME:
        plan_message = (
            "🔑 *VIP-статус*\n\n"
            "У вас есть безлимитный доступ как у владельца бота.\n"
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
            "• Расширенные возможности персонализации\n\n"
            "Для получения информации о премиум-тарифе свяжитесь с @" + OWNER_USERNAME
        )
    
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
            f"ID: {user.id}\n\n"
            f"Сообщение:\n{feedback_text}"
        )
        
        # Здесь можно добавить код для отправки отзыва владельцу
        # Например, сохранение в файл или отправка сообщения
        logger.info(f"Получен отзыв от {user.id}: {feedback_text}")
        
        await update.message.reply_text("✅ Спасибо за ваш отзыв! Мы обязательно его рассмотрим.")

async def button_handler(update: Update, context: CallbackContext):
    """Обработчик нажатий на инлайн-кнопки"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id_str = str(user.id)
    data = query.data
    
    if user_id_str not in user_data:
        today = datetime.now().strftime("%Y-%m-%d")
        user_data[user_id_str] = {
            "date": today,
            "count": 0,
            "model": "llama4_maverick",
            "role": "assistant",
            "style": "balanced",
            "history": []
        }
    
    # Обработка выбора модели
    if data.startswith("model_"):
        model_id = data.split("_")[1]
        if model_id in AVAILABLE_MODELS:
            user_data[user_id_str]["model"] = model_id
            save_data()
            await query.edit_message_text(f"✅ Выбрана модель: {AVAILABLE_MODELS[model_id]['name']}")
    
    # Обработка выбора роли
    elif data.startswith("role_"):
        role_id = data.split("_")[1]
        if role_id in AVAILABLE_ROLES:
            user_data[user_id_str]["role"] = role_id
            save_data()
            role_desc = AVAILABLE_ROLES[role_id]
            role_name = role_desc.split(":")[0] if ":" in role_desc else role_desc[:30]
            await query.edit_message_text(f"✅ Выбрана роль: {role_name}")
    
    # Обработка выбора стиля
    elif data.startswith("style_"):
        style_id = data.split("_")[1]
        if style_id in AVAILABLE_STYLES:
            user_data[user_id_str]["style"] = style_id
            save_data()
            await query.edit_message_text(f"✅ Выбран стиль общения: {AVAILABLE_STYLES[style_id]}")

async def handle_message(update: Update, context: CallbackContext):
    """Обработчик всех входящих сообщений"""
    # Проверка, не является ли сообщение командой обратной связи
    if update.message.text and update.message.text.startswith("/feedback "):
        # Передаем управление обработчику обратной связи
        context.args = update.message.text.split()[1:]
        await feedback(update, context)
        return
    
    user = update.effective_user
    user_id_str = str(user.id)
    
    # Проверка лимита
    has_limit, remaining = await check_user_limit(user.id, user.username)
    
    if not has_limit:
        await update.message.reply_text(
            "⚠️ Вы использовали все доступные запросы на сегодня.\n\n"
            "Лимит обновится завтра или вы можете узнать о премиум-тарифе, введя /plan"
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
            "history": []
        }
    
    # Получение выбранной модели, роли и стиля
    model_id = user_data[user_id_str]["model"]
    role = user_data[user_id_str]["role"]
    style = user_data[user_id_str]["style"]
    
    # Добавление сообщения пользователя в историю
    user_data[user_id_str]["history"].append({"role": "user", "content": message_text})
    
    # Отправка запроса к модели ИИ
    response = await get_ai_response(
        message_text,
        model_id,
        role,
        style,
        user_data[user_id_str]["history"]
    )
    
    # Добавление ответа ассистента в историю
    user_data[user_id_str]["history"].append({"role": "assistant", "content": response})
    
    # Ограничение истории до 20 сообщений, чтобы не перегружать память
    if len(user_data[user_id_str]["history"]) > 20:
        user_data[user_id_str]["history"] = user_data[user_id_str]["history"][-20:]
    
    # Сохранение данных
    save_data()
    
    # Отправка ответа пользователю
    if user.username != OWNER_USERNAME:
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

def main():
    """Основная функция для запуска бота"""
    # Загрузка данных
    load_data()
    
    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("models", select_model))
    application.add_handler(CommandHandler("role", select_role))
    application.add_handler(CommandHandler("style", select_style))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CommandHandler("plan", show_plan))
    application.add_handler(CommandHandler("feedback", feedback))
    
    # Регистрация обработчика инлайн-кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Регистрация обработчика сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запуск бота
    application.run_polling()
    
    # Сохранение данных при завершении
    save_data()

if __name__ == "__main__":
    main()
