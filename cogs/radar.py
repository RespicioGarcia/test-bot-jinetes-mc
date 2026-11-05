import discord
from discord.ext import commands, tasks
import datetime

class ResetPasswordModal(discord.ui.Modal, title=" Autorización de Reset"):
    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager
        self.password_input = discord.ui.TextInput(label="Clave de Reset", style=discord.TextStyle.short, placeholder="Clave de administrador...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        clave_correcta = self.data_manager.cache_config.get('CLAVE_RESET', 'admin')
        if self.password_input.value == clave_correcta:
            await interaction.response.defer(ephemeral=True)
            # Nota: El cog padre manejará la lógica de borrar y recrear el mensaje
            # Aquí solo validamos y pasamos el control, o lo hacemos directo si pasamos el canal
            await interaction.followup.send("✅ Clave correcta. Reseteando radar...", ephemeral=True)
            # Lógica de reseteo simplificada para el modal
            radar_cog = self.bot.get_cog("RadarCog")
            if radar_cog:
                await radar_cog.ejecutar_reset(interaction.channel, interaction.user)
        else:
            await interaction.response.send_message("⚠️ **Clave incorrecta.**", ephemeral=True)

class RadarControlView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label=" Asignar Posición", style=discord.ButtonStyle.blurple, custom_id="radar:posicion")
    async def asignar_posicion(self, interaction: discord.Interaction, button: discord.ui.Button):
        dm = self.cog.bot.data_manager
        if not self.cog.radar_abierto_al_publico:
            return await interaction.response.send_message("❌ El radar está cerrado.", ephemeral=True)
        
        opciones = [discord.SelectOption(label=zona, value=zona) for zona in dm.radar_despliegue.keys()]
        opciones.append(discord.SelectOption(label="🚪 Salir de Servicio", value="Retirarse"))
        view = discord.ui.View(timeout=60)
        select = discord.ui.Select(placeholder="📍 Elige tu punto de despliegue...", options=opciones)
        
        async def select_callback(sel_interaction: discord.Interaction):
            await sel_interaction.response.defer(ephemeral=True)
            zona = sel_interaction.data['values'][0]
            user_mention = sel_interaction.user.mention
            
            if zona != "Retirarse":
                if dm.radar_despliegue.get(zona) is not None and dm.radar_despliegue.get(zona) != user_mention:
                    return await sel_interaction.followup.send(f"❌ La posición **{zona}** ya está ocupada.", ephemeral=True)
                for z, miembro in list(dm.radar_despliegue.items()):
                    if miembro == user_mention: dm.radar_despliegue[z] = None
                dm.radar_despliegue[zona] = user_mention
                await dm.enviar_log(self.cog.bot, "radar", f"📍 {user_mention} se ha desplegado en **{zona}**", discord.Color.blue())
                await sel_interaction.followup.send(f"✅ Desplegado en **{zona}**.", ephemeral=True)
            else:
                for z, miembro in list(dm.radar_despliegue.items()):
                    if miembro == user_mention: dm.radar_despliegue[z] = None
                await dm.enviar_log(self.cog.bot, "radar", f"🚪 {user_mention} ha salido del servicio", discord.Color.orange())
                await sel_interaction.followup.send("❌ Has salido del servicio.", ephemeral=True)
            await self.cog.actualizar_radar_en_canal(sel_interaction.channel)
        select.callback = select_callback
        view.add_item(select)
        await interaction.response.send_message("Selecciona tu zona:", view=view, ephemeral=True)

    @discord.ui.button(label=" Resetear Radar", style=discord.ButtonStyle.danger, custom_id="radar:reset")
    async def resetear_radar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ResetPasswordModal(self.cog.bot.data_manager))

class RadarCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ultimo_radar_message_id = None
        self.canal_radar_id = None
        self.radar_abierto_al_publico = False

    def generar_mapa_texto(self):
        config = self.bot.data_manager.cache_config
        estado = config.get('MENSAJE_ABIERTO', '🟢 ACTIVO') if self.radar_abierto_al_publico else config.get('MENSAJE_CERRADO', '🔴 EN ESPERA')
        lineas_zonas = []
        for zona, usuario in self.bot.data_manager.radar_despliegue.items():
            emoji = next((r.get('Emoji', '📍') for r in self.bot.data_manager.cache_zonas if r.get('Zona') == zona), '')
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

    async def actualizar_radar_en_canal(self, canal):
        if self.ultimo_radar_message_id:
            try:
                msg_viejo = await canal.fetch_message(self.ultimo_radar_message_id)
                await msg_viejo.delete()
            except: pass
        nuevo_msg = await canal.send(content=self.generar_mapa_texto(), view=RadarControlView(self))
        self.ultimo_radar_message_id = nuevo_msg.id

    async def ejecutar_reset(self, canal, usuario):
        mapa_antes = self.generar_mapa_texto()
        if self.ultimo_radar_message_id:
            try:
                msg_viejo = await canal.fetch_message(self.ultimo_radar_message_id)
                await msg_viejo.delete()
            except: pass
            
        await canal.send(f"🧹 **HISTORIAL: RADAR RESET MANUAL**\n👤 **Responsable:** {usuario.mention}\n🗄️ **Estado archivado:**\n{mapa_antes}")
        await self.bot.data_manager.enviar_log(self.bot, "radar", f"🧹 {usuario.mention} ha reseteado el radar manualmente", discord.Color.red())
        
        for zona in self.bot.data_manager.radar_despliegue: 
            self.bot.data_manager.radar_despliegue[zona] = None
            
        nuevo_msg = await canal.send(content=self.generar_mapa_texto(), view=RadarControlView(self))
        self.ultimo_radar_message_id = nuevo_msg.id

    @commands.hybrid_command(name="radar", description="Desplegar la Central de Operaciones")
    async def radar_slash(self, interaction: discord.Interaction):
        self.canal_radar_id = interaction.channel.id
        self.radar_abierto_al_publico = True
        if self.ultimo_radar_message_id:
            try:
                msg_viejo = await interaction.channel.fetch_message(self.ultimo_radar_message_id)
                await msg_viejo.delete()
            except: pass
        self.bot.data_manager._cargar_zonas()
        await interaction.response.send_message("🔄 Sincronizando central...", ephemeral=True)
        nuevo_msg = await interaction.channel.send(content=self.generar_mapa_texto(), view=RadarControlView(self))
        self.ultimo_radar_message_id = nuevo_msg.id
        await self.bot.data_manager.enviar_log(self.bot, "radar", f"📡 {interaction.user.mention} ha desplegado el radar", discord.Color.blue())

    @tasks.loop(seconds=30)
    async def verificador_tiempo_radar(self):
        if not self.canal_radar_id:
            canal_id_str = self.bot.data_manager.cache_config.get('CANAL_RADAR_ID', '')
            if canal_id_str: self.canal_radar_id = int(canal_id_str)
            else: return
        
        ahora = datetime.datetime.now(datetime.timezone.utc)
        # Lógica simplificada de horarios (puedes expandirla con tu lógica original de DIAS_ACTIVIDAD/HORAS_ACTIVIDAD)
        # Aquí va tu lógica original de apertura/cierre automático usando self.bot.data_manager.cache_config

    @verificador_tiempo_radar.before_loop
    async def before_radar_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RadarCog(bot))
