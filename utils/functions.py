import discord
import asyncio

async def delete_message_later(message, delay):
    await asyncio.sleep(delay)
    try:
        await asyncio.sleep(1)
        await message.delete()
    except discord.errors.HTTPException as e:
        if e.code == 429:
            await asyncio.sleep(5)