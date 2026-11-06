import discord
from discord.ext import commands
import datetime
from utils.data import (
    PREGUNTAS_RECLUTAMIENTO, PREGUNTAS_DESPLEGABLES, CACHE_ROLES_STAFF, CACHE_CATEGORIAS,
    CACHE_ROLES_AUTO, CACHE_MENSAJES, sheet_registro_reclutas,
    cargar_config_reclutamiento, cargar_preguntas_reclutamiento, cargar_config_embed,
    aplicar_formato_texto, enviar_log
)

# ==========================================
# CONFIGURACIÓN DE FUNCIONALIDADES
# ==========================================
ACTIVAR_BOTONES_GESTION = False  # Cambia a True cuando quieras activar los botones de Aceptar/Rechazar/Revisión

# ==========================================
# MODALES
# ==========================================
class FormularioReclutaModal(discord.ui.Modal):
    def __init__(self, usuario, canal_ticket, respuestas_desplegables):
        self.usuario = usuario
        self.canal_ticket = canal_ticket
        self.respuestas_desplegables = respuestas_desplegables
        self.pagina_actual = 1
        self.total_paginas = max(1, (len(PREGUNTAS_RECLUTAMIENTO) + 4) // 5)
        self.respuestas_previas = []
        super().__init__(title=f"Solicitud ({self.pagina_actual}/{self.total_paginas})", custom_id=f"recluta_modal_p1")
        
        preguntas_pagina = PREGUNTAS_RECLUTAMIENTO[0:5]
        if not preguntas_pagina:
            self.add_item(discord.ui.TextInput(label="Sin preguntas", placeholder="Contacta admin", required=False, max_length=100))
            return
        for i, p in enumerate(preguntas_pagina):
            try:
                pregunta = str(p.get('Pregunta', f'Pregunta {i+1}'))
                placeholder = str(p.get('Placeholder', 'Escribe tu respuesta...'))
                obligatoria = str(p.get('Obligatoria', 'NO')).upper() == 'SI'
                estilo = discord.TextStyle.paragraph if any(pal in pregunta.lower() for pal in ['larga', 'motivación', 'experiencia', 'historia', 'backstory', 'por qué', 'detalla', 'describe']) else discord.TextStyle.short
                label_base = pregunta.rstrip('*').strip()
                if len(label_base) > 43: label_base = label_base[:40] + "..."
                label_final = f"{label_base}{'*' if obligatoria else ''}"
                max_len = 4000 if estilo == discord.TextStyle.paragraph else 100
                self.add_item(discord.ui.TextInput(label=label_final, placeholder=placeholder[:100], required=obligatoria, style=estilo, max_length=max_len))
            except:
                self.add_item(discord.ui.TextInput(label=f"Pregunta {i+1}", placeholder="...", required=False, max_length=100))

    async def on_submit(self, interaction: discord.Interaction):
        respuestas_pagina = [(child.label.rstrip(' *').strip(), child.value) for child in self.children]
        todas = self.respuestas_previas + respuestas_pagina
        if self.pagina_actual < self.total_paginas:
            sig = self.pagina_actual + 1
            await interaction.response.send_modal(FormularioReclutaModalPaginado(
                self.usuario, self.canal_ticket, self.respuestas_desplegables,
                PREGUNTAS_RECLUTAMIENTO[(sig-1)*5:sig*5], sig, self.total_paginas, todas
            ))
        else:
            await interaction.response.defer(ephemeral=True)
            await construir_y_enviar_embed(interaction, todas, self.respuestas_desplegables)


class FormularioReclutaModalPaginado(discord.ui.Modal):
    def __init__(self, usuario, canal_ticket, respuestas_desplegables, preguntas, pagina_actual, total_paginas, respuestas_previas):
        self.usuario = usuario
        self.canal_ticket = canal_ticket
        self.respuestas_desplegables = respuestas_desplegables
        self.pagina_actual = pagina_actual
        self.total_paginas = total_paginas
        self.respuestas_previas = respuestas_previas
        super().__init__(title=f"Solicitud ({pagina_actual}/{total_paginas})", custom_id=f"recluta_modal_p{pagina_actual}")
        if not preguntas:
            self.add_item(discord.ui.TextInput(label="Fin", placeholder="...", required=False, max_length=100))
            return
        for i, p in enumerate(preguntas):
            try:
                pregunta = str(p.get('Pregunta', f'Pregunta {i+1}'))
                placeholder = str(p.get('Placeholder', '...'))
                obligatoria = str(p.get('Obligatoria', 'NO')).upper() == 'SI'
                estilo = discord.TextStyle.paragraph if any(pal in pregunta.lower() for pal in ['larga', 'motivación', 'experiencia', 'historia', 'backstory', 'por qué', 'detalla', 'describe']) else discord.TextStyle.short
                label_base = pregunta.rstrip('*').strip()
                if len(label_base) > 43: label_base = label_base[:40] + "..."
                label_final = f"{label_base}{'*' if obligatoria else ''}"
                max_len = 4000 if estilo == discord.TextStyle.paragraph else 100
                self.add_item(discord.ui.TextInput(label=label_final, placeholder=placeholder[:100], required=obligatoria, style=estilo, max_length=max_len))
            except:
                self.add_item(discord.ui.TextInput(label=f"Pregunta {i+1}", placeholder="...", required=False, max_length=100))

    async def on_submit(self, interaction: discord.Interaction):
        respuestas_pagina = [(child.label.rstrip(' *').strip(), child.value) for child in self.children]
        todas = self.respuestas_previas + respuestas_pagina
        if self.pagina_actual < self.total_paginas:
            sig = self.pagina_actual + 1
            await interaction.response.send_modal(FormularioReclutaModalPaginado(
                self.usuario, self.canal_ticket, self.respuestas_desplegables,
                PREGUNTAS_RECLUTAMIENTO[(sig-1)*5:sig*5], sig, self.total_paginas, todas
            ))
        else:
            await interaction.response.defer(ephemeral=True)
            await construir_y_enviar_embed(interaction, todas, self.respuestas_desplegables)


# ==========================================
# VIEWS
# ==========================================
class MenuDesplegableView(discord.ui.View):
    def __init__(self, usuario, canal_ticket):
        super().__init__(timeout=300)
        self.usuario = usuario
        self.canal_ticket = canal_ticket
        self.respuestas_desplegables = {}
        self.build_menus()
    
    def build_menus(self):
        for pregunta in PREGUNTAS_DESPLEGABLES:
            opciones = [opt.strip() for opt in str(pregunta.get('Opciones', '')).split(',') if opt.strip()]
            if opciones:
                select = discord.ui.Select(
                    placeholder=pregunta.get('Pregunta', 'Selecciona...')[:100], 
                    options=[discord.SelectOption(label=opt[:100], value=opt[:100]) for opt in opciones[:25]], 
                    min_values=1, 
                    max_values=1
                )
                
                async def select_callback(interaction: discord.Interaction, select=select, pregunta=pregunta):
                    await interaction.response.defer(ephemeral=True)
                    self.respuestas_desplegables[pregunta.get('Pregunta')] = select.values[0]
                    # Mensaje de confirmación oculto por ahora. Para activarlo, descomenta la siguiente línea:
                    # await interaction.followup.send(f"✅ Seleccionado: {select.values[0]}", ephemeral=True)
                
                select.callback = select_callback
                self.add_item(select)
        
        btn = discord.ui.Button(label="📝 Continuar con formulario", style=discord.ButtonStyle.primary, custom_id="recluta:continuar")
        
        async def continuar(interaction: discord.Interaction):
            if interaction.user != self.usuario: 
                return await interaction.response.send_message("❌ Este formulario es solo para ti.", ephemeral=True)
            oblig = [p for p in PREGUNTAS_DESPLEGABLES if str(p.get('Obligatorio', 'NO')).upper() == 'SI']
            faltan = [p.get('Pregunta') for p in oblig if p.get('Pregunta') not in self.respuestas_desplegables]
            if faltan: 
                return await interaction.response.send_message(f"⚠️ Debes responder: {', '.join(faltan[:3])}", ephemeral=True)
            await interaction.response.send_modal(FormularioReclutaModal(self.usuario, self.canal_ticket, self.respuestas_desplegables))
        
        btn.callback = continuar
        self.add_item(btn)


class BienvenidaReclutaView(discord.ui.View):
    def __init__(self, usuario):
        super().__init__(timeout=None)
        self.usuario = usuario
    
    @discord.ui.button(label="📝 Rellenar solicitud de ingreso", style=discord.ButtonStyle.primary, custom_id="recluta:formulario")
    async def abrir_formulario(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.usuario: 
            return await interaction.response.send_message("❌ Este formulario es solo para el usuario mencionado.", ephemeral=True)
        if not PREGUNTAS_RECLUTAMIENTO: 
            return await interaction.response.send_message("❌ No hay preguntas configuradas.", ephemeral=True)
        await interaction.response.send_modal(FormularioReclutaModal(self.usuario, interaction.channel, {}))


class BotonesGestionView(discord.ui.View):
    def __init__(self, usuario_id, canal_ticket):
        super().__init__(timeout=None)
        self.usuario_id = usuario_id
        self.canal_ticket = canal_ticket

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Si los botones están desactivados, no permitir interacción
        if not ACTIVAR_BOTONES_GESTION:
            await interaction.response.send_message("⚠️ Los botones de gestión están desactivados.", ephemeral=True)
            return False
        
        es_staff = any(rol.id in CACHE_ROLES_STAFF for rol in interaction.user.roles)
        if not (es_staff or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ No tienes permisos.", ephemeral=True)
            return False
        return True

    # Los botones solo se muestran si ACTIVAR_BOTONES_GESTION es True
    @discord.ui.button(label="✅ Aceptar", style=discord.ButtonStyle.success, custom_id="recluta:aceptar")
    async def aceptar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not ACTIVAR_BOTONES_GESTION:
            button.disabled = True
            await interaction.response.edit_message(view=self)
            return
        usuario = interaction.guild.get_member(self.usuario_id)
        if not usuario: 
            return await interaction.response.send_message("❌ Usuario no encontrado.", ephemeral=True)
        await interaction.response.send_message(f"¿Confirmas **ACEPTAR** a {usuario.mention}?", view=ConfirmarAccionView("aceptar", usuario, self.canal_ticket), ephemeral=True)

    @discord.ui.button(label="⏳ En Revisión", style=discord.ButtonStyle.primary, custom_id="recluta:revision")
    async def revision(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not ACTIVAR_BOTONES_GESTION:
            button.disabled = True
            await interaction.response.edit_message(view=self)
            return
        usuario = interaction.guild.get_member(self.usuario_id)
        if not usuario: 
            return await interaction.response.send_message("❌ Usuario no encontrado.", ephemeral=True)
        await interaction.response.send_message(f"¿Confirmas poner a {usuario.mention} **EN REVISIÓN**?", view=ConfirmarAccionView("revision", usuario, self.canal_ticket), ephemeral=True)

    @discord.ui.button(label="❌ Rechazar", style=discord.ButtonStyle.danger, custom_id="recluta:rechazar")
    async def rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not ACTIVAR_BOTONES_GESTION:
            button.disabled = True
            await interaction.response.edit_message(view=self)
            return
        usuario = interaction.guild.get_member(self.usuario_id)
        if not usuario: 
            return await interaction.response.send_message("❌ Usuario no encontrado.", ephemeral=True)
        await interaction.response.send_message(f"¿Confirmas **RECHAZAR** a {usuario.mention}?", view=ConfirmarAccionView("rechazar", usuario, self.canal_ticket), ephemeral=True)

    async def on_timeout(self):
        # Deshabilitar todos los botones cuando expire el timeout
        for item in self.children:
            item.disabled = True


class ConfirmarAccionView(discord.ui.View):
    def __init__(self, accion, usuario, canal_ticket):
        super().__init__(timeout=60)
        self.accion = accion
        self.usuario = usuario
        self.canal_ticket = canal_ticket

    @discord.ui.button(label="Sí, confirmar", style=discord.ButtonStyle.success)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            if self.accion == "aceptar":
                rol_id = CACHE_ROLES_AUTO.get('aceptar')
                if rol_id:
                    rol = interaction.guild.get_role(rol_id)
                    if rol and rol not in self.usuario.roles: 
                        await self.usuario.add_roles(rol)
                cat_id = CACHE_CATEGORIAS.get('aprobados')
                if cat_id:
                    cat = interaction.guild.get_channel(cat_id)
                    if cat: 
                        await self.canal_ticket.edit(category=cat)
                await actualizar_estado_excel(self.usuario.id, "Aceptado")
                await interaction.followup.send(f"✅ {self.usuario.mention} ha sido **ACEPTADO**", ephemeral=True)
                await enviar_log("reclutamiento_aprobado", f"✅ {self.usuario.mention} aceptado por {interaction.user.mention}", discord.Color.green())
            elif self.accion == "revision":
                cat_id = CACHE_CATEGORIAS.get('revision')
                if cat_id:
                    cat = interaction.guild.get_channel(cat_id)
                    if cat: 
                        await self.canal_ticket.edit(category=cat)
                await actualizar_estado_excel(self.usuario.id, "En Revisión")
                await interaction.followup.send(f"⏳ {self.usuario.mention} está **EN REVISIÓN**", ephemeral=True)
            elif self.accion == "rechazar":
                rol_id = CACHE_ROLES_AUTO.get('rechazar')
                if rol_id:
                    rol = interaction.guild.get_role(rol_id)
                    if rol and rol in self.usuario.roles: 
                        await self.usuario.remove_roles(rol)
                cat_id = CACHE_CATEGORIAS.get('rechazados')
                if cat_id:
                    cat = interaction.guild.get_channel(cat_id)
                    if cat: 
                        await self.canal_ticket.edit(category=cat)
                await actualizar_estado_excel(self.usuario.id, "Rechazado")
                await interaction.followup.send(f"❌ {self.usuario.mention} ha sido **RECHAZADO**", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"🚨 Error: {e}", ephemeral=True)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Acción cancelada.", ephemeral=True)


# ==========================================
# FUNCIONES AUXILIARES
# ==========================================
async def actualizar_estado_excel(user_id, nuevo_estado):
    try:
        records = sheet_registro_reclutas.get_all_records()
        for i, row in enumerate(records, start=2):
            if str(row.get('ID_Usuario', '')) == str(user_id):
                sheet_registro_reclutas.update_cell(i, 5, nuevo_estado)
                return True
        return False
    except Exception as e:
        print(f"🚨 Error actualizando Excel: {e}")
        return False


def guardar_recluta_en_excel(usuario, canal, respuestas_formulario, respuestas_desplegables):
    try:
        ahora = datetime.datetime.now(datetime.timezone.utc)
        fila = [ahora.strftime('%d/%m/%Y %H:%M'), usuario.display_name, str(usuario.id), canal.name if canal else 'Desconocido', 'Pendiente']
        for p in PREGUNTAS_DESPLEGABLES: 
            fila.append(respuestas_desplegables.get(p.get('Pregunta', ''), ''))
        for _, respuesta_texto in respuestas_formulario: 
            fila.append(respuesta_texto)
        sheet_registro_reclutas.append_row(fila, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        print(f"🚨 Error al guardar en Excel: {e}")
        return False


async def construir_y_enviar_embed(interaction, todas_las_respuestas, respuestas_desplegables):
    preguntas = cargar_preguntas_reclutamiento()
    config_embed = cargar_config_embed()
    
    # 1. Recopilar todos los datos disponibles
    datos = {}
    for i, (pregunta_texto, respuesta_texto) in enumerate(todas_las_respuestas, start=1): 
        datos[f'Pregunta_{i}'] = respuesta_texto
    
    for pregunta, respuesta in respuestas_desplegables.items():
        idx = next((i for i, p in enumerate(PREGUNTAS_DESPLEGABLES) if p.get('Pregunta') == pregunta), -1)
        if idx >= 0: 
            datos[f'Pregunta_Desplegable_{idx+1}'] = respuesta
            
    datos['Fecha'] = datetime.datetime.now(datetime.timezone.utc).strftime('%d/%m/%Y %H:%M')
    datos['Usuario_Discord'] = interaction.user.display_name
    datos['ID_Usuario'] = str(interaction.user.id)
    datos['Canal_Ticket'] = interaction.channel.name
    datos['Estado'] = '⏳ Pendiente de revisión'
    
    # 2. Crear el embed base
    embed = discord.Embed(
        title="📋 SOLICITUD DE INGRESO - JINETES MC", 
        color=discord.Color.gold(), 
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    
    # 3. Aplicar configuración de Config_Embed (o fallback al sistema antiguo)
    config_solicitud = config_embed.get('solicitud', [])
    if config_solicitud:
        for campo in config_solicitud:
            if not campo['mostrar']: 
                continue
            valor = datos.get(campo['campo'], '')
            if not valor: 
                continue
            valor_fmt = aplicar_formato_texto(str(valor), campo['formato'])
            titulo = f"{campo['icono']} {campo['titulo']}".strip()
            embed.add_field(name=titulo, value=valor_fmt, inline=False)
    else:
        # Fallback: comportamiento antiguo
        for pregunta, respuesta in respuestas_desplegables.items(): 
            embed.add_field(name=f"📌 {pregunta}", value=f"**{respuesta}**", inline=False)
        
        for (pt, rt), pc in zip(todas_las_respuestas, preguntas):
            ub = str(pc.get('Ubicacion', 'CAMPO')).upper()
            es = str(pc.get('Estilo', 'Normal')).lower()
            if es == 'negrita': 
                rt = f"**{rt}**"
            elif es == 'cursiva': 
                rt = f"*{rt}*"
            
            if ub == 'TITULO': 
                embed.title = f"📋 SOLICITUD: {rt}"
            elif ub == 'DESCRIPCION': 
                embed.description = rt
            else: 
                embed.add_field(name=pt, value=rt, inline=False)
                
        embed.add_field(name="📊 Estado", value="⏳ **Pendiente de revisión**", inline=False)
    
    embed.set_footer(text=f"ID: {interaction.user.id} | Ticket: {interaction.channel.name}")
    
    # 4. Crear el View (los botones se mostrarán o no según ACTIVAR_BOTONES_GESTION)
    view = BotonesGestionView(interaction.user.id, interaction.channel)
    
    # Si los botones están desactivados, deshabilitarlos visualmente
    if not ACTIVAR_BOTONES_GESTION:
        for item in view.children:
            item.disabled = True
    
    # 5. Enviar el embed y los logs
    await interaction.channel.send(embed=embed, view=view)
    await enviar_log("reclutamiento_formulario", f"📝 **{interaction.user.mention}** envió ficha en {interaction.channel.mention}", discord.Color.yellow())
    guardar_recluta_en_excel(interaction.user, interaction.channel, todas_las_respuestas, respuestas_desplegables)
    
    # 6. 🔄 RENOMBRAR EL CANAL DEL TICKET (Lógica restaurada y mejorada)
    titulo_personalizado = None
    for (pregunta_texto, respuesta_texto), pregunta_config in zip(todas_las_respuestas, preguntas):
        ubicacion = str(pregunta_config.get('Ubicacion', 'CAMPO')).upper()
        if ubicacion == 'TITULO':
            titulo_personalizado = respuesta_texto
            break
            
    if titulo_personalizado and interaction.channel:
        try:
            # Limpiamos el texto: minúsculas, sin espacios (usamos guiones), y solo caracteres alfanuméricos
            nombre_limpio = str(titulo_personalizado).lower().replace(' ', '-')
            nombre_limpio = ''.join(e for e in nombre_limpio if e.isalnum() or e == '-')
            nombre_limpio = nombre_limpio[:20] # Límite de seguridad
            
            await interaction.channel.edit(name=f"⏳-{nombre_limpio}")
            print(f"✅ Canal renombrado a: ⏳-{nombre_limpio}")
        except Exception as e:
            print(f"⚠️ Error al renombrar canal: {e}")
    
    # 7. Mensaje final al usuario
    msg_info_extra = CACHE_MENSAJES.get('MSG_INFO_EXTRA', '')
    if msg_info_extra:
        await interaction.channel.send(content=f"**{interaction.user.mention}**,\n\n{msg_info_extra}")
    
    await interaction.followup.send("✅ **Solicitud enviada correctamente.** Un administrador la revisará pronto.", ephemeral=True)


async def enviar_bienvenida_recluta(canal, usuario):
    config = cargar_config_reclutamiento()
    if PREGUNTAS_DESPLEGABLES:
        view = MenuDesplegableView(usuario, canal)
        await canal.send(content=f"👋 **{usuario.mention}**, bienvenido al proceso de reclutamiento de **Jinetes MC**.\n\nSelecciona tus respuestas y pulsa continuar.", view=view)
        await enviar_log("reclutamiento_ticket", f"📋 Menús enviados a {usuario.mention} en {canal.mention}", discord.Color.blue())
    else:
        msg = config.get('MENSAJE_BIENVENIDA', '¡Bienvenido {user}!').replace('{user}', usuario.mention)
        await canal.send(content=msg, view=BienvenidaReclutaView(usuario))


# ==========================================
# COG
# ==========================================
class RecruitmentCog(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if isinstance(channel, discord.TextChannel) and "ticket" in channel.name.lower():
            await enviar_log("reclutamiento_ticket", f"🎫 **Nuevo ticket creado**: {channel.mention}", discord.Color.green())
            await channel.typing()
            import asyncio
            await asyncio.sleep(4)
            usuario_creador = None
            try:
                async for message in channel.history(limit=5):
                    if message.mentions:
                        for user in message.mentions:
                            if not user.bot:
                                usuario_creador = user
                                break
                    if usuario_creador: 
                        break
            except: 
                pass
            if not usuario_creador:
                try:
                    async for message in channel.history(limit=10):
                        if not message.author.bot:
                            usuario_creador = message.author
                            break
                except: 
                    pass
            if usuario_creador:
                await enviar_bienvenida_recluta(channel, usuario_creador)
            else:
                await channel.send("❌ No se pudo identificar al usuario real. Usa `/recluta @usuario` manualmente.")

    @commands.Cog.listener()
    async def on_thread_create(self, thread):
        if "ticket" in thread.name.lower():
            import asyncio
            await asyncio.sleep(3)
            try:
                async for message in thread.history(limit=10):
                    if not message.author.bot:
                        await enviar_bienvenida_recluta(thread, message.author)
                        break
            except: 
                pass

    @commands.hybrid_command(name="recluta", description="Enviar formulario de ingreso manualmente en un ticket")
    async def recluta_manual(self, ctx, usuario: discord.Member):
        config = cargar_config_reclutamiento()
        es_ticket = False
        if config.get('CATEGORIA_TICKETS_ID', '') and ctx.channel.category_id:
            if str(ctx.channel.category_id) == config.get('CATEGORIA_TICKETS_ID', ''): 
                es_ticket = True
        if not es_ticket and ctx.channel.name.lower().startswith('ticket-'): 
            es_ticket = True
        if not es_ticket: 
            return await ctx.send("⚠️ Este comando solo funciona en canales de ticket.", ephemeral=True)
        await ctx.send("🔄 Enviando bienvenida...", ephemeral=True)
        await enviar_bienvenida_recluta(ctx.channel, usuario)
        await ctx.send(f"✅ Bienvenida enviada a {usuario.mention}", ephemeral=True)

    @commands.hybrid_command(name="ficha", description="Mostrar ficha oficial del miembro")
    async def ficha_comando(self, ctx, usuario: discord.Member):
        await ctx.defer(ephemeral=True)
        records = sheet_registro_reclutas.get_all_records()
        ficha = next((row for row in records if str(row.get('ID_Usuario', '')) == str(usuario.id)), None)
        if not ficha: 
            return await ctx.send(f"❌ **{usuario.mention}** no tiene ficha registrada.", ephemeral=True)
        
        config_embed = cargar_config_embed()
        embed = discord.Embed(
            title="📋 FICHA OFICIAL - JINETES MC", 
            color=discord.Color.gold(), 
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_thumbnail(url=usuario.display_avatar.url)
        
        config_ficha = config_embed.get('ficha', [])
        if config_ficha:
            for campo in config_ficha:
                if not campo['mostrar']: 
                    continue
                valor = ficha.get(campo['campo'], '')
                if not valor: 
                    continue
                valor_fmt = aplicar_formato_texto(str(valor), campo['formato'])
                titulo = f"{campo['icono']} {campo['titulo']}".strip()
                embed.add_field(name=titulo, value=valor_fmt, inline=False)
        else:
            if ficha.get('Fecha'): 
                embed.add_field(name="📅 Fecha", value=f"**{ficha['Fecha']}**", inline=False)
            if ficha.get('Usuario_Discord'): 
                embed.add_field(name="👤 Usuario", value=f"**{ficha['Usuario_Discord']}**", inline=False)
            if ficha.get('Estado'): 
                embed.add_field(name="📊 Estado", value=f"**{ficha['Estado']}**", inline=False)
            for key, value in ficha.items():
                if key.startswith('Pregunta_') and value: 
                    embed.add_field(name=f"📌 {key}", value=f"**{value}**", inline=False)
        
        embed.set_footer(text=f"ID: {usuario.id}")
        await ctx.send(f"📋 Ficha de {usuario.mention}", embed=embed, ephemeral=True)


async def setup(bot): 
    await bot.add_cog(RecruitmentCog(bot))
