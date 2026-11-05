import os
import discord
from discord.ext import commands
import threading
from flask import Flask, jsonify
from utils.data_manager import DataManager

# 1. Inicializar Bot
intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix="-", intents=intents)

# 2. Inyectar el Data Manager
bot.data_manager = DataManager()
bot.data_manager.cargar_todo()

# 3. Cargar Cogs automáticamente
async def setup_hook():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith('_'):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            print(f"✅ Cargado: cogs.{filename[:-3]}")

bot.setup_hook = setup_hook

# 4. Servidor Web (Flask)
app = Flask(__name__)
@app.route('/')
def home(): 
    return "Bot Jinetes MC Activo 24/7 ✅", 200

@app.route('/health')
def health():
    return jsonify({"status": "ok" if bot.is_ready() else "error"}), 200 if bot.is_ready() else 503

def run_web():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

threading.Thread(target=run_web, daemon=True).start()

# 5. Ejecutar el bot
if __name__ == "__main__":
    # Render inyecta las variables de entorno automáticamente
    token = os.getenv("DISCORD_TOKEN")
    
    if not token:
        print("❌ ERROR: No se encontró DISCORD_TOKEN en las variables de entorno de Render")
        exit(1)
    
    print("🚀 Iniciando conexión con Discord...")
    bot.run(token, reconnect=True)
