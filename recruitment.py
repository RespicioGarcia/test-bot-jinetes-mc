import discord
from discord.ext import commands
import datetime

class FormularioReclutaModalPaginado(discord.ui.Modal):
    def __init__(self, usuario, canal_ticket, respuestas_desplegables, preguntas, pagina_actual, total_paginas, respuestas_previas, data_manager):
        self.usuario = usuario
        self.canal_ticket = canal_ticket
        self.respuestas_desplegables = respuestas_desplegables
        self.pagina_actual = pagina_actual
        self.total_paginas = total_paginas
        self.respuestas_previas = respuestas_previas
        self.data_manager = data_manager
        
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
                max_len = 4000 if estilo == discord.TextStyle.paragraph else 100
                self.add_item(discord.ui.TextInput(label=label_final, placeholder=placeholder, required=obligatoria, style=estilo, max_length=max_len))
            except Exception as e:
                print(f"❌ Error en campo {i}: {e}")
                self.add_item(discord.ui.TextInput(label=f"Pregunta {i+1}", placeholder="Escribe aquí...", required=False, style=discord.TextStyle.short, max_length=100))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            respuestas_pagina = [(child.label.rstrip(' *').strip(), child.value) for child in self.children]
            todas_las_respuestas = self.respuestas_previas + respuestas_pagina
            
            if self.pagina_actual < self.total_paginas:
                siguiente_pagina = self.pagina_actual + 1
                inicio = (siguiente_pagina - 1) * 5
                fin = siguiente_pagina * 5
                preguntas_siguientes = self.data_manager.preguntas_reclutamiento[inicio:fin]
                
                siguiente_modal = FormularioReclutaModalPaginado(
                    self.usuario, self.canal_ticket, self.respuestas_desplegables,
                    preguntas_siguientes, siguiente_pagina, self.total_paginas, todas_las_respuestas, self.data_manager
                )
                await interaction.response.send_modal(siguiente_modal)
            else:
                await interaction.response.defer(ephemeral=True)
                cog = interaction.client.get_cog("RecruitmentCog")
                await cog.construir_y_enviar_embed(interaction, todas_las_respuestas, self.respuestas_desplegables)
        except Exception as e:
            print(f"🚨 ERROR EN MODAL: {e}")
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

class FormularioReclutaModal(discord.ui.Modal):
    def __init__(self, usuario, canal_ticket, respuestas_desplegables, data_manager):
        self.usuario = usuario
        self.canal_ticket = canal_ticket
        self.respuestas_desplegables = respuestas_desplegables
        self.data_manager = data_manager
        self.pagina_actual = 1
        self.total_paginas = (len(self.data_manager.preguntas_reclutamiento) + 4) // 5
        self.respuestas_previas = []
        
        super().__init__(title=f"Solicitud ({self.pagina_actual}/{self.total_paginas})")
        
        inicio = 0
        fin = 5
        preguntas_pagina = self.data_manager.preguntas_reclutamiento[inicio:fin]
        
        for i, p in enumerate(preguntas_pagina):
            try:
                pregunta = str(p.get('Pregunta', f'Pregunta {i+1}'))
                placeholder = str(p.get('Placeholder', 'Escribe tu respuesta...'))
                obligatoria = str(p.get('Obligatoria', 'NO')).upper() == 'SI'
                estilo = discord.TextStyle.paragraph if any(palabra in pregunta.lower() for palabra in ['larga', 'motivación', 'experiencia', 'historia', 'backstory', 'por qué', 'detalla', 'describe']) else discord.TextStyle.short
                pregunta_limpia = pregunta.rstrip('*').strip()[:37] + ("..." if len(pregunta) > 40 else "")
                label_final = f"{pregunta_limpia}{'*' if obligatoria else ''}"
                placeholder = (placeholder.strip() or 'Escribe aquí...')[:100]
                max_len = 4000 if estilo == discord.TextStyle.paragraph else 100
                self.add_item(discord.ui.TextInput(label=label_final, placeholder=placeholder, required=obligatoria, style=estilo, max_length=max_len))
            except Exception as e:
                print(f"❌ Error en campo {i}: {e}")
                self.add_item(discord.ui.TextInput(label=f"Pregunta {i+1}", placeholder="Escribe aquí...", required=False, style=discord.TextStyle.short, max_length=100))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            respuestas_pagina = [(child.label.rstrip(' *').strip(), child.value) for child in self.children]
            todas_las_respuestas = self.respuestas_previas + respuestas_pagina
            
            if self.pagina_actual < self.total_paginas:
                siguiente_pagina = self.pagina_actual + 1
                inicio = (siguiente_pagina - 1) * 5
                fin = siguiente_pagina * 5
                preguntas_siguientes = self.data_manager.preguntas_reclutamiento[inicio:fin]
                
                siguiente_modal = FormularioReclutaModalPaginado(
                    self.usuario, self.canal_ticket, self.respuestas_desplegables,
                    preguntas_siguientes, siguiente_pagina, self.total_paginas, todas_las_respuestas, self.data_manager
                )
                await interaction.response.send_modal(siguiente_modal)
            else:
                await interaction.response.defer(ephemeral=True)
                cog = interaction.client.get_cog("RecruitmentCog")
                await cog.construir_y_enviar_embed(interaction, todas_las_respuestas, self.respuestas_desplegables)
        except Exception as e:
            print(f"🚨 ERROR EN MODAL: {e}")
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

