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
import sys
import io
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. CONEXIÓN A GOOGLE SHEETS
# ==========================================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/creds.json", scope)
client_gsheet = gspread.authorize(creds)

SPREADSHEET_NAME = "jinetesmc"
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
sheet_recluta_general = spreadsheet.worksheet("Config_Recluta_General")
sheet_recluta_preguntas = spreadsheet.worksheet("Config_Recluta_Preguntas")
sheet_registro_reclutas = spreadsheet.worksheet("Registro_Reclutas")

# ==========================================
# 2. VARIABLES GLOBALES Y CACHÉ
# ==========================================
RADAR_DESPLIEGUE = {}
ultimo_radar_message_id = None
canal_radar_id = None
radar_abierto_al_publico = False
COMANDOS_CONFIG = {}
PREFIX = "-"

CACHE_ZONAS = []
CACHE_MENU = []
CACHE_SUB = []
CACHE_CONTENIDO = []
CACHE_CONFIG = {}
CACHE_RECLUTAMIENTO = {}
PREGUNTAS_RECLUTAMIENTO = []

def cargar_config_general():
    global CACHE_CONFIG
    if not CACHE_CONFIG:
        records = sheet_general.get_all_records()
        for row in records:
            clave = next((k for k in row.keys() if 'clave' in k.lower()), None)
            valor = next((k for k in row.keys() if 'valor' in k.lower()), None)
            if clave and valor:
                CACHE_CONFIG[str(row[clave])] = str(row[valor])
    return CACHE_CONFIG

def cargar_zonas():
    global CACHE_ZONAS, RADAR_DESPLIEGUE
    if not CACHE_ZONAS:
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

def cargar_config_reclutamiento():
    global CACHE_RECLUTAMIENTO
    if not CACHE_RECLUTAMIENTO:
        records = sheet_recluta_general.get_all_records()
        for row in records:
            clave = next((k for k in row.keys() if 'clave' in k.lower()), None)
            valor = next((k for k in row.keys() if 'valor' in k.lower()), None)
            if clave and valor:
                CACHE_RECLUTAMIENTO[str(row[clave])] = str(row[valor])
    return CACHE_RECLUTAMIENTO

def cargar_preguntas_reclutamiento():
    global PREGUNTAS_RECLUTAMIENTO
    records = sheet_recluta_preguntas.get_all_records()
    preguntas = [r for r in records if str(r.get('Orden', '')).isdigit() and int(r.get('Orden', 0)) > 0]
    preguntas.sort(key=lambda x: int(x.get('Orden', 0)))
    PREGUNTAS_RECLUTAMIENTO = preguntas
    return PREGUNTAS_RECLUTAMIENTO

# Carga inicial
CONFIG_RECLUTAMIENTO = cargar_config_reclutamiento()
cargar_preguntas_reclutamiento()
CONFIG_RADAR = cargar_config_general()
cargar_zonas()
DIAS_ACTIVIDAD, HORAS_ACTIVIDAD = cargar_horarios()
cargar_comandos()

# ==========================================
# 3. BOT Y EVENTOS
# ==========================================
intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    sys.stdout.write("🚀 " + "="*50 + "\n")
    sys.stdout.write(f"✅ Bot Jinetes MC CONECTADO\n")
    sys.stdout.write(f"👤 Usuario: {bot.user.name} (ID: {bot.user.id})\n")
    sys.stdout.write(f"📌 Prefijo: '{PREFIX}'\n")
    sys.stdout.write("🚀 " + "="*50 + "\n")
    sys.stdout.flush()
    
    try:
        await bot.tree.sync()
        sys.stdout.write("✅ Comandos slash sincronizados.\n")
        sys.stdout.flush()
    except Exception as e:
        sys.stdout.write(f"🚨 Error en sync: {e}\n")
        sys.stdout.flush()

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

