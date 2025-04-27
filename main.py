#!/usr/bin/env python3
"""
OpenRouter Telegram Bot - A powerful Telegram bot that integrates with OpenRouter API
to provide AI-powered conversations with features like message history, voice transcription,
document processing, and more.
"""

import asyncio
import aiohttp
import json
import logging
import os
import time
import tempfile
import io
import datetime
from typing import Dict, List, Optional, Any, Union
from collections import deque, defaultdict
import re
import base64
import uuid

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    FSInputFile, BufferedInputFile
)
from aiogram.filters import Command, CommandStart
from aiogram.utils.chat_action import ChatActionMiddleware
from aiogram.utils.markdown import hbold, hcode, hpre, hide_link, hitalic
from aiogram.enums import ParseMode, ChatAction
from aiogram.exceptions import TelegramAPIError
from aiogram.client.default import DefaultBotProperties

import speech_recognition as sr
from pydub import AudioSegment
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Bot configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEYS = os.getenv("OPENROUTER_API_KEYS", "").split(",")
OPENROUTER_API_URL = os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "gpt-3.5-turbo")
BOT_ADMIN_IDS = list(map(int, os.getenv("BOT_ADMIN_IDS", "").split(","))) if os.getenv("BOT_ADMIN_IDS") else []
ALLOWED_USER_IDS = os.getenv("ALLOWED_USER_IDS", "*")  # "*" means everyone is allowed
MAX_MESSAGES_PER_DAY = int(os.getenv("MAX_MESSAGES_PER_DAY", "50"))
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "50"))
HISTORY_EXPIRATION_HOURS = int(os.getenv("HISTORY_EXPIRATION_HOURS", "24"))
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful assistant.")

# Initialize the router
router = Router()

# State storage for users
class UserState:
    def __init__(self):
        # Message history: deque of (role, content, timestamp) tuples
        self.history = deque(maxlen=MAX_HISTORY_MESSAGES)
        # Daily usage tracking
        self.daily_usage = 0
        self.usage_reset_date = datetime.datetime.now().date()
        # Current API key index
        self.current_api_key_index = 0
        # Last interaction time
        self.last_interaction = datetime.datetime.now()

# Global state
user_states: Dict[int, UserState] = {}
api_key_failure_count: Dict[str, int] = {key: 0 for key in OPENROUTER_API_KEYS}

# Helper Functions
def get_user_state(user_id: int) -> UserState:
    """Get or create user state"""
    if user_id not in user_states:
        user_states[user_id] = UserState()
    
    # Check if we need to reset daily usage
    current_date = datetime.datetime.now().date()
    if user_states[user_id].usage_reset_date != current_date:
        user_states[user_id].daily_usage = 0
        user_states[user_id].usage_reset_date = current_date
    
    # Update last interaction time
    user_states[user_id].last_interaction = datetime.datetime.now()
    
    return user_states[user_id]

def is_user_allowed(user_id: int) -> bool:
    """Check if user is allowed to use the bot"""
    if ALLOWED_USER_IDS == "*":
        return True
    
    if str(user_id) in ALLOWED_USER_IDS.split(","):
        return True
    
    if user_id in BOT_ADMIN_IDS:
        return True
    
    return False

def get_next_api_key(user_id: int) -> str:
    """Get the next available API key"""
    if not OPENROUTER_API_KEYS:
        logger.error("No API keys configured!")
        return ""
    
    user_state = get_user_state(user_id)
    
    # Try the current key first
    current_index = user_state.current_api_key_index
    if current_index < len(OPENROUTER_API_KEYS) and api_key_failure_count[OPENROUTER_API_KEYS[current_index]] < 3:
        return OPENROUTER_API_KEYS[current_index]
    
    # Find the next key with fewer than 3 failures
    for i in range(len(OPENROUTER_API_KEYS)):
        if api_key_failure_count[OPENROUTER_API_KEYS[i]] < 3:
            user_state.current_api_key_index = i
            return OPENROUTER_API_KEYS[i]
    
    # If all keys have failed, reset counters and try the first one
    for key in OPENROUTER_API_KEYS:
        api_key_failure_count[key] = 0
    
    user_state.current_api_key_index = 0
    return OPENROUTER_API_KEYS[0]