class MenuDesplegableView(discord.ui.View):
    def __init__(self, usuario, canal_ticket, data_manager):
        super().__init__(timeout=300)
        self.usuario = usuario
        self.canal_ticket = canal_ticket
        self.data_manager = data_manager
        self.respuestas_desplegables = {}
        self.preguntas_respondidas = 0
        self.build_menus()
    
    def build_menus(self):
        for pregunta in self.data_manager.preguntas_desplegables:
            opciones_str = str(pregunta.get('Opciones', ''))
            opciones = [opt.strip() for opt in opciones_str.split(',') if opt.strip()]
            
            if opciones:
                select = discord.ui.Select(
                    placeholder=pregunta.get('Pregunta', 'Selecciona...')[:100],
                    options=[discord.SelectOption(label=opt[:100], value=opt[:100]) for opt in opciones[:25]],
                    min_values=1, max_values=1
                )
                
                async def select_callback(interaction: discord.Interaction, select=select, pregunta=pregunta):
                    await interaction.response.defer(ephemeral=True)
                    self.respuestas_desplegables[pregunta.get('Pregunta')] = select.values[0]
                    self.preguntas_respondidas += 1
                    await interaction.followup.send(f"✅ Seleccionado: {select.values[0]}", ephemeral=True)
                
                select.callback = select_callback
                self.add_item(select)
        
        continuar_btn = discord.ui.Button(label="📝 Continuar con formulario", style=discord.ButtonStyle.primary, custom_id="recluta:continuar")
        async def continuar_callback(interaction: discord.Interaction):
            if interaction.user != self.usuario:
                return await interaction.response.send_message("❌ Este formulario es solo para ti.", ephemeral=True)
            
            preguntas_obligatorias = [p for p in self.data_manager.preguntas_desplegables if str(p.get('Obligatorio', 'NO')).upper() == 'SI']
            faltan = [p.get('Pregunta') for p in preguntas_obligatorias if p.get('Pregunta') not in self.respuestas_desplegables]
            
            if faltan:
                return await interaction.response.send_message(f"⚠️ Debes responder: {', '.join(faltan[:3])}", ephemeral=True)
            
            await interaction.response.send_modal(FormularioReclutaModal(self.usuario, self.canal_ticket, self.respuestas_desplegables, self.data_manager))
        continuar_btn.callback = continuar_callback
        self.add_item(continuar_btn)