@bot.event
async def on_guild_channel_create(channel):
    sys.stdout.write(f"🔔 [CANAL CREADO] Nombre: '{channel.name}'\n")
    sys.stdout.flush()
    
    if isinstance(channel, discord.TextChannel) and "ticket" in channel.name.lower():
        sys.stdout.write(f"✅ ¡ES UN TICKET! Buscando usuario real...\n")
        sys.stdout.flush()
        
        await asyncio.sleep(4)
        usuario_creador = None
        
        try:
            async for message in channel.history(limit=5):
                if message.mentions:
                    for user in message.mentions:
                        if not user.bot:
                            usuario_creador = user
                            sys.stdout.write(f"👤 Usuario encontrado por mención: {usuario_creador.name}\n")
                            sys.stdout.flush()
                            break
                if usuario_creador:
                    break
        except Exception as e:
            sys.stdout.write(f"⚠️ Error buscando menciones: {e}\n")
            sys.stdout.flush()

        if not usuario_creador:
            try:
                async for message in channel.history(limit=10):
                    if not message.author.bot:
                        usuario_creador = message.author
                        sys.stdout.write(f"👤 Usuario encontrado por historial: {usuario_creador.name}\n")
                        sys.stdout.flush()
                        break
            except Exception as e:
                sys.stdout.write(f"⚠️ Error buscando historial: {e}\n")
                sys.stdout.flush()

        if usuario_creador:
            sys.stdout.write(f"📩 Enviando bienvenida a {usuario_creador.name}...\n")
            sys.stdout.flush()
            await enviar_bienvenida_recluta(channel, usuario_creador)
            sys.stdout.write(f"✅ ¡Bienvenida enviada correctamente!\n")
            sys.stdout.flush()
        else:
            sys.stdout.write(f"❌ No se pudo identificar al usuario real. Usa /recluta @usuario manualmente.\n")
            sys.stdout.flush()

@bot.event
async def on_thread_create(thread):
    sys.stdout.write(f"🧵 [HILO CREADO] Nombre: '{thread.name}'\n")
    sys.stdout.flush()
    if "ticket" in thread.name.lower():
        sys.stdout.write(f"✅ ¡ES UN HILO DE TICKET! Procesando...\n")
        sys.stdout.flush()
        await asyncio.sleep(3)
        try:
            async for message in thread.history(limit=10):
                if not message.author.bot:
                    sys.stdout.write(f"👤 Usuario encontrado en hilo: {message.author.name}\n")
                    sys.stdout.flush()
                    await enviar_bienvenida_recluta(thread, message.author)
                    break
        except Exception as e:
            sys.stdout.write(f"🚨 Error al procesar hilo: {e}\n")
            sys.stdout.flush()

# ==========================================
# 4. MENÚS Y BÚSQUEDA
# ==========================================
def obtener_hoja_busqueda(nombre_hoja):
    mapeo = {"Reglas_Buscable": sheet_busq_reglas, "Vestimenta_Buscable": sheet_busq_vestimenta}
    return mapeo.get(nombre_hoja, sheet_busq_reglas)

