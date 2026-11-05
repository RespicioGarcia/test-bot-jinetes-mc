import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import threading
from flask import Flask, jsonify
from utils.data_manager import DataManager

# 1. Cargar otras variables de entorno (PORT, SPREADSHEET_NAME, etc.)
load_dotenv()

# 2. Inicializar Bot
intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix="-", intents=intents)

# 3. Inyectar el Data Manager
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
def home(): 
    return "Bot Jinetes MC Activo 24/7 ✅", 200

@app.route('/health')
def health():
    return jsonify({"status": "ok" if bot.is_ready() else "error"}), 200 if bot.is_ready() else 503

def run_web():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

threading.Thread(target=run_web, daemon=True).start()

# ==========================================
# 6. OBTENCIÓN SEGURA DEL TOKEN
# ==========================================
def obtener_token():
    # RUTA DEL ARCHIVO EN TU HOSTING (Cámbiala por la ruta real que uses)
    ruta_archivo_token = "/etc/secrets/discord_token.txt" 
    
    # 1. Intentar leer desde el archivo de secretos del hosting
    if os.path.exists(ruta_archivo_token):
        with open(ruta_archivo_token, "r", encoding="utf-8") as f:
            token = f.read().strip() # .strip() elimina espacios o saltos de línea accidentales
            if token:
                print("✅ Token cargado correctamente desde el archivo de secretos.")
                return token

    # 2. Si no existe el archivo (ej: estás probando en tu PC local), usa el .env como respaldo
    token_env = os.getenv("DISCORD_TOKEN")
    if token_env:
        print("⚠️ Archivo de secretos no encontrado. Usando token del archivo .env (Modo Local).")
        return token_env

    # 3. Si no hay nada, fallar de forma segura
    print("❌ ERROR FATAL: No se encontró el token ni en el archivo de secretos ni en el .env")
    return None

# 7. Ejecutar el bot
if __name__ == "__main__":
    token = obtener_token()
    
    if not token:
        print("🛑 El bot no puede iniciarse sin un token válido.")
        exit(1) # Detiene el programa de forma limpia
        
    print("🚀 Iniciando conexión con Discord...")
    bot.run(token, reconnect=True)
