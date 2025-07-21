from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from plugins.helper.db import db
import time
import random
from plugins.helper.time_parser import *
import asyncio
from config import *
from plugins.Post.admin_panel import admin_filter

async def restore_pending_deletions(client):
    """Restore pending deletions when bot starts"""
    try:
        pending_posts = await db.get_pending_deletions()
        now = time.time()
        
        for post in pending_posts:
            post_id = post["post_id"]
            delete_after = post["delete_after"] - now
            
            if delete_after > 0:  # Only if deletion is in future
                channels = post.get("channels", [])
                deletion_tasks = []
                
                for channel in channels:
                    deletion_tasks.append(
                        schedule_deletion(
                            client,
                            channel["channel_id"],
                            channel["message_id"],
                            delete_after,
                            post["user_id"],
                            post_id,
                            channel.get("channel_name", str(channel["channel_id"])),
                            post.get("confirmation_msg_id")
                        )
                    )
                
                if deletion_tasks:
                    asyncio.create_task(
                        handle_deletion_results(
                            client=client,
                            deletion_tasks=deletion_tasks,
                            post_id=post_id,
                            delay_seconds=delete_after
                        )
                    )
    except Exception as e:
        print(f"Error restoring pending deletions: {e}")


@Client.on_message(filters.command(["post", "post0", "post1", "post2", "post3"]) & filters.private & admin_filter)
async def send_post(client, message: Message):
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except:
        pass
    if not await db.is_admin(message.from_user.id):
        await message.reply("**❌ You are not authorized to use this command!**")
        return
    
    if not message.reply_to_message:
        await message.reply("**Reply to a message to post it.**")
        return

    # Determine which group to post to (default 0)
    cmd = message.command[0]
    group = "0"  # Default group
    if len(cmd) > 4:  # For post1, post2, post3
        group = cmd[-1]  # Get the last character

    delete_after = None
    time_input = None
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

    post_content = message.reply_to_message
    channels = await db.get_channels_by_group(group)  # Get channels from specific group

    if not channels:
        await message.reply(f"**No channels connected in group {group} yet.**")
        return

    post_id = int(time.time())
    sent_messages = []
    success_count = 0
    total_channels = len(channels)
    failed_channels = []

    processing_msg = await message.reply(
        f"**📢 Posting to {total_channels} channels in group {group}...**",
        reply_to_message_id=post_content.id
    )

    deletion_tasks = []
    
    for channel in channels:
        try:
            sent_message = await client.copy_message(
                chat_id=channel["channel_id"],  # Use channel_id instead of _id
                from_chat_id=message.chat.id,
                message_id=post_content.id
            )

            sent_messages.append({
                "channel_id": channel["channel_id"],
                "message_id": sent_message.id,
                "channel_name": channel.get("name", str(channel["channel_id"]))
            })
            success_count += 1

            if delete_after:
                deletion_tasks.append(
                    schedule_deletion(
                        client,
                        channel["channel_id"],
                        sent_message.id,
                        delete_after,
                        message.from_user.id,
                        post_id,
                        channel.get("name", str(channel["channel_id"])),
                        processing_msg.id
                    )
                )
                
        except Exception as e:
            error_msg = str(e)[:200]  # Truncate long error messages
            print(f"Error posting to channel {channel['channel_id']}: {error_msg}")
            failed_channels.append({
                "channel_id": channel["channel_id"],
                "channel_name": channel.get("name", str(channel["channel_id"])),
                "error": error_msg
            })

    # Save post with deletion info if needed
    post_data = {
        "post_id": post_id,
        "channels": sent_messages,
        "user_id": message.from_user.id,
        "confirmation_msg_id": processing_msg.id,
        "created_at": time.time(),
        "group": group  # Store which group this post was sent to
    }
    
    if delete_after:
        post_data["delete_after"] = time.time() + delete_after
        post_data["delete_original"] = True
    
    await db.save_post(post_data)

    result_msg = (
        f"<blockquote>📣 <b>Posting Completed!</b></blockquote>\n\n"
        f"• <b>Group:</b> {group}\n"
        f"• <b>Post ID:</b> <code>{post_id}</code>\n"
        f"• <b>Success:</b> {success_count}/{total_channels} channels\n"
    )
    
    if delete_after:
        time_str = format_time(delete_after)
        result_msg += f"• <b>Auto-delete in:</b> {time_str}\n"

    if failed_channels:
        result_msg += f"• <b>Failed:</b> {len(failed_channels)} channels\n\n"
        if len(failed_channels) <= 10:
            result_msg += "<b>Failed Channels:</b>\n"
            for idx, channel in enumerate(failed_channels, 1):
                result_msg += f"{idx}. {channel['channel_name']} - {channel['error']}\n"
        else:
            result_msg += "<i>Too many failed channels to display (see logs for details)</i>\n"

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Delete This Post", callback_data=f"delete_{post_id}")]
    ])

    await processing_msg.edit_text(result_msg, reply_markup=reply_markup)

    try:
        log_msg = (
            f"📢 <blockquote><b>#Post | Group {group} | @Interferons_bot</b></blockquote>\n\n"
            f"👤 <b>Posted By:</b> {message.from_user.mention}\n"
            f"📌 <b>Post ID:</b> <code>{post_id}</code>\n"
            f"📡 <b>Sent to:</b> {success_count}/{total_channels} channels\n"
            f"⏳ <b>Auto-delete:</b> {time_str if delete_after else 'No'}\n"
        )
        
        if failed_channels:
            log_msg += f"\n❌ <b>Failed Channels ({len(failed_channels)}):</b>\n"
            for channel in failed_channels[:15]:  # Show up to 15 in logs
                log_msg += f"  - {channel['channel_name']}: {channel['error']}\n"
            if len(failed_channels) > 15:
                log_msg += f"  ...and {len(failed_channels)-15} more"
        
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=log_msg
        )    
    except Exception as e:
        print(f"Error sending confirmation to log channel: {e}")

    if delete_after and deletion_tasks:
        asyncio.create_task(
            handle_deletion_results(
                client=client,
                deletion_tasks=deletion_tasks,
                post_id=post_id,
                delay_seconds=delete_after
            )
        )

