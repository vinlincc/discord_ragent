# import discord
import traceback
from discord.ext import commands
from datetime import datetime
import settings
# from models import Message
from rag import forget_all_index, remember_message, answer_query
logger = settings.logging.getLogger("bot")

def process_incoming_message(message):
  """Replace user id with handle for mentions."""
  content = message.content
  for user in message.mentions:
    mention_str = f'<@{user.id}>'
    content = content.replace(mention_str, f'@{user.name}')
  message.content = content
  return message

class DiscordBot(commands.Bot):
  def __init__(self, command_prefix, intents, persist_listening, persist_messages):
      super().__init__(command_prefix=command_prefix, intents=intents)
      self.messages = {}
      self.listening = {}
      self.persist_listening = persist_listening
      self.persist_messages = persist_messages

  async def on_ready(self):
    logger.info(f"User: {self.user} (ID: {self.user.id})")

  async def on_message(self, message):
    global listening
    # if message.author == bot.user:
    #     return
    message = process_incoming_message(message)
  
    if listening.get(message.guild.id, False):
      if message.content.startswith('/'):
        if message.content.startswith('/l') or message.content.startswith('/llama'):
          remember_message(message, True)
      else:
        remember_message(message, message.author==self.user)
  
  
    await self.process_commands(message)

  # def remember_message(self, message, save_only_message):
  #     # ...

  @commands.command(aliases=['li'])
  async def listen(self, ctx):
      self.listening[ctx.guild.id] = True
      self.persist_listening(self.listening)
      logger.info(f"Listening to messages on channel {ctx.channel.name} of server: {ctx.guild.id} "
                  f"from {datetime.now().strftime('%m-%d-%Y %H:%M:%S')}")
      await ctx.send('Listening to your messages now.')

  @commands.command(aliases=['s'])
  async def stop(self, ctx):
      self.listening[ctx.guild.id] = False
      self.persist_listening(self.listening)
      logger.info(f"Stopped Listening to messages on channel "
                  f"{ctx.channel.name} from {datetime.now().strftime('%m-%d-%Y')}")
      await ctx.send('Stopped listening to messages.')

  @commands.command(aliases=['f'])
  async def forget(self, ctx):
      self.forget_all(ctx)
      await ctx.send('All messages forgotten & stopped listening to yall')

  @commands.command(aliases=['st'])
  async def status(self, ctx):
      await ctx.send(
          "Listening to yall👂" if self.listening.get(ctx.guild.id, False) \
          else "Not Listening 🙉"
      )
  @commands.command(aliases=['l'])
  async def llama(self, ctx, *query):
      if not self.listening.get(ctx.guild.id, False):
          await ctx.message.reply(
              "I'm not listening to what y'all saying 🙈🙉🙊. "
              "\nRun \"/listen\" if you want me to start listening."
          )
          return

      if len(query) == 0:
          await ctx.message.reply("What?")
          return
      user_messages = [msg for msg in self.messages.get(ctx.guild.id, []) if msg.author != str(self.user) and not msg.just_msg.startswith("/")]
      if len(user_messages) == 0:
          await ctx.message.reply("Hey, Bot's knowledge base is empty now. Please say something before asking it questions.")
          return

      try:
          async with ctx.typing():
              await ctx.message.reply(await answer_query(" ".join(query), ctx, self, self.messages))
      except:
          tb = traceback.format_exc()
          print(tb)
          await ctx.message.reply("The bot encountered an error, will try to fix it soon. Feel free to send a dm to @rsrohan99 about it or open an issue on GitHub https://github.com/rsrohan99/llamabot, any kind of feedback is really appreciated, thanks.")


  def forget_all(self, ctx):
      try:
          self.messages.pop(ctx.guild.id)
          self.listening.pop(ctx.guild.id)
      except KeyError:
          pass
      self.persist_messages(self.messages)
      self.persist_listening(self.listening)

      forget_all_index(ctx)