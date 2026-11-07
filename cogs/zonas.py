import discord
from discord.ext import commands, tasks
import datetime

from utils.data import (
    CACHE_DISPUTAS_ZONAS, CACHE_DISPUTAS_GENERAL, ALARMAS_PROGRAMADAS,
    cargar_disputas_zonas, cargar_disputas_general,
    sheet_registro_disputas, registrar_disputa,
    cargar_alarmas_pendientes, marcar_alarma_enviada
)

# ==========================================
# FUNCIÓN FINAL: REGISTRA Y NOTIFICA
# ==========================================
async def finalizar_disputa(interaction, zona, resultado, org_ganadora, horas_alarma):
    ahora = datetime.datetime.now()
    fecha = ahora.strftime('%d/%m/%Y')
    hora = ahora.strftime('%H:%M')
    
    alarma_txt = "Sin alarma"
    dispara_txt = ""
    dispara = None
    if horas_alarma > 0:
        dispara = ahora + datetime.timedelta(hours=horas_alarma)
        alarma_txt = f"{horas_alarma}h"
        dispara_txt = dispara.strftime('%d/%m/%Y %H:%M')
    
    # 1. Registro en Excel (persistente)
    id_unico = registrar_disputa(fecha, hora, zona, resultado, org_ganadora, alarma_txt, dispara_txt, interaction.user)
    
    # 2. Alarma en memoria
    if horas_alarma > 0 and dispara:
        ALARMAS_PROGRAMADAS.append({
            'id': id_unico, 'dispara': dispara,
            'zona': zona, 'usuario': interaction.user.display_name
        })
    
    # 3. Notificaciones (canales configurables desde Excel)
    cargar_disputas_general()
    if resultado == "Ganada":
        canal_id = CACHE_DISPUTAS_GENERAL.get('CANAL_VICTORIA', '')
        if canal_id:
            try:
                canal = interaction.client.get_channel(int(canal_id))
                if canal:
                    embed = discord.Embed(title="🏆 ¡ZONA GANADA!", description=f"**{zona}** ahora es nuestra.\n👤 Registrado por: {interaction.user.mention}", color=discord.Color.green(), timestamp=ahora)
                    await canal.send(embed=embed)
            except Exception as e:
                print(f"🚨 Error canal victoria: {e}")
    
    if horas_alarma > 0:
        canal_id = CACHE_DISPUTAS_GENERAL.get('CANAL_ALARMA', '')
        if canal_id:
            try:
                canal = interaction.client.get_channel(int(canal_id))
                if canal:
                    embed = discord.Embed(title="⏰ Alarma de control programada", description=f"Zona: **{zona}**\n⏳ Se activará en **{horas_alarma}h** ({dispara_txt})\n👤 Por: {interaction.user.mention}", color=discord.Color.orange(), timestamp=ahora)
                    await canal.send(embed=embed)
            except Exception as e:
                print(f"🚨 Error canal alarma: {e}")
    
    # 4. Confirmación al usuario
    resumen = f"✅ Disputa registrada: **{zona}** → {resultado}"
    if org_ganadora: resumen += f" | Org: {org_ganadora}"
    if horas_alarma > 0: resumen += f" | ⏰ Alarma en {horas_alarma}h"
    await interaction.followup.send(resumen, ephemeral=True)


# ==========================================
# VIEWS Y MODALES
# ==========================================
class ZonasSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        options = [discord.SelectOption(label=str(z.get('Texto_Mostrar', z.get('Zona')))[:100], value=str(z.get('Zona'))[:100]) for z in CACHE_DISPUTAS_ZONAS[:25]]
        select = discord.ui.Select(placeholder="🗺️ Selecciona la zona en disputa...", options=options)
        async def callback(interaction: discord.Interaction):
            zona = select.values[0]
            await interaction.response.edit_message(
                content=f"🗺️ Zona seleccionada: **{zona}**\n¿Cuál fue el resultado?",
                view=ResultadoView(zona)
            )
        select.callback = callback
        self.add_item(select)


