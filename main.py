import discord
from discord.ext import commands, tasks
import datetime
import os
from flask import Flask, jsonify
import threading
import asyncio
import time
import sys

# ==========================================
# IMPORTAR DATOS Y FUNCIONES DE LA CARPETA UTILS
# ==========================================
from utils.data import *

# ==========================================
# CARGA INICIAL (CON PAUSAS PARA GOOGLE SHEETS)
# ==========================================
print("🔄 Cargando datos desde Google Sheets (modo seguro)...")
time.sleep(1)
CONFIG_RADAR = cargar_config_general()
time.sleep(0.5)
cargar_zonas()
time.sleep(0.5)
DIAS_ACTIVIDAD, HORAS_ACTIVIDAD = cargar_horarios()
time.sleep(0.5)
cargar_comandos()
time.sleep(0.5)
CONFIG_RECLUTAMIENTO = cargar_config_reclutamiento()
time.sleep(0.5)
cargar_preguntas_reclutamiento()
time.sleep(0.5)
cargar_preguntas_desplegables()
time.sleep(0.5)
cargar_logs_config()
time.sleep(0.5)
cargar_categorias_config()
time.sleep(0.5)
cargar_roles_staff()
time.sleep(0.5)
cargar_roles_auto()
time.sleep(0.5)
cargar_mensajes_config()
time.sleep(0.5)
cargar_config_embed()
print("✅ Todos los datos cargados correctamente.")

# ==========================================
# BOT Y EVENTOS GLOBALES
# ==========================================
intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    sys.stdout.write("🚀 " + "="*50 + "\n")
    sys.stdout.write(f"✅ Bot Jinetes MC CONECTADO\n")
    sys.stdout.write(f" Usuario: {bot.user.name} (ID: {bot.user.id})\n")
    sys.stdout.write(f"📌 Prefijo: '{PREFIX}'\n")
    sys.stdout.write("🚀 " + "="*50 + "\n")
    sys.stdout.flush()
    try:
        await bot.tree.sync()
        sys.stdout.write("✅ Comandos slash sincronizados.\n")
        sys.stdout.flush()
        await enviar_log("sistema", " Bot Jinetes MC conectado y listo", discord.Color.green())
    except Exception as e:
        sys.stdout.write(f"🚨 Error en sync: {e}\n")
        sys.stdout.flush()
    if not ping_keeping_alive.is_running():
        ping_keeping_alive.start()

@bot.event
async def on_disconnect():
    print("⚠️ Bot desconectado de Discord. Intentando reconectar...")
    await enviar_log("sistema", "⚠️ Bot desconectado", discord.Color.orange())

@bot.event
async def on_resumed():
    print("✅ Bot reconectado a Discord.")
    await enviar_log("sistema", "✅ Bot reconectado", discord.Color.green())

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    print(f"Error en comando: {error}")

@bot.event
async def on_message(message):
    if message.author.bot or not message.content.startswith(PREFIX): return
    args = message.content[len(PREFIX):].strip().split()
    if not args: return
    comando_nombre = args[0].lower()
    if comando_nombre in COMANDOS_CONFIG:
        config = COMANDOS_CONFIG[comando_nombre]
        if str(config.get('Activo', '')).upper() == 'SI':
            funcion = config.get('Funcion', '')
            # Nota: ejecutar_menu_ayuda y ejecutar_radar ahora se manejan mejor vía slash commands, 
            # pero mantenemos compatibilidad si los usas con prefijo.
            if funcion == 'menu_ayuda': 
                from cogs.help_system import MainMenuView
                await message.channel.send(" **SISTEMA DE AYUDA JINETES MC**\nSelecciona una opción del menú desplegable:", view=MainMenuView())
            elif funcion == 'radar_geto': 
                pass # El radar ahora se maneja mejor vía /radar

@tasks.loop(minutes=5)
async def ping_keeping_alive():
    try:
        if bot.is_ready(): print(f"💓 Ping - Bot conectado. Latencia: {round(bot.latency * 1000)}ms")
        else: print("️ Ping - Bot NO está listo")
    except Exception as e: print(f"Error en ping: {e}")

# ==========================================
# CARGA DE COGS
# ==========================================
async def setup_hook():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith('_'):
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                print(f"✅ Cargado: cogs.{filename[:-3]}")
            except Exception as e:
                print(f"❌ Error cargando cogs.{filename[:-3]}: {e}")

bot.setup_hook = setup_hook

# ==========================================
# SERVIDOR WEB + RECONEXIÓN
# ==========================================
server_app = Flask(__name__)

@server_app.route('/')
def home():
    return "Bot Jinetes MC Activo 24/7 ✅", 200

@server_app.route('/health')
def health():
    if bot.is_ready():
        return jsonify({"status": "ok", "bot": "connected"}), 200
    else:
        return jsonify({"status": "error", "bot": "disconnected"}), 503

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ No se encontró DISCORD_TOKEN")
        exit(1)
    print("🚀 Iniciando conexión con Discord...")
    bot.run(token, reconnect=True)
