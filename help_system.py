import discord
from discord.ext import commands

class SearchModal(discord.ui.Modal):
    def __init__(self, categoria_nombre, hoja_nombre, data_manager):
        super().__init__(title=f"🔍 Buscar en {categoria_nombre}")
        self.data_manager = data_manager
        self.query_input = discord.ui.TextInput(label="Término de búsqueda", placeholder="Ej: armas, respawn...", required=True, max_length=50)
        self.hoja_nombre = hoja_nombre
        self.categoria_nombre = categoria_nombre

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        query = self.query_input.value.lower()
        hoja = self.data_manager.sheets.get(self.hoja_nombre, self.data_manager.sheets["busq_reglas"])
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
    def __init__(self, data_manager):
        super().__init__(timeout=180)
        self.data_manager = data_manager
        self.build_menu()

    def build_menu(self):
        records = self.data_manager.sheets["menu"].get_all_records()
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
                    sub_records = self.data_manager.sheets["sub"].get_all_records()
                    sub_busqueda = next((s for s in sub_records if s.get('Categoria_Padre') == item_id and str(s.get('Tipo', '')) == '2'), None)
                    hoja = sub_busqueda.get('Hoja_Busqueda') if sub_busqueda else "Reglas_Buscable"
                    return await interaction.response.send_modal(SearchModal(nombre_categoria, hoja, self.data_manager))
                await self.show_subcategories(interaction, item_id, nombre_categoria)
            select.callback = select_callback
            self.add_item(select)

    async def show_subcategories(self, interaction: discord.Interaction, parent_id, parent_name):
        sub_records = self.data_manager.sheets["sub"].get_all_records()
        contenido_records = self.data_manager.sheets["contenido"].get_all_records()
        subs = [r for r in sub_records if r.get('Categoria_Padre') == parent_id]
        subs.sort(key=lambda x: int(x.get('Orden', 0)))
        view = discord.ui.View(timeout=180)
        options = [discord.SelectOption(label=sub['Nombre'], value=f"{sub['ID']}|{str(sub.get('Tipo', ''))}|{sub.get('Hoja_Busqueda', '')}", emoji="🔹") for sub in subs]
        select_sub = discord.ui.Select(placeholder=f" Subcategorías de {parent_name}...", options=options)
        
        async def sub_callback(sub_interaction: discord.Interaction):
            sub_id, tipo, hoja_busqueda = select_sub.values[0].split('|')
            if tipo == '2':
                sub_data = next((r for r in sub_records if r['ID'] == sub_id), None)
                return await sub_interaction.response.send_modal(SearchModal(sub_data['Nombre'] if sub_data else "Búsqueda", hoja_busqueda, self.data_manager))
            contenido = next((c for c in contenido_records if c.get('ID_Subcategoria') == sub_id), None)
            if not contenido:
                return await sub_interaction.response.send_message("⚠️ Esta categoría no tiene contenido.", ephemeral=True)
            embed = discord.Embed(title=contenido.get('Titulo', ''), description=contenido.get('Contenido', ''), color=discord.Color.green())
            if contenido.get('Imagen', '') and str(contenido.get('Imagen', '')).startswith('http'):
                embed.set_image(url=contenido.get('Imagen', ''))
            await sub_interaction.response.send_message(embed=embed, ephemeral=True)
        select_sub.callback = sub_callback
        view.add_item(select_sub)
        await interaction.response.send_message(f" Has seleccionado: **{parent_name}**", view=view, ephemeral=True)

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="ayuda", description="Menú interactivo de normas, vestimenta y ayuda")
    async def ayuda_slash(self, interaction: discord.Interaction):
        view = MainMenuView(self.bot.data_manager)
        await interaction.response.send_message("👋 **SISTEMA DE AYUDA JINETES MC**\nSelecciona una opción del menú desplegable:", view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
