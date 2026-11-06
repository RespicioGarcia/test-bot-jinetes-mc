import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import discord
import datetime
import sys

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
sheet_logs = spreadsheet.worksheet("Config_Logs")
sheet_categorias = spreadsheet.worksheet("Config_Categorias")
sheet_roles_staff = spreadsheet.worksheet("Config_Roles_Staff")
sheet_roles_auto = spreadsheet.worksheet("Config_Roles_Automatizacion")
sheet_preguntas_desplegables = spreadsheet.worksheet("Config_Preguntas_Desplegables")
sheet_mensajes = spreadsheet.worksheet("Config_Mensajes")
sheet_config_embed = spreadsheet.worksheet("Config_Embed")

# ==========================================
# 2. VARIABLES GLOBALES
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
CACHE_CONFIG_EMBED = {'ficha': [], 'solicitud': []}

# ==========================================
# 3. FUNCIONES DE CARGA
# ==========================================
def cargar_config_general():
    global CACHE_CONFIG
    if not CACHE_CONFIG:
        records = sheet_general.get_all_records()
        nuevo = {}
        for row in records:
            clave = next((k for k in row.keys() if 'clave' in k.lower()), None)
            valor = next((k for k in row.keys() if 'valor' in k.lower()), None)
            if clave and valor: nuevo[str(row[clave])] = str(row[valor])
        CACHE_CONFIG.clear(); CACHE_CONFIG.update(nuevo)
    return CACHE_CONFIG

def cargar_zonas():
    global CACHE_ZONAS, RADAR_DESPLIEGUE
    if not CACHE_ZONAS: CACHE_ZONAS.extend(sheet_zonas.get_all_records())
    zonas_activas = sorted([r for r in CACHE_ZONAS if str(r.get('Activo', '')).upper() == 'SI'], key=lambda x: int(x.get('Orden', 0)))
    nuevo_radar = {z['Zona']: None for z in zonas_activas}
    RADAR_DESPLIEGUE.clear(); RADAR_DESPLIEGUE.update(nuevo_radar)

def cargar_horarios():
    records = sheet_horarios.get_all_records()
    dias, horas = [], []
    for r in records:
        if str(r.get('Activo', '')).upper() == 'SI':
            dias.append(int(r.get('Dia_Semana', 0)))
            horas.extend([int(h.strip()) for h in str(r.get('Horas_Actividad', '')).split(',')])
    return list(set(dias)), list(set(horas))

def cargar_comandos():
    global COMANDOS_CONFIG
    records = sheet_comandos.get_all_records()
    nuevo = {str(row.get('Comando', '')).lower(): row for row in records}
    COMANDOS_CONFIG.clear(); COMANDOS_CONFIG.update(nuevo)

def cargar_config_reclutamiento():
    global CACHE_RECLUTAMIENTO
    if not CACHE_RECLUTAMIENTO:
        records = sheet_recluta_general.get_all_records()
        nuevo = {}
        for row in records:
            clave = next((k for k in row.keys() if 'clave' in k.lower()), None)
            valor = next((k for k in row.keys() if 'valor' in k.lower()), None)
            if clave and valor: nuevo[str(row[clave])] = str(row[valor])
        CACHE_RECLUTAMIENTO.clear(); CACHE_RECLUTAMIENTO.update(nuevo)
    return CACHE_RECLUTAMIENTO

def cargar_preguntas_reclutamiento():
    global PREGUNTAS_RECLUTAMIENTO
    records = sheet_recluta_preguntas.get_all_records()
    preguntas = [r for r in records if str(r.get('Orden', '')).strip().isdigit() and int(str(r.get('Orden', '')).strip()) > 0]
    preguntas.sort(key=lambda x: int(str(x.get('Orden', '0')).strip()))
    PREGUNTAS_RECLUTAMIENTO.clear(); PREGUNTAS_RECLUTAMIENTO.extend(preguntas)
    return PREGUNTAS_RECLUTAMIENTO

def cargar_preguntas_desplegables():
    global PREGUNTAS_DESPLEGABLES
    records = sheet_preguntas_desplegables.get_all_records()
    preguntas = [r for r in records if str(r.get('Orden', '')).strip().isdigit() and int(str(r.get('Orden', '')).strip()) > 0]
    preguntas.sort(key=lambda x: int(str(x.get('Orden', '0')).strip()))
    PREGUNTAS_DESPLEGABLES.clear(); PREGUNTAS_DESPLEGABLES.extend(preguntas)
    return PREGUNTAS_DESPLEGABLES