class ResultadoView(discord.ui.View):
    def __init__(self, zona):
        super().__init__(timeout=120)
        self.zona = zona

    @discord.ui.button(label="✅ Ganada", style=discord.ButtonStyle.success)
    async def ganada(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=f"✅ **{self.zona}** — Disputa ganada.\n¿Quieres programar una alarma de control? (opcional)",
            view=AlarmaView(self.zona)
        )

    @discord.ui.button(label="❌ Perdida", style=discord.ButtonStyle.danger)
    async def perdida(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(OrgModal(self.zona))


class AlarmaView(discord.ui.View):
    def __init__(self, zona):
        super().__init__(timeout=120)
        self.zona = zona
        # "Sin alarma" PRIMERO, luego de 4h a 14h
        options = [discord.SelectOption(label="🔕 Sin alarma", value="0")]
        for h in range(4, 15):
            options.append(discord.SelectOption(label=f"⏰ En {h}h", value=str(h)))
        select = discord.ui.Select(placeholder="⏰ Programar alarma (opcional)...", options=options)
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            await finalizar_disputa(interaction, self.zona, "Ganada", "", int(select.values[0]))
        select.callback = callback
        self.add_item(select)


class OrgModal(discord.ui.Modal, title="Organización ganadora"):
    def __init__(self, zona):
        super().__init__()
        self.zona = zona
        self.org_input = discord.ui.TextInput(
            label="¿Qué organización la ganó? (opcional)",
            required=False, max_length=100,
            placeholder="Dejar vacío si no aplica..."
        )
        self.add_item(self.org_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await finalizar_disputa(interaction, self.zona, "Perdida", self.org_input.value.strip(), 0)


# ==========================================
# COG
# ==========================================
class ZonasCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        cargar_disputas_zonas()
        cargar_disputas_general()
        cargar_alarmas_pendientes()  # Recupera alarmas guardadas en Excel tras reinicio
        if not self.verificador_alarmas.is_running():
            self.verificador_alarmas.start()

    @commands.hybrid_command(name="disputa", description="Registrar una disputa de zona")
    async def disputa(self, ctx):
        cargar_disputas_zonas()
        if not CACHE_DISPUTAS_ZONAS:
            return await ctx.send("❌ No hay zonas configuradas en `Config_Disputas_Zonas`.", ephemeral=True)
        await ctx.send("🗺️ **NUEVA DISPUTA DE ZONA**\nSelecciona la zona:", view=ZonasSelectView(), ephemeral=True)

    @commands.hybrid_command(name="taimeo", description="Ver historial de disputas")
    async def taimeo(self, ctx):
        await ctx.defer(ephemeral=True)
        records = sheet_registro_disputas.get_all_records()
        if not records:
            return await ctx.send("📭 No hay disputas registradas todavía.", ephemeral=True)
        
        ganadas = sum(1 for r in records if str(r.get('Resultado', '')).lower() == 'ganada')
        perdidas = sum(1 for r in records if str(r.get('Resultado', '')).lower() == 'perdida')
        
        embed = discord.Embed(
            title="📊 TAIMEO DE DISPUTAS",
            description=f"✅ Ganadas: **{ganadas}** | ❌ Perdidas: **{perdidas}** | Total: {len(records)}",
            color=discord.Color.blue()
        )
        for r in records[-10:][::-1]:
            extra = ""
            if r.get('Org_Ganadora'): extra += f" | Org: {r.get('Org_Ganadora')}"
            if r.get('Alarma') and r.get('Alarma') != 'Sin alarma': extra += f" | ⏰ {r.get('Alarma')}"
            emoji = "✅" if str(r.get('Resultado', '')).lower() == 'ganada' else "❌"
            embed.add_field(
                name=f"{r.get('Fecha', '')} {r.get('Hora', '')} — {r.get('Zona', '')}",
                value=f"{emoji} {r.get('Resultado', '')}{extra} | 👤 {r.get('Usuario', '')}",
                inline=False
            )
        await ctx.send(embed=embed, ephemeral=True)

    @tasks.loop(seconds=30)
    async def verificador_alarmas(self):
        ahora = datetime.datetime.now()
        for alarma in list(ALARMAS_PROGRAMADAS):
            if ahora >= alarma['dispara']:
                ALARMAS_PROGRAMADAS.remove(alarma)
                marcar_alarma_enviada(alarma['id'])
                canal_id = CACHE_DISPUTAS_GENERAL.get('CANAL_ALARMA', '')
                if canal_id:
                    try:
                        canal = self.bot.get_channel(int(canal_id))
                        if canal:
                            embed = discord.Embed(
                                title="🚨 ¡ALARMA DE ZONA!",
                                description=f"⏰ Se cumple el control de **{alarma['zona']}**\n👤 Registrado por: {alarma['usuario']}",
                                color=discord.Color.red(), timestamp=ahora
                            )
                            await canal.send(embed=embed)
                    except Exception as e:
                        print(f"🚨 Error enviando alarma: {e}")

    @verificador_alarmas.before_loop
    async def before_alarmas(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ZonasCog(bot))