def clean_expired_history():
    """Clean expired history for all users"""
    now = datetime.datetime.now()
    for user_id, state in user_states.items():
        # Remove messages older than HISTORY_EXPIRATION_HOURS
        expiration_time = now - datetime.timedelta(hours=HISTORY_EXPIRATION_HOURS)
        state.history = deque(
            [(role, content, timestamp) for role, content, timestamp in state.history if timestamp > expiration_time],
            maxlen=MAX_HISTORY_MESSAGES
        )
        
        # Reset conversation if no activity for HISTORY_EXPIRATION_HOURS
        if state.last_interaction < expiration_time:
            state.history.clear()

async def transcribe_voice(voice_file_path: str) -> str:
    """Transcribe voice message to text"""
    try:
        # Convert the voice message to WAV format
        audio = AudioSegment.from_file(voice_file_path)
        wav_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        audio.export(wav_file.name, format="wav")
        wav_file.close()
        
        # Use speech recognition to transcribe
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_file.name) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
        
        # Clean up temporary file
        os.unlink(wav_file.name)
        
        return text
    except Exception as e:
        logger.error(f"Error transcribing voice: {e}")
        return f"[Voice transcription failed: {str(e)}]"

async def extract_document_text(file_path: str, file_name: str) -> str:
    """Extract text from document"""
    try:
        # Simple text extraction based on file extension
        if file_name.endswith(('.txt', '.md', '.py', '.js', '.html', '.css', '.json')):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                return file.read()
        else:
            return f"[Document type not supported for text extraction: {file_name}]"
    except Exception as e:
        logger.error(f"Error extracting document text: {e}")
        return f"[Document text extraction failed: {str(e)}]"

async def send_chat_action(bot: Bot, chat_id: int, action: str, interval: float = 3.0):
    """Send chat action repeatedly"""
    try:
        await bot.send_chat_action(chat_id=chat_id, action=action)
    except Exception as e:
        logger.error(f"Error sending chat action: {e}")

async def call_openrouter_api(
    user_id: int, 
    messages: List[Dict[str, str]],
    stream: bool = False
) -> Dict[str, Any]:
    """Call OpenRouter API"""
    api_key = get_next_api_key(user_id)
    if not api_key:
        return {"error": "No API keys available"}
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "stream": stream
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPENROUTER_API_URL, 
                headers=headers, 
                json=data,
                timeout=60
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"API error: {response.status}, {error_text}")
                    api_key_failure_count[api_key] += 1
                    return {"error": f"API error: {response.status}"}
                
                if stream:
                    return {"stream": response}
                else:
                    result = await response.json()
                    return result
    except Exception as e:
        logger.error(f"API call error: {e}")
        api_key_failure_count[api_key] += 1
        return {"error": f"API call failed: {str(e)}"}

async def get_ai_response(user_id: int, input_text: str) -> str:
    """Get AI response from OpenRouter"""
    user_state = get_user_state(user_id)
    
    # Build message history
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, content, _ in user_state.history:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": input_text})
    
    # Call API
    response = await call_openrouter_api(user_id, messages)
    
    # Handle errors
    if "error" in response:
        return f"⚠️ {response['error']}"
    
    try:
        result = response["choices"][0]["message"]["content"]
        
        # Add to history
        user_state.history.append(("user", input_text, datetime.datetime.now()))
        user_state.history.append(("assistant", result, datetime.datetime.now()))
        
        # Increment usage count
        user_state.daily_usage += 1
        
        return result
    except Exception as e:
        logger.error(f"Error parsing API response: {e}")
        return f"⚠️ Failed to parse API response: {str(e)}"

