import discord
from discord.ext import commands, tasks
import datetime
from utils.data import (
    CACHE_CONFIG, CACHE_ZONAS, RADAR_DESPLIEGUE, radar_abierto_al_publico,
    ultimo_radar_message_id, canal_radar_id, cargar_config_general, cargar_zonas,
    cargar_horarios, enviar_log
)

def generar_mapa_texto():
    config = cargar_config_general()
    estado = config.get('MENSAJE_ABIERTO', '🟢 ACTIVO') if radar_abierto_al_publico else config.get('MENSAJE_CERRADO', '🔴 EN ESPERA')
    lineas_zonas = []
    for zona, usuario in RADAR_DESPLIEGUE.items():
        emoji = next((r.get('Emoji', '📍') for r in CACHE_ZONAS if r.get('Zona') == zona), '')
        lineas_zonas.append(f"  • {emoji} {zona.ljust(15)} {usuario if usuario else '[ VACÍO ] ️'}")
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
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label=" Asignar Posición", style=discord.ButtonStyle.blurple, custom_id="radar:posicion")
    async def asignar_posicion(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not radar_abierto_al_publico: return await interaction.response.send_message(" El radar está cerrado.", ephemeral=True)
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
                await enviar_log("radar", f"📍 {user_mention} se ha desplegado en **{zona}**", discord.Color.blue())
                await sel_interaction.followup.send(f"✅ Desplegado en **{zona}**.", ephemeral=True)
            else:
                for z, miembro in list(RADAR_DESPLIEGUE.items()):
                    if miembro == user_mention: RADAR_DESPLIEGUE[z] = None
                await enviar_log("radar", f"🚪 {user_mention} ha salido del servicio", discord.Color.orange())
                await sel_interaction.followup.send("❌ Has salido del servicio.", ephemeral=True)
            await self.cog.actualizar_radar_en_canal(sel_interaction.channel)
        select.callback = select_callback
        view.add_item(select)
        await interaction.response.send_message("Selecciona tu zona:", view=view, ephemeral=True)

    @discord.ui.button(label=" Resetear Radar", style=discord.ButtonStyle.danger, custom_id="radar:reset")
    async def resetear_radar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ResetPasswordModal(self.cog))

class ResetPasswordModal(discord.ui.Modal, title=" Autorización de Reset"):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
        self.password_input = discord.ui.TextInput(label="Clave de Reset", style=discord.TextStyle.short, placeholder="Clave de administrador...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        if self.password_input.value == cargar_config_general().get('CLAVE_RESET', 'admin'):
            await interaction.response.defer(ephemeral=True)
            await self.cog.ejecutar_reset(interaction.channel, interaction.user)
            await interaction.followup.send("✅ Radar reseteado.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ **Clave incorrecta.**", ephemeral=True)

class RadarCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.DIAS_ACTIVIDAD, self.HORAS_ACTIVIDAD = cargar_horarios()

    async def actualizar_radar_en_canal(self, canal):
        global ultimo_radar_message_id
        if ultimo_radar_message_id:
            try:
                msg_viejo = await canal.fetch_message(ultimo_radar_message_id)
                await msg_viejo.delete()
            except: pass
        nuevo_msg = await canal.send(content=generar_mapa_texto(), view=RadarControlView(self))
        ultimo_radar_message_id = nuevo_msg.id

    async def ejecutar_reset(self, canal, usuario):
        global ultimo_radar_message_id
        mapa_antes = generar_mapa_texto()
        if ultimo_radar_message_id:
            try:
                msg_viejo = await canal.fetch_message(ultimo_radar_message_id)
                await msg_viejo.delete()
            except: pass
        await canal.send(f"🧹 **HISTORIAL: RADAR RESET MANUAL**\n👤 **Responsable:** {usuario.mention}\n🗄️ **Estado archivado:**\n{mapa_antes}")
        await enviar_log("radar", f"🧹 {usuario.mention} ha reseteado el radar manualmente", discord.Color.red())
        for zona in RADAR_DESPLIEGUE: RADAR_DESPLIEGUE[zona] = None
        nuevo_msg = await canal.send(content=generar_mapa_texto(), view=RadarControlView(self))
        ultimo_radar_message_id = nuevo_msg.id

    @commands.hybrid_command(name="radar", description="Desplegar la Central de Operaciones")
    async def radar_slash(self, ctx):
        global ultimo_radar_message_id, canal_radar_id, radar_abierto_al_publico
        canal_radar_id = ctx.channel.id
        radar_abierto_al_publico = True
        if ultimo_radar_message_id:
            try:
                msg_viejo = await ctx.channel.fetch_message(ultimo_radar_message_id)
                await msg_viejo.delete()
            except: pass
        await ctx.send("🔄 Sincronizando central...", ephemeral=True)
        cargar_zonas()
        nuevo_msg = await ctx.channel.send(content=generar_mapa_texto(), view=RadarControlView(self))
        ultimo_radar_message_id = nuevo_msg.id
        await enviar_log("radar", f"📡 {ctx.author.mention} ha desplegado el radar", discord.Color.blue())

    @tasks.loop(seconds=30)
    async def verificador_tiempo_radar(self):
        global radar_abierto_al_publico, ultimo_radar_message_id, canal_radar_id
        if not canal_radar_id:
            canal_id_str = cargar_config_general().get('CANAL_RADAR_ID', '')
            if canal_id_str: canal_radar_id = int(canal_id_str)
            else: return
        ahora = datetime.datetime.now(datetime.timezone.utc)
        if ahora.weekday() in self.DIAS_ACTIVIDAD:
            for h in self.HORAS_ACTIVIDAD:
                h_apertura = h - 1 if h > 0 else 23
                if ahora.hour == h_apertura and ahora.minute < 5 and not radar_abierto_al_publico:
                    radar_abierto_al_publico = True
                    try:
                        canal = self.bot.get_channel(canal_radar_id)
                        if canal:
                            await canal.send(f"🔓 **[SISTEMA]:** Posiciones abiertas para la actividad de las **{h}:00 UTC**. ¡Asignen zonas!")
                            await enviar_log("radar", f"🔓 Radar abierto automáticamente para las {h}:00 UTC", discord.Color.green())
                            await self.actualizar_radar_en_canal(canal)
                    except Exception as e: print(f"Error al abrir radar: {e}")
                    break
            for h in self.HORAS_ACTIVIDAD:
                if ahora.hour == h and ahora.minute == 5:
                    if radar_abierto_al_publico or any(RADAR_DESPLIEGUE.values()):
                        radar_abierto_al_publico = False
                        try:
                            canal = self.bot.get_channel(canal_radar_id)
                            if canal:
                                await canal.send(f"🗃️ **ARCHIVO DE OPERACIONES AUTOMÁTICO**\n📅 **Fecha:** {ahora.strftime('%d/%m/%Y')}\n️ **Actividad:** {h}:00 UTC\n🔒 **Estado:** Cuadrante Bloqueado\n📋 **Despliegue Final:**\n{generar_mapa_texto()}")
                                for zona in RADAR_DESPLIEGUE: RADAR_DESPLIEGUE[zona] = None
                                await enviar_log("radar", f"🔒 Radar cerrado automáticamente - Actividad {h}:00 UTC", discord.Color.red())
                                await self.actualizar_radar_en_canal(canal)
                        except Exception as e: print(f"Error al cerrar radar: {e}")
                        break

    @verificador_tiempo_radar.before_loop
    async def before_radar_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    cog = RadarCog(bot)
    await bot.add_cog(cog)
    cog.verificador_tiempo_radar.start()
