import telethon.sync
import collections
import threading
import asyncio
from datetime import datetime
from sys import argv, exit
from telethon import TelegramClient, events, connection
from telethon.tl.types import UserStatusOnline, UserStatusOffline
from time import mktime
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- Dummy Server for Render Health Checks ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def start_dummy_server():
    """Starts a simple HTTP server in a separate thread to keep the Render service alive."""
    server = HTTPServer(("0.0.0.0", 10000), DummyHandler)
    server.serve_forever()

threading.Thread(target=start_dummy_server, daemon=True).start()

# --- Configuration ---
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
API_HASH = 'YOUR_API_HASH'  # Replace with your actual API Hash
API_ID = 'YOUR_API_ID'      # Replace with your actual API ID
BOT_TOKEN = "YOUR_BOT_TOKEN" # Replace with your actual Bot Token

# --- Telegram Clients ---
# This client logs in as a user account to check online status.
# It will create a 'user_client.session' file.
client = TelegramClient('user_client', API_ID, API_HASH)

# This client logs in as your bot to interact with users.
# It will create a 'bot_client.session' file.
bot = TelegramClient('bot_client', API_ID, API_HASH)

# --- In-memory Data Storage ---
# Note: This data will be lost on restart. For persistence, consider using a database.
data = {}
background_tasks = {} # To keep track of running monitoring tasks for each chat

# --- Data Structure for Contacts ---
class Contact:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.online = False
        # Timestamps are not used in the current logic but are good for future features.
        self.last_online = None
        self.last_offline = None

    def __str__(self):
        return f'{self.name}: {self.id}'

# --- Background Monitoring Function ---
async def monitor_user(chat_id, user_data):
    """
    This is the actual monitoring loop. It runs as a background task
    and can be started or stopped without blocking the whole bot.
    """
    contacts = user_data.get('contacts', [])
    try:
        # The loop continues as long as the 'is_running' flag is True.
        while user_data.get('is_running', False):
            for contact in contacts:
                try:
                    # Fetch the user entity to get their latest status.
                    account = await client.get_entity(contact.id)
                    status = account.status

                    if isinstance(status, UserStatusOnline):
                        if not contact.online:
                            contact.online = True
                            contact.last_online = datetime.now()
                            # Use bot.send_message for background tasks.
                            await bot.send_message(chat_id, f"{contact.name} is now 🟢 ONLINE")
                    elif isinstance(status, UserStatusOffline):
                        if contact.online:
                            contact.online = False
                            contact.last_offline = datetime.now()
                            await bot.send_message(chat_id, f"{contact.name} is now 🔴 OFFLINE")

                except Exception as e:
                    # Notify the user if an error occurs while checking a contact.
                    await bot.send_message(chat_id, f"Error checking status for {contact.name}: {e}")
                    # To prevent spamming on persistent errors, you might want to stop monitoring this user.
                    user_data['is_running'] = False # Optional: stop on error
                    break # Exit the for loop

            delay = user_data.get('delay', 15) # Default delay of 15 seconds
            await asyncio.sleep(delay)

    except asyncio.CancelledError:
        # This exception is raised when the task is cancelled, which is a normal way to stop it.
        print(f"Monitoring task for chat {chat_id} was cancelled.")
    finally:
        print(f"Monitoring stopped for chat {chat_id}.")
        await bot.send_message(chat_id, "Monitoring has been fully stopped.")


# --- Bot Command Handlers ---

@bot.on(events.NewMessage(pattern='^/start$'))
async def start_monitoring(event):
    chat_id = event.chat_id
    if chat_id not in data:
        data[chat_id] = {}

    # Prevent starting a new task if one is already running.
    if chat_id in background_tasks and not background_tasks[chat_id].done():
        await event.respond("A monitor is already running. Please use /stop first.")
        return

    user_data = data[chat_id]
    user_data.setdefault('contacts', [])
    user_data['is_running'] = True

    if not user_data['contacts']:
        await event.respond("Your contact list is empty. Add a user with `/add @username DisplayName`.")
        return

    # Create and store the background task.
    task = asyncio.create_task(monitor_user(chat_id, user_data))
    background_tasks[chat_id] = task
    await event.respond("✅ Monitoring started...")

