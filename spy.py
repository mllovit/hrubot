import telethon.sync
import collections
import threading
import asyncio
import os
from telethon.sessions import StringSession
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import UserStatusOnline, UserStatusOffline
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- Dummy Server for Render Health Checks ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def start_dummy_server():
    server = HTTPServer(("0.0.0.0", 10000), DummyHandler)
    server.serve_forever()

threading.Thread(target=start_dummy_server, daemon=True).start()

# --- Configuration ---
API_ID = int(os.environ.get('API_ID'))
API_HASH = os.environ.get('API_HASH')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
TELETHON_SESSION = os.environ.get('TELETHON_SESSION')

# --- Telegram Clients ---
client = TelegramClient(StringSession(TELETHON_SESSION), API_ID, API_HASH)
bot = TelegramClient(None, API_ID, API_HASH)

# --- In-memory Data Storage ---
data = {}
background_tasks = {}

# --- Data Structure for Contacts ---
class Contact:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.online = False
        self.last_online = None
        self.last_offline = None

    def __str__(self):
        return f'{self.name}: {self.id}'

# --- Background Monitoring Function (ROBUST VERSION) ---
async def monitor_user(chat_id, user_data):
    try:
        while user_data.get('is_running', False):
            contacts_to_remove = []
            contacts = user_data.get('contacts', [])

            for contact in contacts:
                try:
                    account = await client.get_entity(contact.id)
                    status = account.status

                    if isinstance(status, UserStatusOnline):
                        if not contact.online:
                            contact.online = True
                            await bot.send_message(chat_id, f"{contact.name} is now 🟢 ONLINE")
                    elif isinstance(status, UserStatusOffline):
                        if contact.online:
                            contact.online = False
                            await bot.send_message(chat_id, f"{contact.name} is now 🔴 OFFLINE")

                except (ValueError, TypeError):
                    await bot.send_message(chat_id, f"⚠️ Could no longer find user {contact.id}. Removing them from the list.")
                    contacts_to_remove.append(contact)
                except Exception as e:
                    await bot.send_message(chat_id, f"An unexpected error occurred while checking {contact.name}: {e}. Stopping monitor.")
                    user_data['is_running'] = False
                    break

            if contacts_to_remove:
                user_data['contacts'] = [c for c in contacts if c not in contacts_to_remove]
            
            if not user_data.get('is_running', False):
                break

            delay = user_data.get('delay', 15)
            await asyncio.sleep(delay)

    except asyncio.CancelledError:
        print(f"Monitoring task for chat {chat_id} was cancelled.")
    finally:
        print(f"Monitoring stopped for chat {chat_id}.")

# --- Bot Command Handlers ---

@bot.on(events.NewMessage(pattern='^/start$'))
async def start_monitoring(event):
    chat_id = event.chat_id
    if chat_id not in data: data[chat_id] = {}
    if chat_id in background_tasks and not background_tasks[chat_id].done():
        await event.respond("A monitor is already running. Use /stop first.")
        return
    user_data = data[chat_id]
    user_data.setdefault('contacts', [])
    user_data['is_running'] = True
    if not user_data['contacts']:
        await event.respond("Your list is empty. Add a user with `/add @username DisplayName`.")
        return
    task = asyncio.create_task(monitor_user(chat_id, user_data))
    background_tasks[chat_id] = task
    await event.respond("✅ Monitoring started...")

@bot.on(events.NewMessage(pattern='^/stop$'))
async def stop_monitoring(event):
    chat_id = event.chat_id
    if chat_id in data: data[chat_id]['is_running'] = False
    task = background_tasks.get(chat_id)
    if task and not task.done():
        task.cancel()
        del background_tasks[chat_id]
        await event.respond('🛑 Monitoring stopped.')
    else:
        await event.respond('Monitoring was not running.')

@bot.on(events.NewMessage(pattern='^/add'))
async def add_contact(event):
    parts = event.message.message.split(maxsplit=2)
    if len(parts) < 3:
        await event.respond('Invalid format. Please use: `/add @username DisplayName`')
        return

    user_identifier = parts[1]
    name = parts[2]
    chat_id = event.chat_id

    try:
        await client.get_entity(user_identifier)
        print(f"Successfully resolved user: {user_identifier}")
    except (ValueError, TypeError):
        await event.respond(f"❌ **Error:** Could not find the user `{user_identifier}`. Please make sure the username is correct, includes the '@', and is for a public account.")
        return

    if chat_id not in data: data[chat_id] = {}
    user_data = data[chat_id]
    user_data.setdefault('contacts', [])
    if any(c.id == user_identifier for c in user_data['contacts']):
        await event.respond(f'"{name}" is already in your list.')
        return
    contact = Contact(user_identifier, name)
    user_data['contacts'].append(contact)
    await event.respond(f'✅ Added "{name}" ({user_identifier}) to your monitoring list.')

@bot.on(events.NewMessage(pattern='^/list$'))
async def list_contacts(event):
    contacts = data.get(event.chat_id, {}).get('contacts', [])
    if not contacts:
        await event.respond('Your monitoring list is empty.')
        return
    response_lines = ["Your monitoring list:"]
    for i, contact in enumerate(contacts):
        response_lines.append(f'{i}: {contact.name} ({contact.id})')
    await event.respond('\n'.join(response_lines))

@bot.on(events.NewMessage(pattern='^/remove'))
async def remove_contact(event):
    parts = event.message.message.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await event.respond('Invalid format. Use `/remove <index>` (get index from /list).')
        return
    index = int(parts[1])
    contacts = data.get(event.chat_id, {}).get('contacts', [])
    if 0 <= index < len(contacts):
        removed_contact = contacts.pop(index)
        await event.respond(f'Removed "{removed_contact.name}" from your list.')
    else:
        await event.respond('Invalid index. Use /list to see available contacts.')

@bot.on(events.NewMessage(pattern='^/setdelay'))
async def set_delay(event):
    parts = event.message.message.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await event.respond('Invalid format. Use: `/setdelay <seconds>`')
        return
    delay = int(parts[1])
    if event.chat_id not in data: data[event.chat_id] = {}
    if delay >= 5:
        data[event.chat_id]['delay'] = delay
        await event.respond(f'Check delay updated to {delay} seconds.')
    else:
        await event.respond('Delay must be at least 5 seconds.')

@bot.on(events.NewMessage(pattern='^/help$'))
async def show_help(event):
    help_messages = [
        '/start - Start monitoring users.',
        '/stop - Stop monitoring.',
        '/add @username Name - Add a user to monitor.',
        '/list - Show users in your list.',
        '/remove <index> - Remove a user from the list.',
        '/setdelay <seconds> - Set delay between checks (min 5s).',
        '/help - Show this help message.'
    ]
    await event.respond('\n'.join(help_messages))

# --- Main Application Logic ---
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("Bot is running!")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    with client:
        client.loop.run_until_complete(main())