class SearchModal(discord.ui.Modal):
    def __init__(self, categoria_nombre, hoja_nombre):
        super().__init__(title=f"🔍 Buscar en {categoria_nombre}")
        self.query_input = discord.ui.TextInput(label="Término de búsqueda", placeholder="Ej: armas, respawn...", required=True, max_length=50)
        self.hoja_nombre = hoja_nombre
        self.categoria_nombre = categoria_nombre

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        query = self.query_input.value.lower()
        hoja = obtener_hoja_busqueda(self.hoja_nombre)
        try:
            records = hoja.get_all_records()
            resultados = [" ".join([str(v) for v in r.values() if v]) for r in records if query in " ".join([str(v) for v in r.values() if v]).lower()]
            if not resultados:
                return await interaction.followup.send(f"❌ No se encontraron resultados para '**{query}**'.")
            embed = discord.Embed(title=f"🔍 Resultados para '{query}'", color=discord.Color.blue())
            for i, res in enumerate(resultados[:5], 1):
                embed.add_field(name=f"Coincidencia {i}", value=res, inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error al buscar: {e}", ephemeral=True)

class MainMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.build_menu()

    def build_menu(self):
        global CACHE_MENU
        if not CACHE_MENU: CACHE_MENU = sheet_menu.get_all_records()
        records = CACHE_MENU
        items = [r for r in records if str(r.get('Estado', '')) in ['1', '2']]
        items.sort(key=lambda x: int(x.get('Orden', 0)))
        options = [discord.SelectOption(label=item['Nombre'], value=f"{item['ID']}|{str(item.get('Estado', ''))}", emoji=item.get('Emoji')) for item in items]
        
        if options:
            select = discord.ui.Select(placeholder="📂 Selecciona una categoría...", options=options)
            async def select_callback(interaction: discord.Interaction):
                item_id, estado = select.values[0].split('|')
                item_data = next((r for r in records if r['ID'] == item_id), None)
                nombre_categoria = item_data['Nombre'] if item_data else "Categoría"
                if estado == '2':
                    global CACHE_SUB
                    if not CACHE_SUB: CACHE_SUB = sheet_sub.get_all_records()
                    sub_busqueda = next((s for s in CACHE_SUB if s.get('Categoria_Padre') == item_id and str(s.get('Tipo', '')) == '2'), None)
                    hoja = sub_busqueda.get('Hoja_Busqueda') if sub_busqueda else "Reglas_Buscable"
                    return await interaction.response.send_modal(SearchModal(nombre_categoria, hoja))
                await self.show_subcategories(interaction, item_id, nombre_categoria)
            select.callback = select_callback
            self.add_item(select)

    async def show_subcategories(self, interaction: discord.Interaction, parent_id, parent_name):
        global CACHE_SUB, CACHE_CONTENIDO
        if not CACHE_SUB: CACHE_SUB = sheet_sub.get_all_records()
        if not CACHE_CONTENIDO: CACHE_CONTENIDO = sheet_contenido.get_all_records()
        subs = [r for r in CACHE_SUB if r.get('Categoria_Padre') == parent_id]
        subs.sort(key=lambda x: int(x.get('Orden', 0)))
        view = discord.ui.View(timeout=180)
        options = [discord.SelectOption(label=sub['Nombre'], value=f"{sub['ID']}|{str(sub.get('Tipo', ''))}|{sub.get('Hoja_Busqueda', '')}", emoji="🔹") for sub in subs]
        select_sub = discord.ui.Select(placeholder=f"📂 Subcategorías de {parent_name}...", options=options)
        
        async def sub_callback(sub_interaction: discord.Interaction):
            sub_id, tipo, hoja_busqueda = select_sub.values[0].split('|')
            if tipo == '2':
                sub_data = next((r for r in CACHE_SUB if r['ID'] == sub_id), None)
                return await sub_interaction.response.send_modal(SearchModal(sub_data['Nombre'] if sub_data else "Búsqueda", hoja_busqueda))
            contenido = next((c for c in CACHE_CONTENIDO if c.get('ID_Subcategoria') == sub_id), None)
            if not contenido:
                return await sub_interaction.response.send_message("⚠️ Esta categoría no tiene contenido.", ephemeral=True)
            embed = discord.Embed(title=contenido.get('Titulo', ''), description=contenido.get('Contenido', ''), color=discord.Color.green())
            if contenido.get('Imagen', '') and str(contenido.get('Imagen', '')).startswith('http'):
                embed.set_image(url=contenido.get('Imagen', ''))
            await sub_interaction.response.send_message(embed=embed, ephemeral=True)
        select_sub.callback = sub_callback
        view.add_item(select_sub)
        await interaction.response.send_message(f"📂 Has seleccionado: **{parent_name}**", view=view, ephemeral=True)

async def ejecutar_menu_ayuda(message):
    await message.channel.send("👋 **SISTEMA DE AYUDA JINETES MC**\nSelecciona una opción del menú desplegable:", view=MainMenuView())

# ==========================================
# 5. RADAR
# ==========================================
def generar_mapa_texto():
    config = cargar_config_general()
    estado = config.get('MENSAJE_ABIERTO', '🟢 ACTIVO') if radar_abierto_al_publico else config.get('MENSAJE_CERRADO', '🔴 EN ESPERA')
    lineas_zonas = []
    for zona, usuario in RADAR_DESPLIEGUE.items():
        emoji = next((r.get('Emoji', '📍') for r in CACHE_ZONAS if r.get('Zona') == zona), '📍')
        lineas_zonas.append(f"  • {emoji} {zona.ljust(15)} {usuario if usuario else '[ VACÍO ] ⚠️'}")
    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f" {config.get('TITULO_RADAR', '🏍️ JINETES MC • RADAR DE ZONAS')}\n"
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
            return await interaction.response.send_message("❌ El radar está cerrado.", ephemeral=True)
        opciones = [discord.SelectOption(label=zona, value=zona) for zona in RADAR_DESPLIEGUE.keys()]
        opciones.append(discord.SelectOption(label="🚪 Salir de Servicio", value="Retirarse"))
        view = discord.ui.View(timeout=60)
        select = discord.ui.Select(placeholder="📍 Elige tu punto de despliegue...", options=opciones)
        
        async def select_callback(sel_interaction: discord.Interaction):
            await sel_interaction.response.defer(ephemeral=True)
            zona = sel_interaction.data['values'][0]
            user_mention = sel_interaction.user.mention
            if zona != "Retirarse":
                if RADAR_DESPLIEGUE.get(zona) is not None and RADAR_DESPLIEGUE.get(zona) != user_mention:
                    return await sel_interaction.followup.send(f"❌ La posición **{zona}** ya está ocupada.", ephemeral=True)
                for z, miembro in list(RADAR_DESPLIEGUE.items()):
                    if miembro == user_mention: RADAR_DESPLIEGUE[z] = None
                RADAR_DESPLIEGUE[zona] = user_mention
                await sel_interaction.followup.send(f"✅ Desplegado en **{zona}**.", ephemeral=True)
            else:
                for z, miembro in list(RADAR_DESPLIEGUE.items()):
                    if miembro == user_mention: RADAR_DESPLIEGUE[z] = None
                await sel_interaction.followup.send("❌ Has salido del servicio.", ephemeral=True)
            await actualizar_radar_en_canal(sel_interaction.channel)
        select.callback = select_callback
        view.add_item(select)
        await interaction.response.send_message("Selecciona tu zona:", view=view, ephemeral=True)

    @discord.ui.button(label="🧹 Resetear Radar", style=discord.ButtonStyle.danger, custom_id="radar:reset")
    async def resetear_radar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ResetPasswordModal())