async def stream_ai_response(user_id: int, input_text: str, message: Message) -> None:
    """Stream AI response from OpenRouter"""
    user_state = get_user_state(user_id)
    
    # Build message history
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, content, _ in user_state.history:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": input_text})
    
    # Call API with streaming
    response = await call_openrouter_api(user_id, messages, stream=True)
    
    # Handle errors
    if "error" in response:
        await message.answer(f"⚠️ {response['error']}")
        return
    
    try:
        # Initial empty message
        response_message = await message.answer("...")
        collected_message = ""
        buffer = ""
        last_update_time = time.time()
        
        async for line in response["stream"].content:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                if line.strip() == 'data: [DONE]':
                    break
                
                try:
                    json_str = line[6:]  # Remove 'data: ' prefix
                    if not json_str.strip():
                        continue
                    
                    chunk = json.loads(json_str)
                    if 'choices' in chunk and len(chunk['choices']) > 0:
                        delta = chunk['choices'][0].get('delta', {})
                        if 'content' in delta:
                            content = delta['content']
                            buffer += content
                            collected_message += content
                            
                            # Update message every 1 second or when buffer reaches 100 chars
                            current_time = time.time()
                            if current_time - last_update_time > 1 or len(buffer) > 100:
                                try:
                                    await response_message.edit_text(
                                        collected_message, 
                                        parse_mode=ParseMode.MARKDOWN
                                    )
                                except TelegramAPIError:
                                    # If Markdown parsing fails, try without it
                                    await response_message.edit_text(collected_message)
                                buffer = ""
                                last_update_time = current_time
                except json.JSONDecodeError:
                    continue
        
        # Final update with complete message
        if buffer:
            try:
                await response_message.edit_text(
                    collected_message, 
                    parse_mode=ParseMode.MARKDOWN
                )
            except TelegramAPIError:
                await response_message.edit_text(collected_message)
        
        # Add to history
        user_state.history.append(("user", input_text, datetime.datetime.now()))
        user_state.history.append(("assistant", collected_message, datetime.datetime.now()))
        
        # Increment usage count
        user_state.daily_usage += 1
    
    except Exception as e:
        logger.error(f"Error streaming API response: {e}")
        await message.answer(f"⚠️ Failed to stream response: {str(e)}")

# Command Handlers
@router.message(CommandStart())
async def command_start(message: Message, bot: Bot):
    """Handle /start command"""
    if not is_user_allowed(message.from_user.id):
        await message.answer("⚠️ You're not authorized to use this bot.")
        return
    
    user_state = get_user_state(message.from_user.id)
    
    # Welcome message with markdown
    welcome_text = (
        f"👋 Welcome to OpenRouter AI Bot!\n\n"
        f"I'm powered by {hbold(OPENROUTER_MODEL)} through OpenRouter API.\n\n"
        f"You can simply send me a message and I'll respond with an AI-generated answer. "
        f"You can also send me voice messages or documents, and I'll process them.\n\n"
        f"Available commands:\n"
        f"• /start - Show this welcome message\n"
        f"• /help - Show help information\n"
        f"• /reset - Reset conversation history\n"
        f"• /menu - Show main menu\n\n"
        f"You have {hbold(MAX_MESSAGES_PER_DAY - user_state.daily_usage)} messages left today."
    )
    
    # Create keyboard
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Reset Conversation"), KeyboardButton(text="❓ Help")],
            [KeyboardButton(text="📊 Usage Stats"), KeyboardButton(text="🧩 Menu")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

@router.message(Command("help"))
async def command_help(message: Message):
    """Handle /help command"""
    if not is_user_allowed(message.from_user.id):
        await message.answer("⚠️ You're not authorized to use this bot.")
        return
    
    help_text = (
        f"🤖 {hbold('OpenRouter AI Bot Help')}\n\n"
        f"This bot allows you to chat with OpenRouter AI models.\n\n"
        f"{hbold('Features:')}\n"
        f"• Chat with AI assistant\n"
        f"• Process voice messages (speech to text)\n"
        f"• Extract text from documents\n"
        f"• Conversation memory (up to {MAX_HISTORY_MESSAGES} messages or {HISTORY_EXPIRATION_HOURS} hours)\n\n"
        f"{hbold('Commands:')}\n"
        f"• /start - Start the bot and show welcome message\n"
        f"• /help - Show this help message\n"
        f"• /reset - Reset your conversation history\n"
        f"• /menu - Show main menu with options\n\n"
        f"{hbold('Usage Limits:')}\n"
        f"• {MAX_MESSAGES_PER_DAY} messages per day\n"
        f"• Conversation history resets after {HISTORY_EXPIRATION_HOURS} hours of inactivity\n\n"
        f"For issues or feedback, please contact the bot administrator."
    )
    
    await message.answer(help_text, parse_mode=ParseMode.HTML)

@router.message(Command("reset"))
async def command_reset(message: Message):
    """Handle /reset command"""
    if not is_user_allowed(message.from_user.id):
        await message.answer("⚠️ You're not authorized to use this bot.")
        return
    
    user_state = get_user_state(message.from_user.id)
    user_state.history.clear()
    
    await message.answer("🔄 Conversation history has been reset.")

@router.message(Command("menu"))
async def command_menu(message: Message):
    """Handle /menu command"""
    if not is_user_allowed(message.from_user.id):
        await message.answer("⚠️ You're not authorized to use this bot.")
        return
    
    # Create inline keyboard
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Reset Conversation", callback_data="reset_conversation")],
            [InlineKeyboardButton(text="📊 Usage Statistics", callback_data="usage_stats")],
            [InlineKeyboardButton(text="ℹ️ About", callback_data="about")],
        ]
    )
    
    await message.answer("🧩 Main Menu:", reply_markup=keyboard)