class ConfirmarAccionView(discord.ui.View):
    def __init__(self, accion, usuario, canal_ticket, data_manager):
        super().__init__(timeout=60)
        self.accion = accion
        self.usuario = usuario
        self.canal_ticket = canal_ticket
        self.data_manager = data_manager

    @discord.ui.button(label="Sí, confirmar", style=discord.ButtonStyle.success)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            if self.accion == "aceptar":
                rol_id = self.data_manager.cache_roles_auto.get('aceptar')
                if rol_id:
                    rol = interaction.guild.get_role(rol_id)
                    if rol and rol not in self.usuario.roles: await self.usuario.add_roles(rol)
                
                cat_id = self.data_manager.cache_categorias.get('aprobados')
                if cat_id:
                    categoria = interaction.guild.get_channel(cat_id)
                    if categoria: await self.canal_ticket.edit(category=categoria)
                
                await self.actualizar_estado_excel(self.usuario.id, "Aceptado")
                await interaction.followup.send(f"✅ {self.usuario.mention} ha sido **ACEPTADO**", ephemeral=True)
                await self.data_manager.enviar_log(interaction.client, "reclutamiento_aprobado", f"✅ {self.usuario.mention} ha sido aceptado por {interaction.user.mention}", discord.Color.green())
                
            elif self.accion == "revision":
                cat_id = self.data_manager.cache_categorias.get('revision')
                if cat_id:
                    categoria = interaction.guild.get_channel(cat_id)
                    if categoria: await self.canal_ticket.edit(category=cاتegoria)
                await self.actualizar_estado_excel(self.usuario.id, "En Revisión")
                await interaction.followup.send(f"⏳ {self.usuario.mention} está **EN REVISIÓN**", ephemeral=True)
                
            elif self.accion == "rechazar":
                rol_id = self.data_manager.cache_roles_auto.get('rechazar')
                if rol_id:
                    rol = interaction.guild.get_role(rol_id)
                    if rol and rol in self.usuario.roles: await self.usuario.remove_roles(rol)
                
                cat_id = self.data_manager.cache_categorias.get('rechazados')
                if cat_id:
                    categoria = interaction.guild.get_channel(cat_id)
                    if categoria: await self.canal_ticket.edit(category=categoria)
                
                await self.actualizar_estado_excel(self.usuario.id, "Rechazado")
                await interaction.followup.send(f"❌ {self.usuario.mention} ha sido **RECHAZADO**", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"🚨 Error: {e}", ephemeral=True)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Acción cancelada.", ephemeral=True)

    async def actualizar_estado_excel(self, user_id, nuevo_estado):
        try:
            records = self.data_manager.sheets["registro_reclutas"].get_all_records()
            for i, row in enumerate(records, start=2):
                if str(row.get('ID_Usuario', '')) == str(user_id):
                    self.data_manager.sheets["registro_reclutas"].update_cell(i, 5, nuevo_estado)
                    return True
            return False
        except Exception as e:
            print(f"🚨 Error actualizando Excel: {e}")
            return False

