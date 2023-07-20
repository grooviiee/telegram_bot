import asyncio
import telegram
from telegram.ext import *

MY_TOKEN = '6381769851:AAE_7t57ut7jh0-pHZWTZz2f0T96BulTWmY'
CHAT_ID = 'grooviiee_bot'

async def send_text(bot, text):
    await bot.send_message(CHAT_ID, text)
    
msg = 'new is start yes'

bot = telegram.Bot(token=MY_TOKEN)
asyncio.run(send_text(bot, msg))


import asyncio
import telegram
import json
import requests

MY_TOKEN = '6381769851:AAE_7t57ut7jh0-pHZWTZz2f0T96BulTWmY'
CHAT_ID = '798391124'


def send_message(message):
  url=f'https://api.telegram.org/bot{MY_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={message}'
  response=json.loads(requests.get(url).text)
  print(response)

send_message('반가워요')