def cargar_logs_config():
    global CACHE_LOGS
    records = sheet_logs.get_all_records()
    nuevo = {}
    for row in records:
        if row.get('Tipo_Log') and row.get('Canal_ID'):
            try: nuevo[row.get('Tipo_Log')] = int(row.get('Canal_ID'))
            except: pass
    CACHE_LOGS.clear(); CACHE_LOGS.update(nuevo)
    return CACHE_LOGS

def cargar_categorias_config():
    global CACHE_CATEGORIAS
    records = sheet_categorias.get_all_records()
    nuevo = {}
    for row in records:
        if row.get('Tipo') and row.get('Categoria_ID'):
            try: nuevo[row.get('Tipo')] = int(row.get('Categoria_ID'))
            except: pass
    CACHE_CATEGORIAS.clear(); CACHE_CATEGORIAS.update(nuevo)
    return CACHE_CATEGORIAS

def cargar_roles_staff():
    global CACHE_ROLES_STAFF
    records = sheet_roles_staff.get_all_records()
    nuevos = [int(row.get('Rol_ID')) for row in records if row.get('Rol_ID')]
    CACHE_ROLES_STAFF.clear(); CACHE_ROLES_STAFF.extend(nuevos)
    return CACHE_ROLES_STAFF

def cargar_roles_auto():
    global CACHE_ROLES_AUTO
    records = sheet_roles_auto.get_all_records()
    nuevo = {}
    for row in records:
        if row.get('Accion') and row.get('Rol_ID'):
            try: nuevo[row.get('Accion')] = int(row.get('Rol_ID'))
            except: pass
    CACHE_ROLES_AUTO.clear(); CACHE_ROLES_AUTO.update(nuevo)
    return CACHE_ROLES_AUTO

def cargar_mensajes_config():
    global CACHE_MENSAJES
    records = sheet_mensajes.get_all_records()
    nuevo = {row.get('Clave'): row.get('Valor') for row in records if row.get('Clave')}
    CACHE_MENSAJES.clear(); CACHE_MENSAJES.update(nuevo)
    return CACHE_MENSAJES

def cargar_config_embed():
    global CACHE_CONFIG_EMBED
    records = sheet_config_embed.get_all_records()
    CACHE_CONFIG_EMBED = {'ficha': [], 'solicitud': []}
    for row in records:
        tipo = str(row.get('Tipo_Embed', '')).lower()
        if tipo in ['ficha', 'solicitud']:
            try:
                CACHE_CONFIG_EMBED[tipo].append({
                    'orden': int(row.get('Orden', 0)),
                    'campo': str(row.get('Campo_Origen', '')).strip(),
                    'titulo': str(row.get('Titulo_Campo', '')),
                    'icono': str(row.get('Icono', '')),
                    'formato': str(row.get('Formato', 'normal')).lower(),
                    'mostrar': str(row.get('Mostrar', 'SI')).upper() == 'SI'
                })
            except: pass
    for tipo in CACHE_CONFIG_EMBED:
        CACHE_CONFIG_EMBED[tipo].sort(key=lambda x: x['orden'])
    return CACHE_CONFIG_EMBED

def aplicar_formato_texto(texto, formato):
    if formato == 'negrita': return f"**{texto}**"
    elif formato == 'cursiva': return f"*{texto}*"
    elif formato == 'negrita_cursiva': return f"***{texto}***"
    elif formato == 'codigo': return f"`{texto}`"
    return str(texto)

async def enviar_log(tipo_log, mensaje, color):
    bot = sys.modules['__main__'].bot
    if not CACHE_LOGS: cargar_logs_config()
    canal_id = CACHE_LOGS.get(tipo_log)
    if not canal_id: return
    try:
        canal = bot.get_channel(canal_id) or await bot.fetch_channel(canal_id)
        embed = discord.Embed(description=mensaje, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        await canal.send(embed=embed)
    except Exception as e:
        print(f"🚨 Error enviando log {tipo_log}: {e}")