# Callback Handlers
@router.callback_query(F.data == "reset_conversation")
async def callback_reset(callback: CallbackQuery):
    """Handle reset conversation callback"""
    if not is_user_allowed(callback.from_user.id):
        await callback.answer("⚠️ You're not authorized to use this bot.")
        return
    
    user_state = get_user_state(callback.from_user.id)
    user_state.history.clear()
    
    await callback.answer("Conversation history has been reset.")
    await callback.message.edit_text("🔄 Conversation history has been reset.")

@router.callback_query(F.data == "usage_stats")
async def callback_stats(callback: CallbackQuery):
    """Handle usage statistics callback"""
    if not is_user_allowed(callback.from_user.id):
        await callback.answer("⚠️ You're not authorized to use this bot.")
        return
    
    user_state = get_user_state(callback.from_user.id)
    
    stats_text = (
        f"📊 {hbold('Usage Statistics')}\n\n"
        f"Messages used today: {hbold(user_state.daily_usage)}/{hbold(MAX_MESSAGES_PER_DAY)}\n"
        f"Remaining today: {hbold(MAX_MESSAGES_PER_DAY - user_state.daily_usage)}\n"
        f"History message count: {hbold(len(user_state.history))}/{hbold(MAX_HISTORY_MESSAGES)}\n"
        f"Reset date: {hbold(user_state.usage_reset_date.strftime('%Y-%m-%d'))}"
    )
    
    await callback.answer()
    await callback.message.edit_text(stats_text, parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "about")
async def callback_about(callback: CallbackQuery):
    """Handle about callback"""
    if not is_user_allowed(callback.from_user.id):
        await callback.answer("⚠️ You're not authorized to use this bot.")
        return
    
    about_text = (
        f"ℹ️ {hbold('About OpenRouter AI Bot')}\n\n"
        f"This bot uses the OpenRouter API to provide access to various AI models.\n\n"
        f"Current model: {hbold(OPENROUTER_MODEL)}\n"
        f"Max history: {hbold(MAX_HISTORY_MESSAGES)} messages or {hbold(HISTORY_EXPIRATION_HOURS)} hours\n"
        f"Daily message limit: {hbold(MAX_MESSAGES_PER_DAY)} messages\n\n"
        f"Built with aiogram 3.x and Python 3.11+\n"
        f"Version: 1.0.0"
    )
    
    await callback.answer()
    await callback.message.edit_text(about_text, parse_mode=ParseMode.HTML)

# Message Handlers
@router.message(F.text == "🔄 Reset Conversation")
async def reset_button_handler(message: Message):
    """Handle reset conversation button"""
    if not is_user_allowed(message.from_user.id):
        await message.answer("⚠️ You're not authorized to use this bot.")
        return
    
    user_state = get_user_state(message.from_user.id)
    user_state.history.clear()
    
    await message.answer("🔄 Conversation history has been reset.")