@bot.on(events.NewMessage(pattern='^/stop$'))
async def stop_monitoring(event):
    chat_id = event.chat_id
    if chat_id in data:
        # Signal the loop to stop.
        data[chat_id]['is_running'] = False

    task = background_tasks.get(chat_id)
    if task and not task.done():
        # Cancel the task to stop it immediately.
        task.cancel()
        del background_tasks[chat_id]
        await event.respond('🛑 Stopping monitoring... The process will halt shortly.')
    else:
        await event.respond('Monitoring was not running.')

@bot.on(events.NewMessage(pattern='^/add'))
async def add_contact(event):
    parts = event.message.message.split()
    if len(parts) < 3:
        await event.respond('Invalid format. Please use: `/add @username DisplayName`')
        return

    user_identifier = parts[1] # e.g., @username or phone number
    name = " ".join(parts[2:])
    chat_id = event.chat_id

    if chat_id not in data:
        data[chat_id] = {}
    user_data = data[chat_id]
    user_data.setdefault('contacts', [])

    # Check for duplicates
    if any(c.id == user_identifier for c in user_data['contacts']):
        await event.respond(f'{name} is already in your list.')
        return

    contact = Contact(user_identifier, name)
    user_data['contacts'].append(contact)
    await event.respond(f'Added "{name}" ({user_identifier}) to your monitoring list.')

@bot.on(events.NewMessage(pattern='^/list$'))
async def list_contacts(event):
    chat_id = event.chat_id
    contacts = data.get(chat_id, {}).get('contacts', [])
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
        await event.respond('Invalid format. Please use: `/remove <index>` (get index from /list).')
        return

    index = int(parts[1])
    chat_id = event.chat_id
    contacts = data.get(chat_id, {}).get('contacts', [])

    if 0 <= index < len(contacts):
        removed_contact = contacts.pop(index)
        await event.respond(f'Removed "{removed_contact.name}" from your list.')
    else:
        await event.respond('Invalid index. Use /list to see available contacts.')

@bot.on(events.NewMessage(pattern='^/setdelay'))
async def set_delay(event):
    parts = event.message.message.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await event.respond('Invalid format. Please use: `/setdelay <seconds>`')
        return

    delay = int(parts[1])
    chat_id = event.chat_id
    if chat_id not in data:
        data[chat_id] = {}

    if delay >= 5: # Set a reasonable minimum delay
        data[chat_id]['delay'] = delay
        await event.respond(f'Check delay has been updated to {delay} seconds.')
    else:
        await event.respond('Delay must be at least 5 seconds.')

@bot.on(events.NewMessage(pattern='^/help$'))
async def show_help(event):
    help_messages = [
        '/start - Start monitoring the users in your list.',
        '/stop - Stop the monitoring process.',
        '/add @username Name - Add a user to the monitoring list.',
        '/list - Show all users in your list with their index.',
        '/remove <index> - Remove a user by their index from the list.',
        '/setdelay <seconds> - Set the delay between status checks (min 5s).',
        '/help - Show this help message.'
    ]
    await event.respond('\n'.join(help_messages))

# --- Main Application Logic ---
async def main():
    """Connects both clients and runs the bot until it's disconnected."""
    # Connect the user client first. It might ask for login details in the console on first run.
    await client.connect()
    if not await client.is_user_authorized():
        print("User client is not authorized. Please log in.")
        # Handle login flow here if needed, e.g., client.send_code_request(...) etc.
        # For a server environment, you MUST upload the session file after a local login.

    # Start the bot client using the bot token.
    await bot.start(bot_token=BOT_TOKEN)

    print("Bot is running!")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    # This approach correctly handles the asyncio event loop for Telethon.
    # It gets the current event loop and runs the main() coroutine,
    # which then blocks on run_until_disconnected, keeping the bot alive.
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
