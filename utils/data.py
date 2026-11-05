import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import discord
import datetime

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

# ==========================================
# 2. VARIABLES GLOBALES (Se modificarán en memoria, no se reasignarán)
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
# 3. FUNCIONES DE CARGA (Corregidas para modificar en memoria)
# ==========================================
def cargar_config_general():
    global CACHE_CONFIG
    if not CACHE_CONFIG:
        records = sheet_general.get_all_records()
        nuevo_cache = {}
        for row in records:
            clave = next((k for k in row.keys() if 'clave' in k.lower()), None)
            valor = next((k for k in row.keys() if 'valor' in k.lower()), None)
            if clave and valor:
                nuevo_cache[str(row[clave])] = str(row[valor])
        CACHE_CONFIG.clear()
        CACHE_CONFIG.update(nuevo_cache)
    return CACHE_CONFIG

def cargar_zonas():
    global CACHE_ZONAS, RADAR_DESPLIEGUE
    if not CACHE_ZONAS:
        CACHE_ZONAS.extend(sheet_zonas.get_all_records())
    
    zonas_activas = [r for r in CACHE_ZONAS if str(r.get('Activo', '')).upper() == 'SI']
    zonas_activas.sort(key=lambda x: int(x.get('Orden', 0)))
    
    nuevo_radar = {z['Zona']: None for z in zonas_activas}
    RADAR_DESPLIEGUE.clear()
    RADAR_DESPLIEGUE.update(nuevo_radar)

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
    nuevo_comandos = {str(row.get('Comando', '')).lower(): row for row in records}
    COMANDOS_CONFIG.clear()
    COMANDOS_CONFIG.update(nuevo_comandos)

def cargar_config_reclutamiento():
    global CACHE_RECLUTAMIENTO
    if not CACHE_RECLUTAMIENTO:
        records = sheet_recluta_general.get_all_records()
        nuevo_cache = {}
        for row in records:
            clave = next((k for k in row.keys() if 'clave' in k.lower()), None)
            valor = next((k for k in row.keys() if 'valor' in k.lower()), None)
            if clave and valor:
                nuevo_cache[str(row[clave])] = str(row[valor])
        CACHE_RECLUTAMIENTO.clear()
        CACHE_RECLUTAMIENTO.update(nuevo_cache)
    return CACHE_RECLUTAMIENTO

def cargar_preguntas_reclutamiento():
    global PREGUNTAS_RECLUTAMIENTO
    records = sheet_recluta_preguntas.get_all_records()
    preguntas = [r for r in records if str(r.get('Orden', '')).strip().isdigit() and int(str(r.get('Orden', '')).strip()) > 0]
    preguntas.sort(key=lambda x: int(str(x.get('Orden', '0')).strip()))
    
    # MODIFICAMOS LA LISTA ORIGINAL EN MEMORIA
    PREGUNTAS_RECLUTAMIENTO.clear()
    PREGUNTAS_RECLUTAMIENTO.extend(preguntas)
    return PREGUNTAS_RECLUTAMIENTO

def cargar_preguntas_desplegables():
    global PREGUNTAS_DESPLEGABLES
    records = sheet_preguntas_desplegables.get_all_records()
    preguntas = [r for r in records if str(r.get('Orden', '')).strip().isdigit
