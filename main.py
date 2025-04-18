import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.methods import DeleteWebhook
from aiogram.types import Message
from openai import OpenAI
import os

# Токен Telegram-бота
TOKEN = os.getenv("TOKEN")

# Ключи OpenRouter (переключаются по порядку)
API_KEYS = os.getenv("API_KEYS").split(',')

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Я бот на GPT. Напиши что-нибудь, и я тебе отвечу!")

@dp.message(lambda message: True)
async def handle_message(message: Message):
    for api_key in API_KEYS:
        try:
            client = OpenAI(
                base_url="https://api.langdock.com/openai/v1/",
                api_key=api_key,
            )
            completion = client.chat.completions.create(
                model="gpt-4o-4intl",
                messages=[{"role": "user", "content": message.text}]
            )
            reply = completion.choices[0].message.content
            await message.answer(reply)
            return
        except Exception as e:
            logging.warning(f"Ошибка с ключом {api_key[:15]}...: {e}")
            continue

    await message.answer("Все ключи OpenRouter недоступны. Попробуй позже.")

async def main():
    await bot(DeleteWebhook(drop_pending_updates=True))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