@Client.on_message(filters.command(["fpost", "fpost0", "fpost1", "fpost2", "fpost3"]) & filters.private & admin_filter)
async def forward_post(client, message: Message):
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except:
        pass
    
    if not message.reply_to_message:
        await message.reply("**Reply to a message to forward it.**")
        return

    # Determine which group to post to (default 0)
    cmd = message.command[0]
    group = "0"  # Default group
    if len(cmd) > 5:  # For fpost1, fpost2, fpost3
        group = cmd[-1]  # Get the last character

    delete_after = None
    time_input = None
    if len(message.command) > 1:
        try:
            time_input = ' '.join(message.command[1:]).lower()
            delete_after = parse_time(time_input)
            if delete_after <= 0:
                await message.reply("❌ Time must be greater than 0")
                return
        except ValueError as e:
            await message.reply(f"❌ {str(e)}\nExample: /fpost 1h 30min or /fpost 2 hours 15 minutes")
            return

    post_content = message.reply_to_message
    channels = await db.get_channels_by_group(group)  # Get channels from specific group

    if not channels:
        await message.reply(f"**No channels connected in group {group} yet.**")
        return

    post_id = int(time.time())
    sent_messages = []
    success_count = 0
    total_channels = len(channels)
    failed_channels = []

    processing_msg = await message.reply(
        f"**📢 Forwarding to {total_channels} channels in group {group}...**",
        reply_to_message_id=post_content.id
    )

    deletion_tasks = []
    
    for channel in channels:
        try:
            sent_message = await client.forward_messages(
                chat_id=channel["channel_id"],  # Use channel_id instead of _id
                from_chat_id=message.chat.id,
                message_ids=post_content.id
            )

            sent_messages.append({
                "channel_id": channel["channel_id"],
                "message_id": sent_message.id,
                "channel_name": channel.get("name", str(channel["channel_id"]))
            })
            success_count += 1

            if delete_after:
                deletion_tasks.append(
                    schedule_deletion(
                        client,
                        channel["channel_id"],
                        sent_message.id,
                        delete_after,
                        message.from_user.id,
                        post_id,
                        channel.get("name", str(channel["channel_id"])),
                        processing_msg.id
                    )
                )
                
        except Exception as e:
            error_msg = str(e)[:200]  # Truncate long error messages
            print(f"Error forwarding to channel {channel['channel_id']}: {error_msg}")
            failed_channels.append({
                "channel_id": channel["channel_id"],
                "channel_name": channel.get("name", str(channel["channel_id"])),
                "error": error_msg
            })

    post_data = {
        "post_id": post_id,
        "channels": sent_messages,
        "user_id": message.from_user.id,
        "confirmation_msg_id": processing_msg.id,
        "created_at": time.time(),
        "is_forward": True,
        "group": group  # Store which group this post was sent to
    }
    
    if delete_after:
        post_data["delete_after"] = time.time() + delete_after
        post_data["delete_original"] = True
    
    await db.save_post(post_data)

    result_msg = (
        f"<blockquote>📣 <b>Forwarding Completed!</b></blockquote>\n\n"
        f"• <b>Group:</b> {group}\n"
        f"• <b>Post ID:</b> <code>{post_id}</code>\n"
        f"• <b>Success:</b> {success_count}/{total_channels} channels\n"
    )
    
    if delete_after:
        time_str = format_time(delete_after)
        result_msg += f"• <b>Auto-delete in:</b> {time_str}\n"

    if failed_channels:
        result_msg += f"• <b>Failed:</b> {len(failed_channels)} channels\n\n"
        if len(failed_channels) <= 10:
            result_msg += "<b>Failed Channels:</b>\n"
            for idx, channel in enumerate(failed_channels, 1):
                result_msg += f"{idx}. {channel['channel_name']} - {channel['error']}\n"
        else:
            result_msg += "<i>Too many failed channels to display (see logs for details)</i>\n"

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Delete This Post", callback_data=f"delete_{post_id}")]
    ])

    await processing_msg.edit_text(result_msg, reply_markup=reply_markup)

    try:
        log_msg = (
            f"📢 <blockquote><b>#FPost | Group {group} | @Interferons_bot</b></blockquote>\n\n"
            f"👤 <b>Forwarded By:</b> {message.from_user.mention}\n"
            f"📌 <b>Post ID:</b> <code>{post_id}</code>\n"
            f"📡 <b>Sent to:</b> {success_count}/{total_channels} channels\n"
            f"⏳ <b>Auto-delete:</b> {time_str if delete_after else 'No'}\n"
        )
        
        if failed_channels:
            log_msg += f"\n❌ <b>Failed Channels ({len(failed_channels)}):</b>\n"
            for channel in failed_channels[:15]:
                log_msg += f"  - {channel['channel_name']}: {channel['error']}\n"
            if len(failed_channels) > 15:
                log_msg += f"  ...and {len(failed_channels)-15} more"
        
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=log_msg
        )    
    except Exception as e:
        print(f"Error sending confirmation to log channel: {e}")

    if delete_after and deletion_tasks:
        asyncio.create_task(
            handle_deletion_results(
                client=client,
                deletion_tasks=deletion_tasks,
                post_id=post_id,
                delay_seconds=delete_after
            )
	    )
