import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import discord

class DataManager:
    def __init__(self):
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_path = os.getenv("CREDS_PATH", "/etc/secrets/creds.json")
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        self.client = gspread.authorize(creds)
        
        spreadsheet_name = os.getenv("SPREADSHEET_NAME", "jinetesmc")
        self.spreadsheet = self.client.open(spreadsheet_name)

        # Diccionario centralizado de hojas
        self.sheets = {
            "menu": self.spreadsheet.worksheet("Menu_Principal"),
            "sub": self.spreadsheet.worksheet("Subcategorias"),
            "contenido": self.spreadsheet.worksheet("Contenido_Menu"),
            "zonas": self.spreadsheet.worksheet("Config_Radar_Zonas"),
            "horarios": self.spreadsheet.worksheet("Config_Radar_Horarios"),
            "general": self.spreadsheet.worksheet("Config_Radar_General"),
            "comandos": self.spreadsheet.worksheet("Config_Comandos"),
            "recluta_general": self.spreadsheet.worksheet("Config_Recluta_General"),
            "recluta_preguntas": self.spreadsheet.worksheet("Config_Recluta_Preguntas"),
            "registro_reclutas": self.spreadsheet.worksheet("Registro_Reclutas"),
            "logs": self.spreadsheet.worksheet("Config_Logs"),
            "categorias": self.spreadsheet.worksheet("Config_Categorias"),
            "roles_staff": self.spreadsheet.worksheet("Config_Roles_Staff"),
            "roles_auto": self.spreadsheet.worksheet("Config_Roles_Automatizacion"),
            "preguntas_desplegables": self.spreadsheet.worksheet("Config_Preguntas_Desplegables"),
            "mensajes": self.spreadsheet.worksheet("Config_Mensajes"),
            "busq_reglas": self.spreadsheet.worksheet("Reglas_Buscable"),
            "busq_vestimenta": self.spreadsheet.worksheet("Vestimenta_Buscable")
        }

        # Cachés (Reemplazan a tus variables globales)
        self.cache_config = {}
        self.cache_zonas = []
        self.radar_despliegue = {}
        self.comandos_config = {}
        self.cache_reclutamiento = {}
        self.preguntas_reclutamiento = []
        self.preguntas_desplegables = []
        self.cache_logs = {}
        self.cache_categorias = {}
        self.cache_roles_staff = []
        self.cache_roles_auto = {}
        self.cache_mensajes = {}

    def cargar_todo(self):
        self._cargar_config_general()
        self._cargar_zonas()
        self._cargar_comandos()
        self._cargar_reclutamiento()
        self._cargar_logs()
        self._cargar_categorias()
        self._cargar_roles()
        self._cargar_mensajes()

    def _cargar_config_general(self):
        records = self.sheets["general"].get_all_records()
        for row in records:
            clave = next((k for k in row.keys() if 'clave' in k.lower()), None)
            valor = next((k for k in row.keys() if 'valor' in k.lower()), None)
            if clave and valor: self.cache_config[str(row[clave])] = str(row[valor])

    def _cargar_zonas(self):
        self.cache_zonas = self.sheets["zonas"].get_all_records()
        zonas_activas = [r for r in self.cache_zonas if str(r.get('Activo', '')).upper() == 'SI']
        zonas_activas.sort(key=lambda x: int(x.get('Orden', 0)))
        self.radar_despliegue = {z['Zona']: None for z in zonas_activas}

    def _cargar_comandos(self):
        records = self.sheets["comandos"].get_all_records()
        self.comandos_config = {str(row.get('Comando', '')).lower(): row for row in records}

    def _cargar_reclutamiento(self):
        records = self.sheets["recluta_general"].get_all_records()
        for row in records:
            clave = next((k for k in row.keys() if 'clave' in k.lower()), None)
            valor = next((k for k in row.keys() if 'valor' in k.lower()), None)
            if clave and valor: self.cache_reclutamiento[str(row[clave])] = str(row[valor])
        
        preg = self.sheets["recluta_preguntas"].get_all_records()
        self.preguntas_reclutamiento = sorted([r for r in preg if str(r.get('Orden', '')).isdigit() and int(r.get('Orden', 0)) > 0], key=lambda x: int(x.get('Orden', 0)))
        
        desp = self.sheets["preguntas_desplegables"].get_all_records()
        self.preguntas_desplegables = sorted([r for r in desp if str(r.get('Orden', '')).isdigit() and int(r.get('Orden', 0)) > 0], key=lambda x: int(x.get('Orden', 0)))

    def _cargar_logs(self):
        records = self.sheets["logs"].get_all_records()
        for row in records:
            if row.get('Tipo_Log') and row.get('Canal_ID'):
                try: self.cache_logs[row.get('Tipo_Log')] = int(row.get('Canal_ID'))
                except: pass

    def _cargar_categorias(self):
        records = self.sheets["categorias"].get_all_records()
        for row in records:
            if row.get('Tipo') and row.get('Categoria_ID'):
                try: self.cache_categorias[row.get('Tipo')] = int(row.get('Categoria_ID'))
                except: pass

    def _cargar_roles(self):
        records_staff = self.sheets["roles_staff"].get_all_records()
        self.cache_roles_staff = [int(row.get('Rol_ID')) for row in records_staff if row.get('Rol_ID')]
        
        records_auto = self.sheets["roles_auto"].get_all_records()
        self.cache_roles_auto = {row.get('Accion'): int(row.get('Rol_ID')) for row in records_auto if row.get('Accion') and row.get('Rol_ID')}

    def _cargar_mensajes(self):
        records = self.sheets["mensajes"].get_all_records()
        self.cache_mensajes = {row.get('Clave'): row.get('Valor') for row in records if row.get('Clave')}

    async def enviar_log(self, bot, tipo_log, mensaje, color):
        if not self.cache_logs: self._cargar_logs()
        canal_id = self.cache_logs.get(tipo_log)
        if not canal_id: return
        try:
            canal = bot.get_channel(canal_id) or await bot.fetch_channel(canal_id)
            embed = discord.Embed(description=mensaje, color=color, timestamp=discord.utils.utcnow())
            await canal.send(embed=embed)
        except Exception as e:
            print(f"🚨 Error enviando log {tipo_log}: {e}")