@router.message(F.text == "❓ Help")
async def help_button_handler(message: Message):
    """Handle help button"""
    await command_help(message)

@router.message(F.text == "📊 Usage Stats")
async def stats_button_handler(message: Message):
    """Handle usage stats button"""
    if not is_user_allowed(message.from_user.id):
        await message.answer("⚠️ You're not authorized to use this bot.")
        return
    
    user_state = get_user_state(message.from_user.id)
    
    stats_text = (
        f"📊 {hbold('Usage Statistics')}\n\n"
        f"Messages used today: {hbold(user_state.daily_usage)}/{hbold(MAX_MESSAGES_PER_DAY)}\n"
        f"Remaining today: {hbold(MAX_MESSAGES_PER_DAY - user_state.daily_usage)}\n"
        f"History message count: {hbold(len(user_state.history))}/{hbold(MAX_HISTORY_MESSAGES)}\n"
        f"Reset date: {hbold(user_state.usage_reset_date.strftime('%Y-%m-%d'))}"
    )
    
    await message.answer(stats_text, parse_mode=ParseMode.HTML)

@router.message(F.text == "🧩 Menu")
async def menu_button_handler(message: Message):
    """Handle menu button"""
    await command_menu(message)

@router.message(F.voice)
async def voice_message_handler(message: Message, bot: Bot):
    """Handle voice messages"""
    if not is_user_allowed(message.from_user.id):
        await message.answer("⚠️ You're not authorized to use this bot.")
        return
    
    user_state = get_user_state(message.from_user.id)
    
    # Check if user has reached daily limit
    if user_state.daily_usage >= MAX_MESSAGES_PER_DAY:
        await message.answer(f"⚠️ You've reached your daily limit of {MAX_MESSAGES_PER_DAY} messages. Please try again tomorrow.")
        return
    
    # Send typing indicator while processing
    action_task = asyncio.create_task(
        send_chat_action(bot, message.chat.id, ChatAction.TYPING.value, 10.0)
    )
    
    try:
        # Download voice file
        voice_file = await bot.get_file(message.voice.file_id)
        voice_data = io.BytesIO()
        await bot.download_file(voice_file.file_path, voice_data)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
            temp_file.write(voice_data.getvalue())
            voice_file_path = temp_file.name
        
        # Transcribe voice to text
        transcribed_text = await transcribe_voice(voice_file_path)
        
        # Clean up temporary file
        os.unlink(voice_file_path)
        
        # Send transcription
        await message.reply(f"🎤 Transcription: {transcribed_text}")
        
        # Get AI response
        await stream_ai_response(message.from_user.id, transcribed_text, message)
    
    except Exception as e:
        logger.error(f"Error processing voice message: {e}")
        await message.reply(f"⚠️ Error processing voice message: {str(e)}")
    
    finally:
        # Cancel typing indicator
        action_task.cancel()

@router.message(F.document)
async def document_handler(message: Message, bot: Bot):
    """Handle document messages"""
    if not is_user_allowed(message.from_user.id):
        await message.answer("⚠️ You're not authorized to use this bot.")
        return
    
    user_state = get_user_state(message.from_user.id)
    
    # Check if user has reached daily limit
    if user_state.daily_usage >= MAX_MESSAGES_PER_DAY:
        await message.answer(f"⚠️ You've reached your daily limit of {MAX_MESSAGES_PER_DAY} messages. Please try again tomorrow.")
        return
    
    # Send typing indicator while processing
    action_task = asyncio.create_task(
        send_chat_action(bot, message.chat.id, ChatAction.TYPING.value, 10.0)
    )
    
    try:
        # Download document file
        document_file = await bot.get_file(message.document.file_id)
        document_data = io.BytesIO()
        await bot.download_file(document_file.file_path, document_data)
        
        file_name = message.document.file_name or "unknown_file"
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(document_data.getvalue())
            document_file_path = temp_file.name
        
        # Extract text from document
        document_text = await extract_document_text(document_file_path, file_name)
        
        # Clean up temporary file
        os.unlink(document_file_path)
        
        # Check if text is too long
        if len(document_text) > 4000:
            document_text = document_text[:4000] + "... [text truncated due to length]"
        
        # Get AI response with context about the document
        prompt = f"I'm sending you the content of a document named '{file_name}'. Please analyze it and provide insights.\n\nDocument content:\n{document_text}"
        
        await stream_ai_response(message.from_user.id, prompt, message)
    
    except Exception as e:
        logger.error(f"Error processing document: {e}")
        await message.reply(f"⚠️ Error processing document: {str(e)}")
    
    finally:
        # Cancel typing indicator
        action_task.cancel()

