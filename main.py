from discord_bot import DiscordBot
import discord
from rag import persis_listening, persis_messages, forget_all

def run():
    intents = discord.Intents.default()
    intents.message_content = True

    bot = DiscordBot(command_prefix='/', intents=intents, persist_listening=persist_listening, persist_messages=persist_messages)
    bot.messages = messages
    bot.listening = listening

    @bot.command(aliases=['l'])
    async def llama(ctx, *query):
        # ...

    bot.run(settings.DISCORD_API_SECRET, root_logger=True)