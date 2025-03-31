from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from plugins.helper.db import db
import time
import random
from plugins.helper.time_parser import *
import asyncio
from config import *

@Client.on_message(filters.command("post") & filters.private & filters.user(ADMIN))
async def send_post(client, message: Message):
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except:
        pass
        
    if not message.reply_to_message:
        await message.reply("**Reply to a message to post it.**")
        return

    # Parse time delay if provided
    delete_after = None
    if len(message.command) > 1:
        try:
            time_input = ' '.join(message.command[1:]).lower()
            delete_after = parse_time(time_input)
            if delete_after <= 0:
                await message.reply("❌ Time must be greater than 0")
                return
        except ValueError as e:
            await message.reply(f"❌ {str(e)}\nExample: /post 1h 30min or /post 2 hours 15 minutes")
            return

    channels = await db.get_all_channels()
    if not channels:
        await message.reply("**No channels connected yet.**")
        return

    post_id = int(time.time())
    sent_messages = []
    success_count = 0
    total_channels = len(channels)

    processing_msg = await message.reply(
        f"**📢 Posting to {total_channels} channels...**",
        reply_to_message_id=message.reply_to_message.id
    )

    for channel in channels:
        try:
            sent_message = await client.copy_message(
                chat_id=channel["_id"],
                from_chat_id=message.chat.id,
                message_id=message.reply_to_message.id
            )

            sent_messages.append({
                "channel_id": channel["_id"],
                "message_id": sent_message.id,
                "channel_name": channel.get("name", str(channel["_id"]))
            })
            success_count += 1

            if delete_after:
                asyncio.create_task(
                    auto_delete_post(
                        client=client,
                        post_id=post_id,
                        delay_seconds=delete_after,
                        processing_msg_id=processing_msg.id,
                        user_id=message.from_user.id
                    )
                )
                
        except Exception as e:
            print(f"Error posting to channel {channel['_id']}: {e}")

    if sent_messages:
        await db.save_post(post_id, sent_messages)

    result_msg = (
        f"📣 <b>Posting Completed!</b>\n\n"
        f"• <b>Post ID:</b> <code>{post_id}</code>\n"
        f"• <b>Success:</b> {success_count}/{total_channels} channels\n"
    )
    if delete_after:
        time_str = format_time(delete_after)
        result_msg += f"• <b>Auto-delete in:</b> {time_str}\n"

    if success_count < total_channels:
        result_msg += f"• <b>Failed:</b> {total_channels - success_count} channels\n"

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Delete This Post", callback_data=f"delete_{post_id}")]
    ])

    await processing_msg.edit_text(result_msg, reply_markup=reply_markup)


async def auto_delete_post(client, post_id, delay_seconds, processing_msg_id, user_id):
    """Handle automatic post deletion after delay"""
    await asyncio.sleep(delay_seconds)
    
    post = await db.get_post(post_id)
    if not post:
        return

    # Delete messages from all channels (silently ignore errors)
    for msg in post["messages"]:
        try:
            await client.delete_messages(
                chat_id=msg["channel_id"],
                message_ids=msg["message_id"]
            )
        except Exception:
            pass

    # Delete processing message if it exists
    try:
        await client.delete_messages(user_id, processing_msg_id)
    except:
        pass

    # Send simple confirmation message
    await client.send_message(
        user_id,
        f"🗑 <b>Auto Post Deleted</b>\n\n"
        f"• <b>Post ID:</b> <code>{post_id}</code>\n"
        f"• <b>Deleted from:</b> {len(post['messages'])} channels"
    )
    await db.delete_post(post_id)