@router.message(F.text)
async def text_message_handler(message: Message, bot: Bot):
    """Handle text messages"""
    if not is_user_allowed(message.from_user.id):
        await message.answer("⚠️ You're not authorized to use this bot.")
        return
    
    user_state = get_user_state(message.from_user.id)
    
    # Check if user has reached daily limit
    if user_state.daily_usage >= MAX_MESSAGES_PER_DAY:
        await message.answer(f"⚠️ You've reached your daily limit of {MAX_MESSAGES_PER_DAY} messages. Please try again tomorrow.")
        return
    
    # Stream response
    await stream_ai_response(message.from_user.id, message.text, message)

# Admin Commands
@router.message(Command("stats_admin"))
async def admin_stats(message: Message):
    """Admin command to show statistics"""
    if message.from_user.id not in BOT_ADMIN_IDS:
        await message.answer("⚠️ This command is only available to admins.")
        return
    
    # Create stats
    total_users = len(user_states)
    active_users = sum(1 for state in user_states.values() if state.daily_usage > 0)
    total_messages = sum(state.daily_usage for state in user_states.values())
    
    # API key stats
    api_stats = "\n".join([
        f"- Key ending with ...{key[-4:]}: {api_key_failure_count[key]} failures"
        for key in OPENROUTER_API_KEYS
    ])
    
    stats_text = (
        f"📊 {hbold('Admin Statistics')}\n\n"
        f"Total users: {hbold(total_users)}\n"
        f"Active users today: {hbold(active_users)}\n"
        f"Total messages today: {hbold(total_messages)}\n\n"
        f"API Key Status:\n{api_stats}"
    )
    
    await message.answer(stats_text, parse_mode=ParseMode.HTML)

@router.message(Command("broadcast"))
async def admin_broadcast(message: Message, bot: Bot):
    """Admin command to broadcast message to all users"""
    if message.from_user.id not in BOT_ADMIN_IDS:
        await message.answer("⚠️ This command is only available to admins.")
        return
    
    # Extract broadcast message
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        await message.answer("⚠️ Please provide a message to broadcast.")
        return
    
    broadcast_message = command_parts[1]
    success_count = 0
    error_count = 0
    
    # Broadcast to all users
    for user_id in user_states:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"📢 {hbold('Broadcast Message')}:\n\n{broadcast_message}",
                parse_mode=ParseMode.HTML
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to user {user_id}: {e}")
            error_count += 1
    
    await message.answer(
        f"📢 Broadcast sent to {success_count} users.\n"
        f"Failed: {error_count}"
    )

# Scheduled tasks
async def scheduled_tasks():
    """Run scheduled tasks"""
    while True:
        try:
            # Clean expired history every hour
            clean_expired_history()
            logger.info("Cleaned expired history")
        except Exception as e:
            logger.error(f"Error in scheduled tasks: {e}")
        
        # Sleep for an hour
        await asyncio.sleep(60 * 60)

# Main function
async def main():
    """Main function"""
    # Initialize the bot and dispatcher
    bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    
    # Add middleware
    dp.message.middleware(ChatActionMiddleware())
    
    # Include the router
    dp.include_router(router)
    
    # Start scheduled tasks
    asyncio.create_task(scheduled_tasks())
    
    # Start polling
    logger.info("Starting bot with polling")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
