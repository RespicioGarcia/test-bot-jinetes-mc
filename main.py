import discord
from discord.ext import commands, tasks
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from flask import Flask, jsonify
import threading
import asyncio
import time

# ==========================================
# 1. CONEXIÓN A GOOGLE SHEETS
# ==========================================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/creds.json", scope)
client_gsheet = gspread.authorize(creds)

SPREADSHEET_NAME = "testbotjinetesmc"
spreadsheet = client_gsheet.open(SPREADSHEET_NAME)

sheet_menu = spreadsheet.worksheet("Menu_Principal")
sheet_sub = spreadsheet.worksheet("Subcategorias")
sheet_contenido = spreadsheet.worksheet("Contenido_Menu")
sheet_busq_reglas = spreadsheet.worksheet("Reglas_Buscable")
sheet_busq_vestimenta = spreadsheet.worksheet("Vestimenta_Buscable")
sheet_zonas = spreadsheet.worksheet("Config_Radar_Zonas")
sheet_horarios = spreadsheet.worksheet("Config_Radar_Horarios")
sheet_general = spreadsheet.worksheet("Config_Radar_General")
sheet_comandos = spreadsheet.worksheet("Config_Comandos")

# ==========================================
# 2. VARIABLES GLOBALES Y CACHÉ (OPTIMIZACIÓN)
# ==========================================
RADAR_DESPLIEGUE = {}
ultimo_radar_message_id = None
canal_radar_id = None
radar_abierto_al_publico = False
COMANDOS_CONFIG = {}
PREFIX = "-"

# Variables de caché para evitar leer el Excel constantemente
CACHE_ZONAS = []
CACHE_MENU = []
CACHE_SUB = []
CACHE_CONTENIDO = []
CACHE_CONFIG = {}

def cargar_config_general():
    global CACHE_CONFIG
    if not CACHE_CONFIG:  # Solo lee si la caché está vacía
        records = sheet_general.get_all_records()
        for row in records:
            clave = next((k for k in row.keys() if 'clave' in k.lower()), None)
            valor = next((k for k in row.keys() if 'valor' in k.lower()), None)
            if clave and valor:
                CACHE_CONFIG[str(row[clave])] = str(row[valor])
    return CACHE_CONFIG

def cargar_zonas():
    global CACHE_ZONAS, RADAR_DESPLIEGUE
    if not CACHE_ZONAS:  # Solo lee si la caché está vacía
        CACHE_ZONAS = sheet_zonas.get_all_records()
    
    zonas_activas = [r for r in CACHE_ZONAS if str(r.get('Activo', '')).upper() == 'SI']
    zonas_activas.sort(key=lambda x: int(x.get('Orden', 0)))
    RADAR_DESPLIEGUE = {z['Zona']: None for z in zonas_activas}

def cargar_horarios():
    records = sheet_horarios.get_all_records()
    dias, horas = [], []
    for r in records:
        if str(r.get('Activo', '')).upper() == 'SI':
            dias.append(int(r.get('Dia_Semana', 0)))
            horas.extend([int(h.strip()) for h in str(r.get('Horas_Actividad', '')).split(',')])
    return list(set(dias)), list(set(horas))

def cargar_comandos():
    records = sheet_comandos.get_all_records()
    global COMANDOS_CONFIG
    COMANDOS_CONFIG = {str(row.get('Comando', '')).lower(): row for row in records}

# Carga inicial al arrancar el bot
CONFIG_RADAR = cargar_config_general()
cargar_zonas()
DIAS_ACTIVIDAD, HORAS_ACTIVIDAD = cargar_horarios()
cargar_comandos()

# ==========================================
# 3. BOT
# ==========================================
intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot Jinetes MC listo. Prefijo: '{PREFIX}'")
    await bot.tree.sync()
    if not verificador_tiempo_radar.is_running():
        verificador_tiempo_radar.start()
    if not ping_keeping_alive.is_running():
        ping_keeping_alive.start()

@bot.event
async def on_disconnect():
    print("⚠️ Bot desconectado de Discord. Intentando reconectar...")

