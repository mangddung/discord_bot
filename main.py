import discord
from discord import app_commands
from discord.ext import commands
from db import engine, Base
from utils.logger import logger

import os
import sys
import json
from dotenv import load_dotenv
load_dotenv()

if not os.path.isfile(f"{os.path.realpath(os.path.dirname(__file__))}/config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open(f"{os.path.realpath(os.path.dirname(__file__))}/config.json", encoding="utf-8") as file:
        config = json.load(file)

discord_token = os.getenv('DISCORD_TOKEN')
# typecast_api =os.getenv('TYPECAST_API')
bot_prefix = config["prefix"]

# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.presences = True
intents.reactions = True
intents.voice_states = True
intents.guild_messages = True
intents.guild_reactions = True

bot = commands.Bot(command_prefix=bot_prefix, intents=intents)

class DiscordBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned_or(config["prefix"]),
            intents=intents,
            help_command=None,
        )
        self.config = config

    async def load_cogs(self) -> None:
        for file in os.listdir(f"{os.path.realpath(os.path.dirname(__file__))}/cogs"):
            if file.endswith(".py"):
                extension = file[:-3]
                try:
                    await self.load_extension(f"cogs.{extension}")
                    logger.info(f"Loaded extension '{extension}'")
                except Exception as e:
                    exception = f"{type(e).__name__}: {e}"
                    logger.error(f"Failed to load extension {extension}\n{exception}")
        # SQLAlchemy DB 설정
        Base.metadata.create_all(bind=engine)

    async def on_ready(self) -> None:
        await self.change_presence(activity=discord.Game(name=config["bot_activity"]))
        synced = await self.tree.sync()
        logger.info(f"{len(synced)}개의 슬래시 명령어가 동기화됨!")

    async def setup_hook(self) -> None:
        await self.load_cogs()


load_dotenv()

bot = DiscordBot()
bot.run(discord_token)