class BotonesGestionView(discord.ui.View):
    def __init__(self, usuario_id, canal_ticket, data_manager):
        super().__init__(timeout=None)
        self.usuario_id = usuario_id
        self.canal_ticket = canal_ticket
        self.data_manager = data_manager

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.data_manager.cache_roles_staff: self.data_manager._cargar_roles()
        es_staff = any(rol.id in self.data_manager.cache_roles_staff for rol in interaction.user.roles)
        if not (es_staff or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ No tienes permisos para gestionar esta solicitud.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Aceptar", style=discord.ButtonStyle.success, custom_id="recluta:aceptar")
    async def aceptar_recluta(self, interaction: discord.Interaction, button: discord.ui.Button):
        usuario = interaction.guild.get_member(self.usuario_id)
        if not usuario: return await interaction.response.send_message("❌ No se encontró al usuario.", ephemeral=True)
        await interaction.response.send_message(f"️ ¿Confirmas que deseas **ACEPTAR** a {usuario.mention}?", view=ConfirmarAccionView("aceptar", usuario, self.canal_ticket, self.data_manager), ephemeral=True)

    @discord.ui.button(label="⏳ En Revisión", style=discord.ButtonStyle.primary, custom_id="recluta:revision")
    async def revision_recluta(self, interaction: discord.Interaction, button: discord.ui.Button):
        usuario = interaction.guild.get_member(self.usuario_id)
        if not usuario: return await interaction.response.send_message("❌ No se encontró al usuario.", ephemeral=True)
        await interaction.response.send_message(f" ¿Confirmas que deseas poner a {usuario.mention} **EN REVISIÓN**?", view=ConfirmarAccionView("revision", usuario, self.canal_ticket, self.data_manager), ephemeral=True)

    @discord.ui.button(label="❌ Rechazar", style=discord.ButtonStyle.danger, custom_id="recluta:rechazar")
    async def rechazar_recluta(self, interaction: discord.Interaction, button: discord.ui.Button):
        usuario = interaction.guild.get_member(self.usuario_id)
        if not usuario: return await interaction.response.send_message("❌ No se encontró al usuario.", ephemeral=True)
        await interaction.response.send_message(f"❌ ¿Confirmas que deseas **RECHAZAR** a {usuario.mention}?", view=ConfirmarAccionView("rechazar", usuario, self.canal_ticket, self.data_manager), ephemeral=True)

class BienvenidaReclutaView(discord.ui.View):
    def __init__(self, usuario, data_manager):
        super().__init__(timeout=None)
        self.usuario = usuario
        self.data_manager = data_manager

    @discord.ui.button(label="📝 Rellenar solicitud de ingreso", style=discord.ButtonStyle.primary, custom_id="recluta:formulario")
    async def abrir_formulario(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.usuario: return await interaction.response.send_message("❌ Este formulario es solo para el usuario mencionado.", ephemeral=True)
        if not self.data_manager.preguntas_reclutamiento: return await interaction.response.send_message("❌ No hay preguntas configuradas.", ephemeral=True)
        await interaction.response.send_modal(FormularioReclutaModal(self.usuario, interaction.channel, {}, self.data_manager))

class RecruitmentCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if isinstance(channel, discord.TextChannel) and "ticket" in channel.name.lower():
            await self.bot.data_manager.enviar_log(self.bot, "reclutamiento_ticket", f"🎫 **Nuevo ticket creado**: {channel.mention}", discord.Color.green())
            # Aquí va tu lógica de buscar al usuario en el historial y llamar a self.enviar_bienvenida_recluta(channel, usuario)

    @commands.hybrid_command(name="recluta", description="Enviar formulario de ingreso manualmente en un ticket")
    async def recluta_manual(self, interaction: discord.Interaction, usuario: discord.Member):
        config = self.bot.data_manager.cache_reclutamiento
        es_ticket = False
        if config.get('CATEGORIA_TICKETS_ID', '') and interaction.channel.category_id:
            if str(interaction.channel.category_id) == config.get('CATEGORIA_TICKETS_ID', ''): es_ticket = True
        if not es_ticket and interaction.channel.name.lower().startswith('ticket-'): es_ticket = True
        
        if not es_ticket: return await interaction.response.send_message(" Este comando solo funciona en canales de ticket.", ephemeral=True)
        await interaction.response.send_message("🔄 Enviando bienvenida...", ephemeral=True)
        await self.enviar_bienvenida_recluta(interaction.channel, usuario)
        await interaction.followup.send(f"✅ Bienvenida enviada a {usuario.mention}", ephemeral=True)

    @commands.hybrid_command(name="ficha", description="Mostrar ficha oficial del miembro")
    async def ficha_comando(self, interaction: discord.Interaction, usuario: discord.Member):
        await interaction.response.defer(ephemeral=True)
        records = self.bot.data_manager.sheets["registro_reclutas"].get_all_records()
        ficha = next((row for row in records if str(row.get('ID_Usuario', '')) == str(usuario.id)), None)
            
        if not ficha:
            return await interaction.followup.send(f"❌ **{usuario.mention}** no tiene ficha registrada.", ephemeral=True)
        
        embed = discord.Embed(title="📋 FICHA OFICIAL - JINETES MC", color=discord.Color.gold())
        embed.set_thumbnail(url=usuario.display_avatar.url)
        
        for key, value in ficha.items():
            if value and key not in ['Fecha', 'Usuario_Discord', 'ID_Usuario', 'Canal_Ticket', 'Estado']:
                embed.add_field(name=f"📌 {key}", value=f"**{value}**", inline=False)
        
        embed.set_footer(text=f"ID: {usuario.id}")
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(f" **Ficha de {usuario.mention}**", embed=embed, ephemeral=True)

    async def construir_y_enviar_embed(self, interaction, todas_las_respuestas, respuestas_desplegables):
        config = self.bot.data_manager.cache_reclutamiento
        preguntas = self.bot.data_manager.preguntas_reclutamiento
        
        embed = discord.Embed(title="📋 SOLICITUD DE INGRESO", color=discord.Color.gold())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        
        titulo_personalizado = None
        descripcion_partes = []
        campos = []
        
        for pregunta, respuesta in respuestas_desplegables.items():
            campos.append((f"📌 {pregunta}", f"**{respuesta}**"))
        
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
        
        embed.add_field(name=" Estado", value="⏳ **Pendiente de revisión**", inline=False)
        embed.set_footer(text=f"ID: {interaction.user.id} | Ticket: {interaction.channel.name}")
        
        view = BotonesGestionView(interaction.user.id, interaction.channel, self.bot.data_manager)
        await interaction.channel.send(embed=embed, view=view)
        
        await self.bot.data_manager.enviar_log(self.bot, "reclutamiento_formulario", f"📝 **{interaction.user.mention}** ha enviado su ficha en {interaction.channel.mention}", discord.Color.yellow())
        self.guardar_recluta_en_excel(interaction.user, interaction.channel, todas_las_respuestas, respuestas_desplegables)
        
        if titulo_personalizado and interaction.channel:
            try:
                nombre_limpio = str(titulo_personalizado).lower().replace(' ', '-')[:20]
                await interaction.channel.edit(name=f"ficha-{nombre_limpio}")
            except: pass
        
        msg_info_extra = self.bot.data_manager.cache_mensajes.get('MSG_INFO_EXTRA', '')
        if msg_info_extra: await interaction.channel.send(content=f"**{interaction.user.mention}**,\n\n{msg_info_extra}")
        
        await interaction.followup.send("✅ **Solicitud enviada correctamente.** Un administrador la revisará pronto.", ephemeral=True)

    def guardar_recluta_en_excel(self, usuario, canal, respuestas_formulario, respuestas_desplegables):
        try:
            ahora = datetime.datetime.now(datetime.timezone.utc)
            fila = [ahora.strftime('%d/%m/%Y %H:%M'), usuario.display_name, str(usuario.id), canal.name if canal else 'Desconocido', 'Pendiente']
            
            for p in self.bot.data_manager.preguntas_desplegables:
                fila.append(respuestas_desplegables.get(p.get('Pregunta', ''), ''))
            for pregunta_texto, respuesta_texto in respuestas_formulario:
                fila.append(respuesta_texto)
            
            self.bot.data_manager.sheets["registro_reclutas"].append_row(fila, value_input_option='USER_ENTERED')
            return True
        except Exception as e:
            print(f"🚨 Error al guardar en Excel: {e}")
            return False

    async def enviar_bienvenida_recluta(self, canal, usuario):
        config = self.bot.data_manager.cache_reclutamiento
        if self.bot.data_manager.preguntas_desplegables:
            try:
                view = MenuDesplegableView(usuario, canal, self.bot.data_manager)
                mensaje = await canal.send(
                    content=f"👋 **{usuario.mention}**, bienvenido al proceso de reclutamiento de **Jinetes MC**.\n\nPor favor, selecciona tus respuestas en los menús desplegables y luego pulsa el botón para continuar.",
                    view=view
                )
                await self.bot.data_manager.enviar_log(self.bot, "reclutamiento_ticket", f"📋 Menús desplegables enviados a {usuario.mention} en {canal.mention}", discord.Color.blue())
            except Exception as e:
                print(f" ERROR ENVIANDO MENÚS: {e}")
        else:
            mensaje_base = config.get('MENSAJE_BIENVENIDA', '¡Bienvenido {user}!')
            mensaje_final = mensaje_base.replace('{user}', usuario.mention)
            view = BienvenidaReclutaView(usuario, self.bot.data_manager)
            await canal.send(content=mensaje_final, view=view)

async def setup(bot):
    await bot.add_cog(RecruitmentCog(bot))