class ResetPasswordModal(discord.ui.Modal, title="🔐 Autorización de Reset"):
    password_input = discord.ui.TextInput(label="Clave de Reset", style=discord.TextStyle.short, placeholder="Clave de administrador...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        global ultimo_radar_message_id  # <-- DEBE IR AL PRINCIPIO ABSOLUTO DE LA FUNCIÓN
        
        if self.password_input.value == cargar_config_general().get('CLAVE_RESET', 'admin'):
            await interaction.response.defer(ephemeral=True)
            canal = interaction.channel
            mapa_antes = generar_mapa_texto()
            
            if ultimo_radar_message_id:
                try:
                    msg_viejo = await canal.fetch_message(ultimo_radar_message_id)
                    await msg_viejo.delete()
                except: pass
                
            await canal.send(f"🧹 **HISTORIAL: RADAR RESET MANUAL**\n👤 **Responsable:** {interaction.user.mention}\n🗄️ **Estado archivado:**\n{mapa_antes}")
            
            for zona in RADAR_DESPLIEGUE: 
                RADAR_DESPLIEGUE[zona] = None
                
            nuevo_msg = await canal.send(content=generar_mapa_texto(), view=RadarControlView())
            ultimo_radar_message_id = nuevo_msg.id
            
            await interaction.followup.send("✅ Radar reseteado.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ **Clave incorrecta.**", ephemeral=True)

async def actualizar_radar_en_canal(canal):
    global ultimo_radar_message_id
    if ultimo_radar_message_id:
        try:
            msg_viejo = await canal.fetch_message(ultimo_radar_message_id)
            await msg_viejo.delete()
        except: pass
    nuevo_msg = await canal.send(content=generar_mapa_texto(), view=RadarControlView())
    ultimo_radar_message_id = nuevo_msg.id

async def ejecutar_radar(message):
    global ultimo_radar_message_id, canal_radar_id, radar_abierto_al_publico
    canal_radar_id = message.channel.id
    radar_abierto_al_publico = True
    if ultimo_radar_message_id:
        try:
            msg_viejo = await message.channel.fetch_message(ultimo_radar_message_id)
            await msg_viejo.delete()
        except: pass
    cargar_zonas()
    nuevo_msg = await message.channel.send(content=generar_mapa_texto(), view=RadarControlView())
    ultimo_radar_message_id = nuevo_msg.id

# ==========================================
# 6. COMANDOS SLASH Y RECLUTAMIENTO
# ==========================================
@bot.tree.command(name="recluta", description="Enviar formulario de ingreso manualmente en un ticket")
async def recluta_manual(interaction: discord.Interaction, usuario: discord.Member):
    config = cargar_config_reclutamiento()
    es_ticket = False
    if config.get('CATEGORIA_TICKETS_ID', '') and interaction.channel.category_id:
        if str(interaction.channel.category_id) == config.get('CATEGORIA_TICKETS_ID', ''): es_ticket = True
    if not es_ticket and interaction.channel.name.lower().startswith('ticket-'): es_ticket = True
    if not es_ticket: return await interaction.response.send_message("❌ Este comando solo funciona en canales de ticket.", ephemeral=True)
    await interaction.response.send_message("🔄 Enviando bienvenida...", ephemeral=True)
    await enviar_bienvenida_recluta(interaction.channel, usuario)
    await interaction.followup.send(f"✅ Bienvenida enviada a {usuario.mention}", ephemeral=True)

@bot.tree.command(name="ayuda", description="Menú interactivo de normas, vestimenta y ayuda")
async def ayuda_slash(interaction: discord.Interaction):
    await interaction.response.send_message("👋 **SISTEMA DE AYUDA JINETES MC**\nSelecciona una opción del menú desplegable:", view=MainMenuView(), ephemeral=True)

@bot.tree.command(name="radar", description="Desplegar la Central de Operaciones")
async def radar_slash(interaction: discord.Interaction):
    global ultimo_radar_message_id, canal_radar_id, radar_abierto_al_publico
    canal_radar_id = interaction.channel.id
    radar_abierto_al_publico = True
    if ultimo_radar_message_id:
        try:
            msg_viejo = await interaction.channel.fetch_message(ultimo_radar_message_id)
            await msg_viejo.delete()
        except: pass
    await interaction.response.send_message("🔄 Sincronizando central...", ephemeral=True)
    cargar_zonas()
    nuevo_msg = await interaction.channel.send(content=generar_mapa_texto(), view=RadarControlView())
    ultimo_radar_message_id = nuevo_msg.id

# ==========================================
# 7. LÓGICA DE RECLUTAMIENTO (MODALES Y EXCEL)
# ==========================================
def guardar_recluta_en_excel(usuario, canal, respuestas_completas):
    try:
        ahora = datetime.datetime.now(datetime.timezone.utc)
        fila = [ahora.strftime('%d/%m/%Y %H:%M'), usuario.display_name, str(usuario.id), canal.name if canal else 'Desconocido', 'Pendiente']
        for pregunta_texto, respuesta_texto in respuestas_completas:
            fila.append(respuesta_texto)
        sheet_registro_reclutas.append_row(fila, value_input_option='USER_ENTERED')
        print(f"✅ Recluta guardado en Excel: {usuario.display_name}")
        return True
    except Exception as e:
        print(f"🚨 Error al guardar en Excel: {e}")
        return False

class FormularioReclutaModal(discord.ui.Modal):
    def __init__(self, preguntas, pagina_actual, total_paginas, respuestas_previas=None):
        self.pagina_actual = pagina_actual
        self.total_paginas = total_paginas
        self.respuestas_previas = respuestas_previas or []
        super().__init__(title=f"Solicitud ({pagina_actual}/{total_paginas})")
        for i, p in enumerate(preguntas):
            try:
                pregunta = str(p.get('Pregunta', f'Pregunta {i+1}'))
                placeholder = str(p.get('Placeholder', 'Escribe tu respuesta...'))
                obligatoria = str(p.get('Obligatoria', 'NO')).upper() == 'SI'
                estilo = discord.TextStyle.paragraph if any(palabra in pregunta.lower() for palabra in ['larga', 'motivación', 'experiencia', 'historia', 'backstory', 'por qué', 'detalla', 'describe']) else discord.TextStyle.short
                pregunta_limpia = pregunta.rstrip('*').strip()[:37] + ("..." if len(pregunta) > 40 else "")
                label_final = f"{pregunta_limpia}{'*' if obligatoria else ''}"
                placeholder = (placeholder.strip() or 'Escribe aquí...')[:100]
                self.add_item(discord.ui.TextInput(label=label_final, placeholder=placeholder, required=obligatoria, style=estilo, max_length=4000 if estilo == discord.TextStyle.paragraph else 100))
            except Exception as e:
                print(f"❌ Error en campo {i}: {e}")
                self.add_item(discord.ui.TextInput(label=f"Pregunta {i+1}", placeholder="Escribe aquí...", required=False, style=discord.TextStyle.short, max_length=100))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            respuestas_pagina = [(child.label.rstrip(' *').strip(), child.value) for child in self.children]
            todas_las_respuestas = self.respuestas_previas + respuestas_pagina
            if self.pagina_actual < self.total_paginas:
                siguiente_pagina = self.pagina_actual + 1
                preguntas_siguientes = PREGUNTAS_RECLUTAMIENTO[(siguiente_pagina - 1) * 5 : siguiente_pagina * 5]
                await interaction.response.send_modal(FormularioReclutaModal(preguntas_siguientes, siguiente_pagina, self.total_paginas, todas_las_respuestas))
            else:
                await interaction.response.defer(ephemeral=True)
                await construir_y_enviar_embed(interaction, todas_las_respuestas)
        except Exception as e:
            print(f"🚨 ERROR EN MODAL: {e}")
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

async def construir_y_enviar_embed(interaction, todas_las_respuestas):
    config = cargar_config_reclutamiento()
    preguntas = cargar_preguntas_reclutamiento()
    embed = discord.Embed(title="📋 SOLICITUD DE INGRESO", color=discord.Color.gold())
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()
    titulo_personalizado, descripcion_partes, campos = None, [], []
    for (pregunta_texto, respuesta_texto), pregunta_config in zip(todas_las_respuestas, preguntas):
        ubicacion = str(pregunta_config.get('Ubicacion', 'CAMPO')).upper()
        estilo = str(pregunta_config.get('Estilo', 'Normal')).lower()
        if estilo == 'negrita': respuesta_texto = f"**{respuesta_texto}**"
        elif estilo == 'cursiva': respuesta_texto = f"*{respuesta_texto}*"
        elif estilo == 'negrita y cursiva': respuesta_texto = f"***{respuesta_texto}***"
        if ubicacion == 'TITULO': titulo_personalizado = respuesta_texto
        elif ubicacion == 'DESCRIPCION': descripcion_partes.append(respuesta_texto)
        else: campos.append((pregunta_texto, respuesta_texto))
    if titulo_personalizado: embed.title = f"📋 SOLICITUD: {titulo_personalizado}"
    if descripcion_partes: embed.description = "\n".join(descripcion_partes)
    for nombre, valor in campos: embed.add_field(name=nombre, value=valor, inline=False)
    
    await interaction.channel.send(embed=embed)
    for canal_id_str in config.get('CANALES_LOG_RECLUTAS', '').split(','):
        try:
            canal_log = bot.get_channel(int(canal_id_str.strip()))
            if canal_log: await canal_log.send(embed=embed)
        except: pass
    if titulo_personalizado:
        try: await interaction.channel.edit(name=f"solicitud-{str(titulo_personalizado).lower().replace(' ', '-')[:20]}")
        except: pass
    guardar_recluta_en_excel(interaction.user, interaction.channel, todas_las_respuestas)
    await interaction.followup.send("✅ **Solicitud enviada correctamente.** Un administrador la revisará pronto.", ephemeral=True)

class BienvenidaReclutaView(discord.ui.View):
    def __init__(self, usuario):
        super().__init__(timeout=None)
        self.usuario = usuario
    @discord.ui.button(label="📝 Rellenar solicitud de ingreso", style=discord.ButtonStyle.primary, custom_id="recluta:formulario")
    async def abrir_formulario(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.usuario: return await interaction.response.send_message("❌ Este formulario es solo para el usuario mencionado.", ephemeral=True)
        preguntas = cargar_preguntas_reclutamiento()
        if not preguntas: return await interaction.response.send_message("❌ No hay preguntas configuradas.", ephemeral=True)
        await interaction.response.send_modal(FormularioReclutaModal(preguntas[:5], 1, (len(preguntas) + 4) // 5))

async def enviar_bienvenida_recluta(canal, usuario):
    config = cargar_config_reclutamiento()
    await canal.send(content=config.get('MENSAJE_BIENVENIDA', '¡Bienvenido {user}!').replace('{user}', usuario.mention), view=BienvenidaReclutaView(usuario))

# ==========================================
# 8. GENERADOR DE CARNET (NUEVO)
# ==========================================
def buscar_ficha_usuario(user_id):
    try:
        records = sheet_registro_reclutas.get_all_records()
        for row in records:
            if str(row.get('ID_Usuario', '')) == str(user_id):
                return row
        return None
    except Exception as e:
        print(f"🚨 Error buscando ficha: {e}")
        return None

def generar_carnet_imagen(datos):
    try:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        ruta_plantilla = os.path.join(BASE_DIR, "plantilla_carnet.png")
        ruta_fuente = os.path.join(BASE_DIR, "fuente.ttf")
        
        print(f"📂 Ruta plantilla: {ruta_plantilla}")
        print(f"📂 Ruta fuente: {ruta_fuente}")
        print(f" DATOS RECIBIDOS DEL EXCEL: {list(datos.keys())}")
        
        img = Image.open(ruta_plantilla)
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(ruta_fuente, 36)
        font_pequeno = ImageFont.truetype(ruta_fuente, 28)
        color_texto = (255, 255, 255)
        
        # Extraer datos con múltiples intentos de claves
        nombre_ic = str(datos.get('¿Cuál es tu nombre IC?', datos.get('[Pregunta 1]', datos.get('Nombre', 'TEST_NOMBRE'))))
        id_usuario = str(datos.get('ID_Usuario', '000000'))
        fecha_completa = str(datos.get('Fecha', '01/01/2026 00:00'))
        nivel = str(datos.get('Nivel', datos.get('[Pregunta 2]', datos.get('Edad OOC', '0'))))
        pais = str(datos.get('Pais que conectas', datos.get('[Pregunta 8]', datos.get('País', 'TEST_PAIS'))))
        
        print(f"👤 Nombre IC extraído: '{nombre_ic}'")
        print(f"🔢 ID Usuario: '{id_usuario}'")
        print(f"📅 Fecha: '{fecha_completa}'")
        print(f"🎮 Nivel: '{nivel}'")
        print(f"🌍 País: '{pais}'")
        
        fecha_solo = fecha_completa.split(' ')[0] if ' ' in fecha_completa else fecha_completa
        nr_formateado = f"#{id_usuario}"
        
        # Coordenadas ajustadas (imagen 1024x1024)
        X_ALINEADO = 720
        
        print(f" Dibujando texto en X={X_ALINEADO}")
        
        draw.text((X_ALINEADO, 340), nombre_ic, fill=color_texto, font=font)
        draw.text((X_ALINEADO, 440), nr_formateado, fill=color_texto, font=font)
        draw.text((X_ALINEADO, 530), fecha_solo, fill=color_texto, font=font_pequeno)
        draw.text((X_ALINEADO, 620), nivel, fill=color_texto, font=font)
        draw.text((X_ALINEADO, 710), pais, fill=color_texto, font=font_pequeno)
        
        print("✅ Texto dibujado, guardando imagen...")
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        return img_byte_arr
    except Exception as e:
        print(f"🚨 Error generando imagen: {e}")
        import traceback
        traceback.print_exc()
        return None
@bot.tree.command(name="carnet", description="Generar carnet oficial del miembro")
async def carnet_comando(interaction: discord.Interaction, usuario: discord.Member):
    await interaction.response.defer()
    datos = buscar_ficha_usuario(usuario.id)
    if not datos:
        return await interaction.followup.send(f"❌ **{usuario.mention}** no tiene ficha registrada en la base de datos.")
    img_bytes = generar_carnet_imagen(datos)
    if not img_bytes:
        return await interaction.followup.send("🚨 Hubo un error al generar la imagen. Asegúrate de que `plantilla_carnet.png` y `fuente.ttf` estén en GitHub.")
    archivo = discord.File(img_bytes, filename=f"carnet_{usuario.name}.png")
    await interaction.followup.send(f"🪪 **Carnet oficial de {usuario.mention}**", file=archivo)

# ==========================================
# 9. COMANDOS DE PREFIJO Y CRONOGRAMA
# ==========================================
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
            if funcion == 'menu_ayuda': await ejecutar_menu_ayuda(message)
            elif funcion == 'radar_geto': await ejecutar_radar(message)

@tasks.loop(seconds=30)
async def verificador_tiempo_radar():
    global radar_abierto_al_publico, ultimo_radar_message_id, canal_radar_id
    if not canal_radar_id:
        canal_id_str = cargar_config_general().get('CANAL_RADAR_ID', '')
        if canal_id_str: canal_radar_id = int(canal_id_str)
        else: return
    ahora = datetime.datetime.now(datetime.timezone.utc)
    if ahora.weekday() in DIAS_ACTIVIDAD:
        for h in HORAS_ACTIVIDAD:
            h_apertura = h - 1 if h > 0 else 23
            if ahora.hour == h_apertura and ahora.minute < 5 and not radar_abierto_al_publico:
                radar_abierto_al_publico = True
                try:
                    canal = bot.get_channel(canal_radar_id)
                    if canal:
                        await canal.send(f"🔓 **[SISTEMA]:** Posiciones abiertas para la actividad de las **{h}:00 UTC**. ¡Asignen zonas!")
                        await actualizar_radar_en_canal(canal)
                except Exception as e: print(f"Error al abrir radar: {e}")
                break
        for h in HORAS_ACTIVIDAD:
            if ahora.hour == h and ahora.minute == 5:
                if radar_abierto_al_publico or any(RADAR_DESPLIEGUE.values()):
                    radar_abierto_al_publico = False
                    try:
                        canal = bot.get_channel(canal_radar_id)
                        if canal:
                            await canal.send(f"🗃️ **ARCHIVO DE OPERACIONES AUTOMÁTICO**\n📅 **Fecha:** {ahora.strftime('%d/%m/%Y')}\n⏱️ **Actividad:** {h}:00 UTC\n🔒 **Estado:** Cuadrante Bloqueado\n📋 **Despliegue Final:**\n{generar_mapa_texto()}")
                            for zona in RADAR_DESPLIEGUE: RADAR_DESPLIEGUE[zona] = None
                            await actualizar_radar_en_canal(canal)
                    except Exception as e: print(f"Error al cerrar radar: {e}")
                    break

@tasks.loop(minutes=5)
async def ping_keeping_alive():
    try:
        if bot.is_ready(): print(f"💓 Ping - Bot conectado. Latencia: {round(bot.latency * 1000)}ms")
        else: print("⚠️ Ping - Bot NO está listo")
    except Exception as e: print(f"Error en ping: {e}")

# ==========================================
# 10. SERVIDOR WEB + RECONEXIÓN
# ==========================================
server_app = Flask(__name__)
@server_app.route('/')
def home(): return "Bot Jinetes MC Activo 24/7 ✅", 200
@server_app.route('/health')
def health():
    if bot.is_ready(): return jsonify({"status": "ok", "bot": "connected"}), 200
    else: return jsonify({"status": "error", "bot": "disconnected"}), 503

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

while True:
    try:
        bot.run(os.getenv("DISCORD_TOKEN"), reconnect=True)
    except Exception as e:
        print(f"Error fatal: {e}. Reintentando en 30 segundos...")
        time.sleep(30)
