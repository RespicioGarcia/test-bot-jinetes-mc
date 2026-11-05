import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# ==========================================
# 1. CONEXIÓN A GOOGLE SHEETS (Igual que antes)
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
sheet_logs = spreadsheet.worksheet("Config_Logs")
sheet_categorias = spreadsheet.worksheet("Config_Categorias")
sheet_roles_staff = spreadsheet.worksheet("Config_Roles_Staff")
sheet_roles_auto = spreadsheet.worksheet("Config_Roles_Automatizacion")
sheet_preguntas_desplegables = spreadsheet.worksheet("Config_Preguntas_Desplegables")
sheet_mensajes = spreadsheet.worksheet("Config_Mensajes")

# ==========================================
# 2. VARIABLES GLOBALES (Las movemos aquí)
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
PREGUNTAS_DESPLEGABLES = []
CACHE_LOGS = {}
CACHE_CATEGORIAS = {}
CACHE_ROLES_STAFF = []
CACHE_ROLES_AUTO = {}
CACHE_MENSAJES = {}

# ==========================================
# 3. FUNCIONES DE CARGA (Copiadas de tu main.py)
# ==========================================
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

def cargar_preguntas_desplegables():
    global PREGUNTAS_DESPLEGABLES
    records = sheet_preguntas_desplegables.get_all_records()
    preguntas = [r for r in records if str(r.get('Orden', '')).isdigit() and int(r.get('Orden', 0)) > 0]
    preguntas.sort(key=lambda x: int(x.get('Orden', 0)))
    PREGUNTAS_DESPLEGABLES = preguntas
    return PREGUNTAS_DESPLEGABLES

def cargar_logs_config():
    global CACHE_LOGS
    CACHE_LOGS = {}
    records = sheet_logs.get_all_records()
    for row in records:
        tipo = row.get('Tipo_Log', '')
        canal_id = row.get('Canal_ID', '')
        if tipo and canal_id:
            try:
                CACHE_LOGS[tipo] = int(canal_id)
            except:
                pass
    return CACHE_LOGS

def cargar_categorias_config():
    global CACHE_CATEGORIAS
    CACHE_CATEGORIAS = {}
    records = sheet_categorias.get_all_records()
    for row in records:
        tipo = row.get('Tipo', '')
        cat_id = row.get('Categoria_ID', '')
        if tipo and cat_id:
            try:
                CACHE_CATEGORIAS[tipo] = int(cat_id)
            except:
                pass
    return CACHE_CATEGORIAS

def cargar_roles_staff():
    global CACHE_ROLES_STAFF
    CACHE_ROLES_STAFF = []
    records = sheet_roles_staff.get_all_records()
    for row in records:
        rol_id = row.get('Rol_ID', '')
        if rol_id:
            try:
                CACHE_ROLES_STAFF.append(int(rol_id))
            except:
                pass
    return CACHE_ROLES_STAFF

def cargar_roles_auto():
    global CACHE_ROLES_AUTO
    CACHE_ROLES_AUTO = {}
    records = sheet_roles_auto.get_all_records()
    for row in records:
        accion = row.get('Accion', '')
        rol_id = row.get('Rol_ID', '')
        if accion and rol_id:
            try:
                CACHE_ROLES_AUTO[accion] = int(rol_id)
            except:
                pass
    return CACHE_ROLES_AUTO

def cargar_mensajes_config():
    global CACHE_MENSAJES
    CACHE_MENSAJES = {}
    records = sheet_mensajes.get_all_records()
    for row in records:
        clave = row.get('Clave', '')
        valor = row.get('Valor', '')
        if clave:
            CACHE_MENSAJES[clave] = valor
    return CACHE_MENSAJES

# Función helper para que los cogs puedan enviar logs fácilmente
async def enviar_log(bot, tipo_log, mensaje, color):
    import discord
    import datetime
    if not CACHE_LOGS:
        cargar_logs_config()
    
    canal_id = CACHE_LOGS.get(tipo_log)
    if not canal_id:
        print(f"⚠️ No hay canal configurado para log: {tipo_log}")
        return
    
    try:
        canal = bot.get_channel(canal_id)
        if not canal:
            canal = await bot.fetch_channel(canal_id)
        
        embed = discord.Embed(description=mensaje, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        await canal.send(embed=embed)
    except Exception as e:
        print(f"🚨 Error enviando log {tipo_log}: {e}")