@bot.event
async def on_resumed():
    print("✅ Bot reconectado a Discord.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"Error en comando: {error}")

# ==========================================
# 4. MENÚS Y BÚSQUEDA (OPTIMIZADO CON CACHÉ)
# ==========================================
def obtener_hoja_busqueda(nombre_hoja):
    mapeo = {
        "Reglas_Buscable": sheet_busq_reglas,
        "Vestimenta_Buscable": sheet_busq_vestimenta
    }
    return mapeo.get(nombre_hoja, sheet_busq_reglas)

class SearchModal(discord.ui.Modal):
    def __init__(self, categoria_nombre, hoja_nombre):
        super().__init__(title=f"🔍 Buscar en {categoria_nombre}")
        self.categoria_nombre = categoria_nombre
        self.hoja_nombre = hoja_nombre
        self.query_input = discord.ui.TextInput(
            label="Término de búsqueda",
            placeholder="Ej: armas, respawn, chaqueta...",
            required=True,
            max_length=50
        )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        query = self.query_input.value.lower()
        hoja = obtener_hoja_busqueda(self.hoja_nombre)
        
        try:
            records = hoja.get_all_records() # Búsquedas sí leen en tiempo real (es lo correcto)
            resultados = []
            for r in records:
                texto_fila = " ".join([str(v) for v in r.values() if v]).lower()
                if query in texto_fila:
                    resultados.append(" ".join([str(v) for v in r.values() if v]))
            
            if not resultados:
                return await interaction.followup.send(f"❌ No se encontraron resultados para '**{query}**' en {self.categoria_nombre}.")
            
            embed = discord.Embed(title=f"🔍 Resultados para '{query}'", color=discord.Color.blue())
            for i, res in enumerate(resultados[:5], 1):
                embed.add_field(name=f"Coincidencia {i}", value=res, inline=False)
            if len(resultados) > 5:
                embed.set_footer(text=f"Mostrando 5 de {len(resultados)} resultados.")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error al buscar: {e}", ephemeral=True)

class MainMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.build_menu()

    def build_menu(self):
        global CACHE_MENU
        if not CACHE_MENU:
            CACHE_MENU = sheet_menu.get_all_records()
        records = CACHE_MENU # Usa la caché
        
        items = [r for r in records if str(r.get('Estado', '')) in ['1', '2']]
        items.sort(key=lambda x: int(x.get('Orden', 0)))
        
        options = []
        for item in items:
            emoji = item.get('Emoji') if item.get('Emoji') else None
            estado = str(item.get('Estado', ''))
            options.append(discord.SelectOption(label=item['Nombre'], value=f"{item['ID']}|{estado}", emoji=emoji))
        
        if options:
            select = discord.ui.Select(placeholder="📂 Selecciona una categoría...", options=options)
            
            async def select_callback(interaction: discord.Interaction):
                selected = select.values[0]
                item_id, estado = selected.split('|')
                item_data = next((r for r in records if r['ID'] == item_id), None)
                nombre_categoria = item_data['Nombre'] if item_data else "Categoría"
                
                if estado == '2':
                    global CACHE_SUB
                    if not CACHE_SUB:
                        CACHE_SUB = sheet_sub.get_all_records()
                    sub_busqueda = next((s for s in CACHE_SUB if s.get('Categoria_Padre') == item_id and str(s.get('Tipo', '')) == '2'), None)
                    hoja = sub_busqueda.get('Hoja_Busqueda') if sub_busqueda else "Reglas_Buscable"
                    return await interaction.response.send_modal(SearchModal(nombre_categoria, hoja))
                
                await self.show_subcategories(interaction, item_id, nombre_categoria)

            select.callback = select_callback
            self.add_item(select)

    async def show_subcategories(self, interaction: discord.Interaction, parent_id, parent_name):
        global CACHE_SUB, CACHE_CONTENIDO
        if not CACHE_SUB:
            CACHE_SUB = sheet_sub.get_all_records()
        if not CACHE_CONTENIDO:
            CACHE_CONTENIDO = sheet_contenido.get_all_records()
            
        records = CACHE_SUB
        subs = [r for r in records if r.get('Categoria_Padre') == parent_id]
        subs.sort(key=lambda x: int(x.get('Orden', 0)))
        
        view = discord.ui.View(timeout=180)
        options = []
        for sub in subs:
            emoji = "🔹"
            tipo = str(sub.get('Tipo', ''))
            options.append(discord.SelectOption(label=sub['Nombre'], value=f"{sub['ID']}|{tipo}|{sub.get('Hoja_Busqueda', '')}", emoji=emoji))
        
        select_sub = discord.ui.Select(placeholder=f"📂 Subcategorías de {parent_name}...", options=options)
        
        async def sub_callback(sub_interaction: discord.Interaction):
            selected = select_sub.values[0]
            sub_id, tipo, hoja_busqueda = selected.split('|')
            
            if tipo == '2':
                sub_data = next((r for r in records if r['ID'] == sub_id), None)
                nombre_sub = sub_data['Nombre'] if sub_data else "Búsqueda"
                return await sub_interaction.response.send_modal(SearchModal(nombre_sub, hoja_busqueda))
            
            cont_records = CACHE_CONTENIDO
            contenido = next((c for c in cont_records if c.get('ID_Subcategoria') == sub_id), None)
            
            if not contenido:
                return await sub_interaction.response.send_message("⚠️ Esta categoría no tiene contenido configurado aún.", ephemeral=True)
            
            embed = discord.Embed(title=contenido.get('Titulo', ''), description=contenido.get('Contenido', ''), color=discord.Color.green())
            img = contenido.get('Imagen', '')
            if img and str(img).startswith('http'):
                embed.set_image(url=img)
            await sub_interaction.response.send_message(embed=embed, ephemeral=True)

        select_sub.callback = sub_callback
        view.add_item(select_sub)
        await interaction.response.send_message(f"📂 Has seleccionado: **{parent_name}**", view=view, ephemeral=True)

async def ejecutar_menu_ayuda(message):
    view = MainMenuView()
    await message.channel.send("👋 **SISTEMA DE AYUDA JINETES MC**\nSelecciona una opción del menú desplegable:", view=view)

# ==========================================
# 5. RADAR (OPTIMIZADO: SIN LEER EXCEL EN EL BUCLE)
# ==========================================
def generar_mapa_texto():
    config = cargar_config_general()
    titulo = config.get('TITULO_RADAR', '🏍️ JINETES MC • RADAR DE ZONAS')
    msg_abierto = config.get('MENSAJE_ABIERTO', '🟢 ACTIVO')
    msg_cerrado = config.get('MENSAJE_CERRADO', '🔴 EN ESPERA')
    
    estado = msg_abierto if radar_abierto_al_publico else msg_cerrado
    
    lineas_zonas = []
    for zona, usuario in RADAR_DESPLIEGUE.items():
        emoji = "📍"
        # OPTIMIZACIÓN: Usamos la caché en lugar de sheet_zonas.get_all_records()
        for r in CACHE_ZONAS:
            if r.get('Zona') == zona:
                emoji = r.get('Emoji', '📍')
                break
        estado_zona = usuario if usuario else "[ VACÍO ] ⚠️"
        lineas_zonas.append(f"  • {emoji} {zona.ljust(15)} {estado_zona}")

    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f" {titulo}\n"
        "     Control de Despliegue en Tiempo Real\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🗺️  DESPLIEGUE EN VIVO (ZONAS ASIGNADAS)\n"
        " ─────────────────────────────────────────────────────\n"
        + "\n".join(lineas_zonas) +
        "\n ─────────────────────────────────────────────────────\n"
        f" ⏱️  ESTADO: {estado}\n"
    )

class RadarControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📍 Asignar Posición", style=discord.ButtonStyle.blurple, custom_id="radar:posicion")
    async def asignar_posicion(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not radar_abierto_al_publico:
            return await interaction.response.send_message("❌ El radar está cerrado. Se abre 1H antes de la actividad.", ephemeral=True)
        
        opciones = [discord.SelectOption(label=zona, value=zona) for zona in RADAR_DESPLIEGUE.keys()]
        opciones.append(discord.SelectOption(label="🚪 Salir de Servicio", value="Retirarse"))
        
        view = discord.ui.View(timeout=60)
        select = discord.ui.Select(placeholder="📍 Elige tu punto de despliegue...", options=opciones)
        
        async def select_callback(sel_interaction: discord.Interaction):
            try:
                # 1. Reconocer la interacción inmediatamente
                await sel_interaction.response.defer(ephemeral=True)
                
                zona = sel_interaction.values[0]
                user_mention = sel_interaction.user.mention
                canal = sel_interaction.channel

                if zona != "Retirarse":
                    # Verificar si está ocupada por otro
                    if RADAR_DESPLIEGUE.get(zona) is not None and RADAR_DESPLIEGUE.get(zona) != user_mention:
                        return await sel_interaction.followup.send(f"❌ La posición **{zona}** ya está ocupada por {RADAR_DESPLIEGUE[zona]}.", ephemeral=True)
                    
                    # Limpiar al usuario de cualquier otra zona que tuviera
                    for z, miembro in list(RADAR_DESPLIEGUE.items()):
                        if miembro == user_mention:
                            RADAR_DESPLIEGUE[z] = None
                    
                    # Asignar nueva zona
                    RADAR_DESPLIEGUE[zona] = user_mention
                    await sel_interaction.followup.send(f"✅ Desplegado en **{zona}**.", ephemeral=True)
                else:
                    # Salir del servicio
                    for z, miembro in list(RADAR_DESPLIEGUE.items()):
                        if miembro == user_mention:
                            RADAR_DESPLIEGUE[z] = None
                    await sel_interaction.followup.send("❌ Has salido del servicio.", ephemeral=True)

                # Actualizar el mapa en el canal
                await actualizar_radar_en_canal(canal)
                
            except Exception as e:
                error_msg = f"🚨 ERROR: {type(e).__name__}: {e}"
                print(error_msg)
                try:
                    await sel_interaction.followup.send(f"❌ {error_msg}", ephemeral=True)
                except:
                    pass

        select.callback = select_callback
        view.add_item(select)
        await interaction.response.send_message("Selecciona tu zona:", view=view, ephemeral=True)

    @discord.ui.button(label="🧹 Resetear Radar", style=discord.ButtonStyle.danger, custom_id="radar:reset")
    async def resetear_radar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ResetPasswordModal())

