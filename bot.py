import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pytgcalls import PyTgCalls
from pytgcalls.types.input_stream import AudioPiped, InputStream
from pytgcalls.types.events import StreamEnded
from pymongo import MongoClient
import youtube_dl
from youtubesearchpython import VideosSearch

# ------------------ ENV -------------------
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_NAME = os.environ.get("BOT_NAME")
OWNER_USERNAME = os.environ.get("OWNER_USERNAME")
SUPPORT_LINK = os.environ.get("SUPPORT_LINK")
UPDATE_LINK = os.environ.get("UPDATE_LINK")
START_IMG = os.environ.get("START_IMG")
OWNER_ID = int(os.environ.get("OWNER_ID"))
MONGO_DB_URI = os.environ.get("MONGO_DB_URI")

# ----------------- CLIENTS ----------------
app = Client(session_name=STRING_SESSION, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
vc = PyTgCalls(app)

# ----------------- MONGO -----------------
mongo = MongoClient(MONGO_DB_URI)
db = mongo["music_bot"]
users_col = db["users"]

# ----------------- QUEUE -----------------
queues = {}  # chat_id: [(audio_url, title)]

# ----------------- HELPERS -----------------
ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True
}

def get_audio_link(url):
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info['url'], info.get('title', 'Unknown Track')

def search_youtube(query):
    results = VideosSearch(query, limit=1).result()
    if results['result']:
        return results['result'][0]['link'], results['result'][0]['title']
    else:
        return None, None

# ----------------- BOT COMMANDS -----------------
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if not users_col.find_one({"id": message.from_user.id}):
        users_col.insert_one({"id": message.from_user.id})
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Support", url=SUPPORT_LINK)],
        [InlineKeyboardButton("Owner", url=f"https://t.me/{OWNER_USERNAME}")]
    ])
    await message.reply_photo(
        photo=START_IMG,
        caption=f"🎵 **Welcome to {BOT_NAME}!**\n\nUse /play <song name or YouTube link> to play music in VC.",
        reply_markup=buttons
    )

# -------------- PLAY COMMAND -----------------
@app.on_message(filters.command("play") & filters.private)
async def play(client, message):
    if len(message.command) < 2:
        await message.reply("Send song name or YouTube link after /play")
        return

    chat_id = message.chat.id
    query = message.text.split(None, 1)[1]

    if query.startswith("http"):
        audio_link, title = get_audio_link(query)
    else:
        link, title = search_youtube(query)
        if not link:
            await message.reply("❌ No results found on YouTube")
            return
        audio_link, _ = get_audio_link(link)

    if chat_id not in queues:
        queues[chat_id] = []

    queues[chat_id].append((audio_link, title))

    if len(queues[chat_id]) == 1:
        await vc.join_group_call(chat_id, InputStream(AudioPiped(audio_link)))
        await message.reply(f"🎵 Now playing: **{title}**")
    else:
        await message.reply(f"✅ Added to queue: **{title}**")

# -------------- HANDLE NEXT SONG -----------------
@vc.on_stream_end()
async def on_stream_end(_, update: StreamEnded):
    chat_id = update.chat_id
    if chat_id in queues and queues[chat_id]:
        queues[chat_id].pop(0)
        if queues[chat_id]:
            audio_link, title = queues[chat_id][0]
            await vc.change_stream(chat_id, AudioPiped(audio_link))
            await app.send_message(chat_id, f"🎶 Now playing: **{title}**")
        else:
            queues.pop(chat_id)
            await vc.leave_group_call(chat_id)
            await app.send_message(chat_id, "⏹ Queue finished, VC stopped.")

# -------------- SKIP COMMAND -----------------
@app.on_message(filters.command("skip") & filters.private)
async def skip(client, message):
    chat_id = message.chat.id
    if chat_id in queues and queues[chat_id]:
        queues[chat_id].pop(0)
        if queues[chat_id]:
            audio_link, title = queues[chat_id][0]
            await vc.change_stream(chat_id, AudioPiped(audio_link))
            await message.reply(f"⏭ Now playing: **{title}**")
        else:
            await vc.leave_group_call(chat_id)
            await message.reply("⏹ Queue finished, VC stopped.")
    else:
        await message.reply("No songs in queue.")

# -------------- STOP COMMAND -----------------
@app.on_message(filters.command("stop") & filters.user(OWNER_ID))
async def stop(client, message):
    chat_id = message.chat.id
    queues.pop(chat_id, None)
    await vc.leave_group_call(chat_id)
    await message.reply("⏹ Stopped VC session and cleared queue.")

# -------------- QUEUE LIST -----------------
@app.on_message(filters.command("queue"))
async def show_queue(client, message):
    chat_id = message.chat.id
    if chat_id in queues and queues[chat_id]:
        text = "**Current Queue:**\n\n"
        for i, (_, title) in enumerate(queues[chat_id], start=1):
            text += f"{i}. {title}\n"
        await message.reply(text)
    else:
        await message.reply("Queue is empty.")

# -------------- BROADCAST (OWNER ONLY) -----------------
@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast(client, message):
    text = message.text.split(" ", 1)
    if len(text) < 2:
        await message.reply("Send text to broadcast")
        return
    all_users = users_col.find({})
    for user in all_users:
        try:
            await client.send_message(user["id"], text[1])
        except:
            continue
    await message.reply("✅ Broadcast sent!")

# -------------- SUPPORT & UPDATE -----------------
@app.on_message(filters.command("support"))
async def support(client, message):
    await message.reply(f"Join Support Group: {SUPPORT_LINK}")

@app.on_message(filters.command("update") & filters.user(OWNER_ID))
async def update(client, message):
    await message.reply(f"✅ Bot updated successfully!\nCheck updates: {UPDATE_LINK}")

# ----------------- RUN BOT -----------------
print(f"✅ {BOT_NAME} is starting...")
app.run()