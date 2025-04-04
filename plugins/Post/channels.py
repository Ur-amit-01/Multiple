from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from plugins.helper.db import db  # Database 
import time
import random
import asyncio
from config import *

# Command to add the current channel to the database
@Client.on_message(filters.command("add") & filters.channel & filters.user(ADMIN))
async def add_current_channel(client, message: Message):

    channel_id = message.chat.id
    channel_name = message.chat.title

    try:
        added = await db.add_channel(channel_id, channel_name)
        if added:
            await message.reply(f"**Channel '{channel_name}' added! ✅**")
        else:
            await message.reply(f"ℹ️ Channel '{channel_name}' already exists.")
    except Exception as e:
        print(f"Error adding channel: {e}")
        await message.reply("❌ Failed to add channel. Contact developer.")

# Command to remove the current channel from the database
@Client.on_message(filters.command("rem") & filters.channel & filters.user(ADMIN))
async def remove_current_channel(client, message: Message):

    channel_id = message.chat.id
    channel_name = message.chat.title

    try:
        if await db.is_channel_exist(channel_id):
            await db.delete_channel(channel_id)
            await message.reply(f"**Channel '{channel_name}' removed from my database!**")
        else:
            await message.reply(f"ℹ️ Channel '{channel_name}' not found.")
    except Exception as e:
        print(f"Error removing channel: {e}")
        await message.reply("❌ Failed to remove channel. Try again.")

# Command to list all connected channels
@Client.on_message(filters.command("channels") & filters.private & filters.user(ADMIN))
async def list_channels(client, message: Message):
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)  # React with a random emoji
    except:
        pass

    # Retrieve all channels from the database
    channels = await db.get_all_channels()

    if not channels:
        await message.reply("**No channels connected yet.🙁**")
        return

    valid_channels = []
    removed_channels = []

    for channel in channels:
        channel_id = channel['_id']
        try:
            # Check if bot is admin in the channel
            chat = await client.get_chat(channel_id)
            if chat.type == "channel":
                member = await client.get_chat_member(channel_id, "me")
                if member.can_post_messages:
                    valid_channels.append(channel)
                else:
                    # Remove channel if bot can't post messages
                    await db.delete_channel(channel_id)
                    removed_channels.append(channel['name'])
            else:
                # Remove if it's not a channel anymore
                await db.delete_channel(channel_id)
                removed_channels.append(channel['name'])
        except Exception as e:
            print(f"Error checking channel {channel_id}: {e}")
            # Remove channel if any error occurs (likely not admin or channel doesn't exist)
            await db.delete_channel(channel_id)
            removed_channels.append(channel['name'])

    if removed_channels:
        removal_msg = "**Removed channels where I'm not admin:**\n" + "\n".join(f"• {name}" for name in removed_channels)
        await message.reply(removal_msg)

    if not valid_channels:
        await message.reply("**No valid channels connected. All channels were removed where I'm not admin.**")
        return

    total_channels = len(valid_channels)

    # Format the list of valid channels
    channel_list = [f"• **{channel['name']}** :- `{channel['_id']}`" for channel in valid_channels]
    response = (
        f"> **Total Valid Channels: {total_channels}**\n\n"
        + "\n".join(channel_list)
    )

    await message.reply(response)