class ResetPasswordModal(discord.ui.Modal, title="🔐 Autorización de Reset"):
    password_input = discord.ui.TextInput(label="Clave de Reset", style=discord.TextStyle.short, placeholder="Clave de administrador...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        config = cargar_config_general()
        clave_correcta = config.get('CLAVE_RESET', 'admin')
        
        if self.password_input.value == clave_correcta:
            await interaction.response.defer(ephemeral=True)
            canal = interaction.channel
            responsable = interaction.user.mention
            
            mapa_antes = generar_mapa_texto()
            historial = (
                f"🧹 **HISTORIAL: RADAR RESET MANUAL**\n"
                f"👤 **Responsable:** {responsable}\n"
                f"📅 **Fecha:** {datetime.datetime.now(datetime.timezone.utc).strftime('%d/%m/%Y %H:%M:%S')} UTC\n"
                f"🗄️ **Estado archivado:**\n{mapa_antes}"
            )
            
            global ultimo_radar_message_id
            if ultimo_radar_message_id:
                try:
                    msg_viejo = await canal.fetch_message(ultimo_radar_message_id)
                    await msg_viejo.delete()
                except: pass

            await canal.send(historial)
            for zona in RADAR_DESPLIEGUE:
                RADAR_DESPLIEGUE[zona] = None
            
            nuevo_mapa = generar_mapa_texto()
            nuevo_msg = await canal.send(content=nuevo_mapa, view=RadarControlView())
            ultimo_radar_message_id = nuevo_msg.id
            await interaction.followup.send("✅ Radar reseteado y archivado.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ **Clave incorrecta.** Acción denegada.", ephemeral=True)

async def actualizar_radar_en_canal(canal):
    global ultimo_radar_message_id
    if ultimo_radar_message_id:
        try:
            msg_viejo = await canal.fetch_message(ultimo_radar_message_id)
            await msg_viejo.delete()
        except: pass
    nuevo_mapa = generar_mapa_texto()
    nuevo_msg = await canal.send(content=nuevo_mapa, view=RadarControlView())
    ultimo_radar_message_id = nuevo_msg.id

async def ejecutar_radar(message):
    global ultimo_radar_message_id, canal_radar_id, radar_abierto_al_publico
    canal_radar_id = message.channel.id
    
    # FORZAR APERTURA MANUAL PARA TESTEO
    radar_abierto_al_publico = True

    if ultimo_radar_message_id:
        try:
            msg_viejo = await message.channel.fetch_message(ultimo_radar_message_id)
            await msg_viejo.delete()
        except: pass

    cargar_zonas()
    nuevo_mapa = generar_mapa_texto()
    nuevo_msg = await message.channel.send(content=nuevo_mapa, view=RadarControlView())
    ultimo_radar_message_id = nuevo_msg.id
    
# ==========================================
# 6. COMANDOS SLASH
# ==========================================
@bot.tree.command(name="ayuda", description="Menú interactivo de normas, vestimenta y ayuda")
async def ayuda_slash(interaction: discord.Interaction):
    view = MainMenuView()
    await interaction.response.send_message("👋 **SISTEMA DE AYUDA JINETES MC**\nSelecciona una opción del menú desplegable:", view=view, ephemeral=True)

@bot.tree.command(name="radar", description="Desplegar la Central de Operaciones")
async def radar_slash(interaction: discord.Interaction):
    global ultimo_radar_message_id, canal_radar_id, radar_abierto_al_publico
    canal_radar_id = interaction.channel.id
    
    # FORZAR APERTURA MANUAL PARA TESTEO
    radar_abierto_al_publico = True

    if ultimo_radar_message_id:
        try:
            msg_viejo = await interaction.channel.fetch_message(ultimo_radar_message_id)
            await msg_viejo.delete()
        except: pass

    await interaction.response.send_message("🔄 Sincronizando central...", ephemeral=True)
    cargar_zonas()
    
    nuevo_mapa = generar_mapa_texto()
    nuevo_msg = await interaction.channel.send(content=nuevo_mapa, view=RadarControlView())
    ultimo_radar_message_id = nuevo_msg.id

# ==========================================
# 7. COMANDOS DE PREFIJO
# ==========================================
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    if not message.content.startswith(PREFIX):
        return

    args = message.content[len(PREFIX):].strip().split()
    if not args:
        return

    comando_nombre = args[0].lower()
    
    if comando_nombre in COMANDOS_CONFIG:
        config = COMANDOS_CONFIG[comando_nombre]
        if str(config.get('Activo', '')).upper() == 'SI':
            funcion = config.get('Funcion', '')
            
            if funcion == 'menu_ayuda':
                await ejecutar_menu_ayuda(message)
            elif funcion == 'radar_geto':
                await ejecutar_radar(message)

# ==========================================
# 8. CRONOGRAMA RADAR
# ==========================================

@tasks.loop(seconds=30)
async def verificador_tiempo_radar():
    global radar_abierto_al_publico, ultimo_radar_message_id, canal_radar_id
    
    if not canal_radar_id:
        config = cargar_config_general()
        canal_id_str = config.get('CANAL_RADAR_ID', '')
        if canal_id_str:
            canal_radar_id = int(canal_id_str)
        else:
            return

    ahora = datetime.datetime.now(datetime.timezone.utc)
    dia_semana = ahora.weekday()
    hora = ahora.hour
    minuto = ahora.minute

    if dia_semana in DIAS_ACTIVIDAD:
        # APERTURA: Verificar si estamos dentro del rango de apertura
        for h in HORAS_ACTIVIDAD:
            h_apertura = h - 1 if h > 0 else 23
            
            # Si es la hora de apertura y estamos en los primeros 5 minutos
            if hora == h_apertura and minuto < 5 and not radar_abierto_al_publico:
                radar_abierto_al_publico = True
                try:
                    canal = bot.get_channel(canal_radar_id)
                    if canal:
                        await canal.send(f"🔓 **[SISTEMA]:** Posiciones abiertas para la actividad de las **{h}:00 UTC**. ¡Asignen zonas!")
                        await actualizar_radar_en_canal(canal)
                except Exception as e:
                    print(f"Error al abrir radar: {e}")
                break
        
        # CIERRE: 5 minutos después de la hora de actividad
        for h in HORAS_ACTIVIDAD:
            if hora == h and minuto == 5:
                if radar_abierto_al_publico or any(RADAR_DESPLIEGUE.values()):
                    radar_abierto_al_publico = False
                    try:
                        canal = bot.get_channel(canal_radar_id)
                        if canal:
                            mapa_final = generar_mapa_texto()
                            bitacora = (
                                f"🗃️ **ARCHIVO DE OPERACIONES AUTOMÁTICO**\n"
                                f"📅 **Fecha:** {ahora.strftime('%d/%m/%Y')}\n"
                                f"⏱️ **Actividad:** {h}:00 UTC\n"
                                f"🔒 **Estado:** Cuadrante Bloqueado\n"
                                f"📋 **Despliegue Final:**\n{mapa_final}"
                            )
                            await canal.send(bitacora)
                            for zona in RADAR_DESPLIEGUE:
                                RADAR_DESPLIEGUE[zona] = None
                            await actualizar_radar_en_canal(canal)
                    except Exception as e:
                        print(f"Error al cerrar radar: {e}")
                    break

# ==========================================
# 9. PING MANTENIMIENTO
# ==========================================
@tasks.loop(minutes=5)
async def ping_keeping_alive():
    try:
        if bot.is_ready():
            print(f"💓 Ping - Bot conectado. Latencia: {round(bot.latency * 1000)}ms")
        else:
            print("⚠️ Ping - Bot NO está listo")
    except Exception as e:
        print(f"Error en ping: {e}")

# ==========================================
# 10. SERVIDOR WEB + RECONEXIÓN
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

# Bucle principal con reconexión automática
while True:
    try:
        bot.run(os.getenv("DISCORD_TOKEN"), reconnect=True)
    except Exception as e:
        print(f"Error fatal: {e}. Reintentando en 30 segundos...")
        time.sleep(30)
