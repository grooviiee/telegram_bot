import asyncio
import os
import telegram
import json
import requests
from telegram.ext import *
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get credentials from environment variables
MY_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if not MY_TOKEN or not CHAT_ID:
    raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env file")


async def send_text(bot, text):
    """Send message using async method"""
    await bot.send_message(CHAT_ID, text)


def send_message(message):
    """Send message using HTTP API"""
    url = f'https://api.telegram.org/bot{MY_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={message}'
    response = json.loads(requests.get(url).text)
    print(response)


if __name__ == '__main__':
    # Example: Send async message
    msg = 'new is start yes'
    bot = telegram.Bot(token=MY_TOKEN)
    asyncio.run(send_text(bot, msg))

    # Example: Send HTTP message
    send_message('반가워요')