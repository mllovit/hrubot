import telethon.sync
import collections
import threading
import asyncio
from datetime import datetime, timedelta
from sys import argv, exit
from telethon import TelegramClient, events, connection
from telethon.tl.types import UserStatusRecently, UserStatusEmpty, UserStatusOnline, UserStatusOffline, PeerUser, PeerChat, PeerChannel
from time import mktime
from http.server import HTTPServer, BaseHTTPRequestHandler

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def start_dummy_server():
    server = HTTPServer(("0.0.0.0", 10000), DummyHandler)
    server.serve_forever()

threading.Thread(target=start_dummy_server, daemon=True).start()

DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
API_HASH = '5ac27b24bb13814945c06e03ab3bd6e9'
API_ID = '27687138'
BOT_TOKEN = "7613028738:AAFwz2nUjX7iXxZoobsSjJt2hEpULQ9yav0"
USER_NAME = "@danz0_o"

client = TelegramClient('data_thief', API_ID, API_HASH)
bot = TelegramClient('bot', API_ID, API_HASH)

data = {}
help_messages = ['/start - start online monitoring ',
         '/stop - stop online monitoring ',
         '/help - show help ',
         '/add - add user to monitoring list "/add +79991234567 UserName"',
         '/list - show added users',
         '/clear - clear user list',
         '/remove - remove user from list with position in list (to show use /list command)"/remove 1"',
         '/setdelay - set delay between user check in seconds',
         '/logs - display command log',
         '/clearlogs - clear the command log file',
         '/cleardata - reset configuration',
         '/disconnect - disconnect bot',
         '/getall - status']

class Contact:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.online = False
        self.last_online = None
        self.last_offline = None

    def __str__(self):
        return f'{self.name}: {self.id}'

@bot.on(events.NewMessage(pattern='^/logs$'))
async def logs(event):
    with open('spy_log.txt', 'r') as file:
        str = file.read()
    await event.respond(str)

@bot.on(events.NewMessage(pattern='/clearlogs$'))
async def clearLogs(event):
    open('spy_log.txt', 'w').close()
    await event.respond('logs has been deleted')

@bot.on(events.NewMessage(pattern='^/clear$'))
async def clear(event):
    id = event.chat_id
    data[id] = {}
    await event.respond('User list has been cleared')

@bot.on(events.NewMessage(pattern='^/help$'))
async def help(event):
    await event.respond('\n'.join(help_messages))

@bot.on(events.NewMessage())
async def log(event):
    message = event.message
    id = message.chat_id
    str = f'{datetime.now().strftime(DATETIME_FORMAT)}: [{id}]: {message.message}'
    printToFile(str)

@bot.on(events.NewMessage(pattern='^/stop$'))
async def stop(event):
    id = event.chat_id
    if id not in data:
        data[id] = {}
    data[id]['is_running'] = False
    await event.respond('Monitoring has been stopped')

@bot.on(events.NewMessage(pattern='^/cleardata$'))
async def clearData(event):
    data.clear()
    await event.respond('Data has been cleared')

@bot.on(events.NewMessage(pattern='^/start$'))
async def start(event):
    id = event.chat_id
    if id not in data:
        data[id] = {}

    user_data = data[id]
    user_data.setdefault('contacts', [])
    user_data['is_running'] = True

    contacts = user_data['contacts']
    if not contacts:
        await event.respond("No contacts added.")
        return

    await event.respond("Monitoring started...")

    while user_data['is_running']:
        for contact in contacts:
            try:
                account = await client.get_entity(contact.id)
                status = account.status

                if isinstance(status, UserStatusOnline):
                    if not contact.online:
                        contact.online = True
                        contact.last_online = datetime.now()
                        await event.respond(f"{contact.name} is now 🟢 ONLINE")
                elif isinstance(status, UserStatusOffline):
                    if contact.online:
                        contact.online = False
                        contact.last_offline = datetime.now()
                        await event.respond(f"{contact.name} is now 🔴 OFFLINE")
                else:
                    pass

            except Exception as e:
                await event.respond(f"Error fetching {contact.name}: {e}")

        delay = user_data.get('delay', 5)
        await asyncio.sleep(delay)

    await event.respond("Stopped monitoring.")

@bot.on(events.NewMessage(pattern='^/add'))
async def add(event):
    person_info = event.message.message.split()
    phone = person_info[1]
    name = person_info[2]
    id = event.chat_id

    if id not in data:
        data[id] = {}
    user_data = data[id]
    user_data.setdefault('contacts', [])
    contact = Contact(phone, name)
    user_data['contacts'].append(contact)
    await event.respond(f'{name}: {phone} has been added')

@bot.on(events.NewMessage(pattern='^/remove'))
async def remove(event):
    index = int(event.message.message.split()[1])
    id = event.chat_id

    if id not in data:
        data[id] = {}
    contacts = data[id].get('contacts', [])

    if 0 <= index < len(contacts):
        del contacts[index]
        await event.respond(f'User №{index} has been deleted')
    else:
        await event.respond('Incorrect index')

@bot.on(events.NewMessage(pattern='^/setdelay'))
async def setDelay(event):
    delay = int(event.message.message.split()[1])
    id = event.chat_id
    if id not in data:
        data[id] = {}
    if delay >= 0:
        data[id]['delay'] = delay
        await event.respond(f'Delay has been updated to {delay}')
    else:
        await event.respond('Incorrect delay')

@bot.on(events.NewMessage(pattern='^/disconnect$'))
async def disconnect(event):
    await event.respond('Bot gonna disconnect')
    await bot.disconnect()

@bot.on(events.NewMessage(pattern='/list'))
async def list_users(event):
    id = event.chat_id
    contacts = data.get(id, {}).get('contacts', [])
    if contacts:
        await event.respond('User list:\n' + '\n'.join([str(x) for x in contacts]))
    else:
        await event.respond('List is empty')

@bot.on(events.NewMessage(pattern='/getall'))
async def getAll(event):
    response = ''
    for key, value in data.items():
        response += f'{key}:\n'
        for j, i in value.items():
            if isinstance(i, collections.Sequence) and not isinstance(i, str):
                response += f'{j}: ' + '\n'.join([str(x) for x in i]) + '\n'
            else:
                response += f'{j}: {i}\n'
        response += '\n'
    await event.respond(response)

def printToFile(text):
    with open('spy_log.txt','a') as f:
        print(text)
        f.write(text + '\n')

def utc2localtime(utc):
    pivot = mktime(utc.timetuple())
    offset = datetime.fromtimestamp(pivot) - datetime.utcfromtimestamp(pivot)
    return utc + offset

def get_interval(date):
    d = divmod(date.total_seconds(), 86400)
    h = divmod(d[1], 3600)
    m = divmod(h[1], 60)
    s = m[1]
    return '%dh:%dm:%ds' % (h[0], m[0], s)

async def main():
    await client.connect()
    await bot.start(bot_token=BOT_TOKEN)
    print("Bot is running")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
