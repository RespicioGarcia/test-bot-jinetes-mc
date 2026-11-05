import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import threading
from flask import Flask, jsonify
from utils.data_manager import DataManager

# 1. Cargar variables de entorno
load_dotenv()

# 2. Inicializar Bot
intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix="-", intents=intents)

# 3. Inyectar el Data Manager en el bot
bot.data_manager = DataManager()
bot.data_manager.cargar_todo()

# 4. Cargar Cogs automáticamente
async def setup_hook():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith('_'):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            print(f"✅ Cargado: cogs.{filename[:-3]}")

bot.setup_hook = setup_hook

# 5. Servidor Web (Flask)
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Jinetes MC Activo 24/7 ✅", 200

@app.route('/health')
def health():
    return jsonify({"status": "ok" if bot.is_ready() else "error"}), 200 if bot.is_ready() else 503

def run_web():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

threading.Thread(target=run_web, daemon=True).start()

# 6. Ejecutar
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    bot.run(token, reconnect=True)
