import discord
from discord.ext import commands, tasks
import sys

class BotEventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        sys.stdout.write("🚀 " + "="*50 + "\n")
        sys.stdout.write(f"✅ Bot Jinetes MC CONECTADO\n")
        sys.stdout.write(f" Usuario: {self.bot.user.name} (ID: {self.bot.user.id})\n")
        sys.stdout.write("🚀 " + "="*50 + "\n")
        sys.stdout.flush()
        
        try:
            await self.bot.tree.sync()
            await self.bot.data_manager.enviar_log(self.bot, "sistema", " Bot Jinetes MC conectado y listo", discord.Color.green())
        except Exception as e:
            print(f"🚨 Error en sync: {e}")

        if not self.ping_keeping_alive.is_running():
            self.ping_keeping_alive.start()

    @tasks.loop(minutes=5)
    async def ping_keeping_alive(self):
        if self.bot.is_ready():
            print(f"💓 Ping - Latencia: {round(self.bot.latency * 1000)}ms")

async def setup(bot):
    await bot.add_cog(BotEventsCog(bot))
