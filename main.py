import subprocess
import sys
import importlib.util

REQUIRED_PACKAGES = ["pyTelegramBotAPI"]
missing_packages = [pkg for pkg in REQUIRED_PACKAGES if importlib.util.find_spec(pkg) is None]
if missing_packages:
    subprocess.run([sys.executable, "-m", "pip", "install", *missing_packages], check=True)

import telebot
from telebot.types import Message

BOT_TOKEN = "7424226387:AAH48CWJDiWnHwAcS7ZFrknwB4pDAWOgcl0"
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(content_types=['video'])
def handle_video(message: Message):
    file_id = message.video.file_id
    chat_id = message.chat.id
    try:
        bot.send_video(chat_id, file_id)
    except Exception as e:
        print(f"Error in senderhide operation: {e}")
    try:
        bot.delete_message(chat_id, message.message_id)
    except Exception as e:
        print(f"Error deleting user message: {e}")

bot.polling(none_stop=True)
