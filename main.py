# Full ReSender bot with fixed video forwarding and single polling instance

import asyncio
import json
import os
import nest_asyncio
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message
from telebot.apihelper import ApiTelegramException
import logging

# Enable nested loops for Colab
nest_asyncio.apply()
API_TOKEN = "8028501216:AAGCd3xv4bgVPcA8Ngdt4CX9DtBTs36y2jI"
bot = AsyncTeleBot(API_TOKEN)

STATE_FILE = "resender_state.json"
state = {"admin_id": None, "group_id": None, "video_file_ids": []}
if os.path.exists(STATE_FILE):
    with open(STATE_FILE, 'r') as f:
        state.update(json.load(f))

def save_state():
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

message_map = {}
queue = asyncio.Queue()

# Safe API call with retry
def log_exception(e):
    logging.error(f"[safe_send] Telegram API error: {e}")
    retry_after = e.result_json.get("parameters", {}).get("retry_after", 5)
    return retry_after + 1

async def safe_send(task):
    try:
        typ = task["type"]
        chat_id = task["chat_id"]
        send_func = {
            "send_message": bot.send_message,
            "send_video": bot.send_video,
            "send_photo": bot.send_photo,
            "send_audio": bot.send_audio,
            "send_document": bot.send_document,
            "send_voice": bot.send_voice,
        }[typ]

        kwargs = {"chat_id": chat_id, "parse_mode": "HTML"}
        if "text" in task:
            kwargs["text"] = task["text"]
        if "file_id" in task:
            kwargs[typ.split('_')[1]] = task["file_id"]
        if "caption" in task:
            kwargs["caption"] = task["caption"]

        result = await send_func(**kwargs)
        if task.get("orig_user"):
            message_map[result.message_id] = task["orig_user"]

    except ApiTelegramException as e:
        delay = log_exception(e)
        await asyncio.sleep(delay)
        await queue.put(task)  # Requeue the failed task
    except Exception as ex:
        logging.error(f"[safe_send] Unexpected error: {ex}")
        await asyncio.sleep(3)
        await queue.put(task)

async def queue_worker():
    while True:
        task = await queue.get()
        await safe_send(task)
        queue.task_done()


@bot.message_handler(commands=['addmeadmin'], chat_types=['private'])
async def add_admin(message: Message):
    user_id = message.from_user.id
    if state["admin_id"] is None or state["admin_id"] == user_id:
        state["admin_id"] = user_id
        save_state()
        await bot.send_message(user_id, "You are now the admin.")

@bot.message_handler(commands=['setgroup'], chat_types=['group', 'supergroup'])
async def set_group(message: Message):
    if message.from_user.id == state["admin_id"]:
        state["group_id"] = message.chat.id
        save_state()
        await bot.send_message(message.chat.id, "Group set for forwarding.")

@bot.message_handler(commands=['togrp'], chat_types=['private'])
async def to_group(message: Message):
    if message.from_user.id != state["admin_id"] or state["group_id"] is None:
        return
    text = message.text.partition(' ')[2]
    if text:
        await queue.put({"type": "send_message", "chat_id": state["group_id"], "text": text})
        try:
            await bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

@bot.message_handler(content_types=['video'], chat_types=['private'])
async def admin_video(message: Message):
    if message.from_user.id == state["admin_id"] and state["group_id"] is not None:
        fid = message.video.file_id
        if fid in state["video_file_ids"]:
            await bot.delete_message(message.chat.id, message.message_id)
            return
        state["video_file_ids"].append(fid)
        save_state()
        await queue.put({"type": "send_video", "chat_id": state["group_id"], "file_id": fid})
        try:
            await bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

@bot.message_handler(chat_types=['private'], func=lambda m: m.from_user.id != state["admin_id"],
                     content_types=['text', 'photo', 'video', 'audio', 'document', 'voice'])
async def user_to_admin(message: Message):
    if state["admin_id"] is None:
        return
    user = message.from_user
    name = user.username or user.first_name or "User"
    prefix = f"<b>{name}:</b> "

    if message.content_type == 'text':
        await queue.put({"type": "send_message", "chat_id": state["admin_id"], "text": prefix + message.text, "orig_user": user.id})
    else:
        file_id = getattr(message, message.content_type).file_id
        await queue.put({"type": f"send_{message.content_type}", "chat_id": state["admin_id"], "file_id": file_id,
                         "caption": prefix + (message.caption or ""), "orig_user": user.id})

@bot.message_handler(chat_types=['private'], func=lambda m: m.from_user.id == state["admin_id"] and m.reply_to_message)
async def admin_reply(message: Message):
    orig_user_id = message_map.get(message.reply_to_message.message_id)
    if not orig_user_id:
        return
    if message.content_type == 'text':
        await queue.put({"type": "send_message", "chat_id": orig_user_id, "text": message.text})
    else:
        file_id = getattr(message, message.content_type).file_id
        await queue.put({"type": f"send_{message.content_type}", "chat_id": orig_user_id, "file_id": file_id,
                         "caption": (message.caption or "")})

# Start bot
async def main():
    asyncio.create_task(queue_worker())
    await bot.infinity_polling()

try:
    asyncio.run(main())
except RuntimeError as e:
    if "already running" in str(e):
        print("Polling loop already running, ignoring duplicate run.")
    else:
        raise
