import asyncio
import collections
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from time import mktime
from telethon import TelegramClient, events
from telethon.tl.types import UserStatusOnline, UserStatusOffline

# --- Constants ---
API_ID = '27687138'
API_HASH = '5ac27b24bb13814945c06e03ab3bd6e9'
BOT_TOKEN = '7613028738:AAFwz2nUjX7iXxZoobsSjJt2hEpULQ9yav0'
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'

# --- Dummy Server for Render ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def start_dummy_server():
    server = HTTPServer(('0.0.0.0', 10000), DummyHandler)
    server.serve_forever()

threading.Thread(target=start_dummy_server, daemon=True).start()

# --- Telethon Clients ---
client = TelegramClient('data_thief', API_ID, API_HASH)
bot = TelegramClient('bot', API_ID, API_HASH)

data = {}
help_messages = [
    '/start - start online monitoring',
    '/stop - stop monitoring',
    '/add - add user: /add username name',
    '/list - show monitored users',
    '/remove - remove user by index',
    '/setdelay - set delay in seconds',
    '/logs - show logs',
    '/clearlogs - clear logs',
    '/clear - clear user list',
    '/cleardata - reset everything',
    '/disconnect - shut down bot'
]

class Contact:
    def __init__(self, username, name):
        self.id = username
        self.name = name
        self.online = None
        self.last_online = None
        self.last_offline = None

    def __str__(self):
        return f'{self.name}: {self.id}'

# --- Utilities ---
def utc2localtime(utc):
    pivot = mktime(utc.timetuple())
    offset = datetime.fromtimestamp(pivot) - datetime.utcfromtimestamp(pivot)
    return utc + offset

def printToFile(text):
    with open('spy_log.txt', 'a') as f:
        print(text)
        f.write(text + '\n')

def get_interval(date):
    d = divmod(date.total_seconds(),86400)
    h = divmod(d[1],3600)
    m = divmod(h[1],60)
    s = m[1]
    return '%dh:%dm:%ds' % (h[0],m[0],s)

# --- Commands ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    id = event.chat_id
    data.setdefault(id, {'contacts': [], 'delay': 5, 'is_running': False})
    user_data = data[id]

    if user_data['is_running']:
        return await event.respond("Already monitoring.")
    if not user_data['contacts']:
        return await event.respond("No contacts added.")

    user_data['is_running'] = True
    await event.respond("Started monitoring.")

    while user_data['is_running'] and user_data['contacts']:
        for contact in user_data['contacts']:
            try:
                entity = await client.get_entity(contact.id)
                status = entity.status

                if isinstance(status, UserStatusOnline) and not contact.online:
                    contact.online = True
                    contact.last_offline = datetime.now()
                    msg = f"{contact.name} went online."
                    await event.respond(msg)

                elif isinstance(status, UserStatusOffline) and contact.online:
                    contact.online = False
                    contact.last_online = status.was_online
                    msg = f"{contact.name} went offline."
                    await event.respond(msg)

            except Exception as e:
                await event.respond(f"Error checking {contact.name}: {e}")

        await asyncio.sleep(user_data.get('delay', 5))

    await event.respond("Monitoring stopped.")

@bot.on(events.NewMessage(pattern='/stop'))
async def stop(event):
    data[event.chat_id]['is_running'] = False
    await event.respond("Stopped monitoring.")

@bot.on(events.NewMessage(pattern='/add'))
async def add(event):
    parts = event.message.text.split()
    if len(parts) < 3:
        return await event.respond("Usage: /add username name")
    username, name = parts[1], parts[2]
    contact = Contact(username, name)
    data.setdefault(event.chat_id, {'contacts': []})['contacts'].append(contact)
    await event.respond(f"Added {name} ({username})")

@bot.on(events.NewMessage(pattern='/remove'))
async def remove(event):
    index = int(event.message.text.split()[1])
    contacts = data[event.chat_id]['contacts']
    if 0 <= index < len(contacts):
        removed = contacts.pop(index)
        await event.respond(f"Removed {removed.name}")
    else:
        await event.respond("Invalid index")

@bot.on(events.NewMessage(pattern='/list'))
async def list_contacts(event):
    contacts = data.get(event.chat_id, {}).get('contacts', [])
    if not contacts:
        await event.respond("List is empty")
    else:
        await event.respond("\n".join(f"{i}: {c}" for i, c in enumerate(contacts)))

@bot.on(events.NewMessage(pattern='/setdelay'))
async def setdelay(event):
    delay = int(event.message.text.split()[1])
    data[event.chat_id]['delay'] = delay
    await event.respond(f"Delay set to {delay}s")

@bot.on(events.NewMessage(pattern='/logs'))
async def logs(event):
    try:
        with open('spy_log.txt') as f:
            await event.respond(f.read() or "No logs yet.")
    except:
        await event.respond("No log file found.")

@bot.on(events.NewMessage(pattern='/clearlogs'))
async def clearlogs(event):
    open('spy_log.txt', 'w').close()
    await event.respond("Logs cleared.")

@bot.on(events.NewMessage(pattern='/clear'))
async def clear(event):
    data[event.chat_id]['contacts'] = []
    await event.respond("Contacts cleared.")

@bot.on(events.NewMessage(pattern='/cleardata'))
async def cleardata(event):
    data[event.chat_id] = {'contacts': [], 'delay': 5, 'is_running': False}
    await event.respond("All data cleared.")

@bot.on(events.NewMessage(pattern='/disconnect'))
async def disconnect(event):
    await event.respond("Disconnecting bot")
    await bot.disconnect()

# --- Main ---
async def main():
    await client.connect()
    await bot.start(bot_token=BOT_TOKEN)
    print("Bot running...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    import asyncio

    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
