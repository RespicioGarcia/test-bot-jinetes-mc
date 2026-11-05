import discord
from discord.ext import commands, tasks
import datetime

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

    # --- VISTAS Y MODALES DEL RADAR ---
    @discord.ui.view
    class RadarControlView(discord.ui.View):
        def __init__(self, outer_instance):
            super().__init__(timeout=None)
            self.outer = outer_instance

        @discord.ui.button(label=" Asignar Posición", style=discord.ButtonStyle.blurple, custom_id="radar:posicion")
        async def asignar_posicion(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not self.outer.radar_abierto_al_publico:
                return await interaction.response.send_message("❌ El radar está cerrado.", ephemeral=True)
            
            # ... (Aquí va tu lógica de select, usando self.outer.bot.data_manager.radar_despliegue) ...
            # Por brevedad, te muestro el patrón. Copia tu lógica de 'asignar_posicion' aquí, 
            # reemplazando 'RADAR_DESPLIEGUE' por 'self.outer.bot.data_manager.radar_despliegue'

    # --- COMANDOS ---
    @commands.hybrid_command(name="radar", description="Desplegar la Central de Operaciones")
    async def radar_slash(self, ctx):
        self.canal_radar_id = ctx.channel.id
        self.radar_abierto_al_publico = True
        self.bot.data_manager._cargar_zonas() # Refrescar datos
        
        # Lógica para borrar mensaje anterior y enviar el nuevo...
        await ctx.send("🔄 Sincronizando central...", ephemeral=True)
        nuevo_msg = await ctx.channel.send(content=self.generar_mapa_texto(), view=self.RadarControlView(self))
        self.ultimo_radar_message_id = nuevo_msg.id
        
        await self.bot.data_manager.enviar_log(self.bot, "radar", f"📡 {ctx.user.mention} ha desplegado el radar", discord.Color.blue())

    # --- TAREA PROGRAMADA ---
    @tasks.loop(seconds=30)
    async def verificador_tiempo_radar(self):
        # Tu lógica del loop, usando self.bot.data_manager.cache_config, etc.
        pass

    @verificador_tiempo_radar.before_loop
    async def before_radar_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RadarCog(bot))
