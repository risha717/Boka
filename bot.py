# ✅ CORRECT IMPORTS:
import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode, ChatAction, ChatMemberStatus
from telegram.error import BadRequest, Forbidden
# ... rest of your code ...
import config
from database import db
from utils import (
    generate_video_id, detect_category, extract_episode_info,
    format_file_size, format_duration, generate_sheet_code,
    generate_batch_sheet_codes, escape_markdown, format_time_ago,
    get_category_emoji, get_database_name, rate_limiter, get_greeting
)

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== HELPER FUNCTIONS ====================

async def is_user_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is member of all force sub channels"""
    for channel_id in config.FORCE_SUB_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel_id, user_id)
            if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                return False
        except Exception as e:
            logger.error(f"Error checking membership for channel {channel_id}: {e}")
            continue
    return True

def get_database_channel(category):
    """Get appropriate database channel for category"""
    return config.DATABASE_CHANNELS.get(category, config.DB_CHANNEL_MOVIE)

async def send_typing_action(chat_id, context):
    """Send typing action"""
    try:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        await asyncio.sleep(0.5)
    except:
        pass

# ==================== START COMMAND ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        # Add user to database
        db.add_user(user.id, user.username, user.first_name)
        
        # Check if it's a deep link (video request)
        if context.args:
            video_id = context.args[0]
            await handle_video_request(update, context, video_id)
            return
        
        # Send welcome message
        greeting = get_greeting()
        welcome_text = config.WELCOME_MSG.format(
            name=user.first_name,
            user_id=user.id
        )
        
        keyboard = [
            [InlineKeyboardButton(config.BTN_LABELS['mini_app'], url=config.MINI_APP_URL)],
            [
                InlineKeyboardButton(config.BTN_LABELS['main_channel'], url=config.MAIN_CHANNEL_LINK),
                InlineKeyboardButton(config.BTN_LABELS['backup_channel'], url=config.BACKUP_CHANNEL_LINK)
            ],
            [InlineKeyboardButton(config.BTN_LABELS['help'], callback_data='help')]
        ]
        
        # Add admin button for admin
        if str(user.id) == str(config.ADMIN_ID):
            keyboard.append([InlineKeyboardButton(config.BTN_LABELS['admin_panel'], callback_data='admin_panel')])
        
        # Send welcome message
        if update.message:
            await update.message.reply_text(
                f"{greeting}\n\n{welcome_text}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{greeting}\n\n{welcome_text}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            
        logger.info(f"✅ User started bot: {user.id} ({user.first_name})")
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")

# ==================== VIDEO REQUEST HANDLER ====================

async def handle_video_request(update: Update, context: ContextTypes.DEFAULT_TYPE, video_id: str):
    """Handle video request from mini app"""
    try:
        user = update.effective_user
        chat_id = update.effective_chat.id
        query = update.callback_query
        
        await send_typing_action(chat_id, context)
        
        # Check if user is banned
        user_data = db.get_user(user.id)
        if user_data and user_data.get('is_banned'):
            await context.bot.send_message(
                chat_id,
                "❌ **You are banned from using this bot!**\n\nContact admin for more info.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Rate limiting
        if not rate_limiter.is_allowed(user.id):
            msg = "⚠️ **Too many requests!**\n\nPlease wait a minute and try again."
            if query:
                await query.answer(msg, show_alert=True)
            else:
                await context.bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
            return
        
        # Check force join
        if not await is_user_member(user.id, context):
            keyboard = [
                [InlineKeyboardButton("📢 Main Channel", url=config.MAIN_CHANNEL_LINK)],
                [InlineKeyboardButton("💾 Backup Channel", url=config.BACKUP_CHANNEL_LINK)],
                [InlineKeyboardButton(config.BTN_LABELS['joined'], callback_data=f'check_{video_id}')]
            ]
            
            if query:
                await query.edit_message_text(
                    config.FORCE_JOIN_MSG,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await context.bot.send_message(
                    chat_id,
                    config.FORCE_JOIN_MSG,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
            return
        
        # Get video from database
        video = db.get_video(video_id)
        
        if not video:
            msg = "❌ **Video not found!**\n\nThis video may have been removed."
            if query:
                await query.answer(msg, show_alert=True)
            else:
                await context.bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
            return
        
        # Get database channel
        db_channel = get_database_channel(video.get('category', 'movie'))
        
        # Send video
        try:
            # Send "sending..." message
            status_msg = await context.bot.send_message(
                chat_id,
                "📤 **Sending video...**\n\nPlease wait...",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Copy video from database channel
            sent_msg = await context.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=db_channel,
                message_id=video['message_id'],
                caption=f"🎬 **{video.get('title', 'Video')}**\n\n"
                       f"{get_category_emoji(video.get('category', 'other'))} Category: {video.get('category', 'Unknown').title()}\n"
                       f"📊 Size: {format_file_size(video.get('file_size', 0))}\n"
                       f"⏱️ Duration: {format_duration(video.get('duration', 0))}\n\n"
                       f"✨ Enjoy your content!\n\n"
                       f"📱 More: {config.MINI_APP_URL}",
                parse_mode=ParseMode.MARKDOWN,
                protect_content=True  # Prevent forwarding
            )
            
            # Delete status message
            await status_msg.delete()
            
            # Send success message with buttons
            keyboard = [
                [InlineKeyboardButton("📱 Open Mini App", url=config.MINI_APP_URL)],
                [InlineKeyboardButton("📢 Share with Friends", url=f"https://t.me/share/url?url={config.MINI_APP_URL}")]
            ]
            
            await context.bot.send_message(
                chat_id,
                config.VIDEO_SENT_MSG.format(
                    mini_app=config.MINI_APP_URL,
                    main_channel=config.MAIN_CHANNEL_LINK
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Update analytics
            db.increment_view(video_id)
            db.update_user_activity(user.id)
            db.log_video_request(user.id, video_id, 'view')
            
            if query:
                await query.answer("✅ Video sent!", show_alert=False)
            
            logger.info(f"✅ Video sent to {user.id}: {video_id}")
            
        except Forbidden:
            logger.error(f"User {user.id} blocked the bot")
            if query:
                await query.answer("❌ Please unblock the bot first!", show_alert=True)
        
        except Exception as e:
            logger.error(f"Error sending video: {e}")
            
            error_msg = "❌ **Error sending video!**\n\nPlease try again later or contact admin."
            
            try:
                await status_msg.delete()
            except:
                pass
            
            if query:
                await query.answer(error_msg, show_alert=True)
            else:
                await context.bot.send_message(chat_id, error_msg, parse_mode=ParseMode.MARKDOWN)
                
    except Exception as e:
        logger.error(f"Error in handle_video_request: {e}")

# ==================== SAVE VIDEOS FROM DATABASE CHANNELS ====================

async def save_channel_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save videos from database channels"""
    try:
        message = update.channel_post
        
        if not message:
            return
        
        # Check if it's from any database channel
        channel_id = message.chat.id
        
        category = None
        for cat, db_id in config.DATABASE_CHANNELS.items():
            if channel_id == db_id:
                category = cat
                break
        
        if not category:
            return
        
        # Only process videos and documents
        if not (message.video or message.document):
            return
        
        # Extract video information
        if message.video:
            file_size = message.video.file_size
            duration = message.video.duration
            file_name = message.video.file_name or "video.mp4"
        else:
            file_size = message.document.file_size
            duration = 0
            file_name = message.document.file_name or "document"
        
        # Extract title
        title = message.caption if message.caption else file_name
        title = title.split('\n')[0].strip()[:200]
        
        # Auto-detect category if not set
        detected_category = detect_category(title)
        if detected_category and detected_category != 'other':
            category = detected_category
        
        # Extract episode info for series
        season, episode = extract_episode_info(title)
        
        # Generate video ID
        video_id = generate_video_id(message.message_id, category)
        
        # Prepare video data
        video_data = {
            'video_id': video_id,
            'message_id': message.message_id,
            'title': title,
            'category': category,
            'database': category,
            'file_size': file_size,
            'duration': duration,
            'file_name': file_name,
            'added_by': config.ADMIN_ID
        }
        
        if season and episode:
            video_data['season'] = season
            video_data['episode'] = episode
        
        # Save to database
        db.add_video(video_data)
        
        # Generate sheet code
        sheet_code = generate_sheet_code(video_data)
        
        # Send notification to admin
        admin_msg = config.VIDEO_SAVED_MSG.format(
            title=escape_markdown(title),
            video_id=video_id,
            category=category.title(),
            database=get_database_name(category),
            size=format_file_size(file_size),
            sheet_code=sheet_code
        )
        
        keyboard = [
            [
                InlineKeyboardButton("📋 Copy Code", callback_data=f'copy_{video_id}'),
                InlineKeyboardButton("✏️ Edit", callback_data=f'edit_{video_id}')
            ],
            [
                InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{video_id}'),
                InlineKeyboardButton("👁️ View Details", callback_data=f'details_{video_id}')
            ]
        ]
        
        await context.bot.send_message(
            config.ADMIN_ID,
            admin_msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        logger.info(f"✅ Video saved: {video_id} ({category})")
        
    except Exception as e:
        logger.error(f"Error saving video: {e}")
        
        try:
            await context.bot.send_message(
                config.ADMIN_ID,
                f"❌ **Error saving video!**\n\n```\n{str(e)}\n```",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass

# ==================== HELP COMMAND ====================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    try:
        chat_id = update.effective_chat.id
        keyboard = [
            [InlineKeyboardButton("📱 Open Mini App", url=config.MINI_APP_URL)],
            [InlineKeyboardButton("📢 Join Main Channel", url=config.MAIN_CHANNEL_LINK)],
            [InlineKeyboardButton("🔙 Back to Start", callback_data='back_to_start')]
        ]
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                config.HELP_MSG,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=config.HELP_MSG,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Error in help command: {e}")

# ==================== ADMIN PANEL ====================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel"""
    try:
        query = update.callback_query
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        if str(user.id) != str(config.ADMIN_ID):
            if query:
                await query.answer("❌ Admin only!", show_alert=True)
            return
        
        # Get statistics
        stats = db.get_stats()
        
        panel_msg = config.ADMIN_PANEL_MSG.format(
            users=stats.get('total_users', 0),
            videos=stats.get('total_videos', 0),
            adult=stats.get('adult_videos', 0),
            movies=stats.get('movie_videos', 0),
            series=stats.get('series_videos', 0),
            new_users=stats.get('new_users_today', 0),
            new_videos=stats.get('new_videos_today', 0),
            time=datetime.now().strftime("%I:%M %p")
        )
        
        keyboard = [
            [
                InlineKeyboardButton(config.BTN_LABELS['manage_videos'], callback_data='manage_videos'),
                InlineKeyboardButton(config.BTN_LABELS['statistics'], callback_data='full_stats')
            ],
            [
                InlineKeyboardButton(config.BTN_LABELS['broadcast'], callback_data='broadcast'),
                InlineKeyboardButton(config.BTN_LABELS['settings'], callback_data='admin_settings')
            ],
            [
                InlineKeyboardButton("🔍 Search Videos", callback_data='search_videos'),
                InlineKeyboardButton("📊 Popular Videos", callback_data='popular_videos')
            ],
            [InlineKeyboardButton(config.BTN_LABELS['refresh'], callback_data='admin_panel')],
            [InlineKeyboardButton(config.BTN_LABELS['back'], callback_data='back_to_start')]
        ]
        
        if query:
            await query.answer()
            await query.edit_message_text(
                panel_msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=panel_msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Error in admin_panel: {e}")

# ==================== MANAGE VIDEOS ====================

async def manage_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage videos interface"""
    try:
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [
                InlineKeyboardButton("🔞 Adult Videos", callback_data='list_adult'),
                InlineKeyboardButton("🎬 Movies", callback_data='list_movie')
            ],
            [
                InlineKeyboardButton("📺 Series", callback_data='list_series'),
                InlineKeyboardButton("📹 All Videos", callback_data='list_all')
            ],
            [
                InlineKeyboardButton("🔍 Search", callback_data='search_videos'),
                InlineKeyboardButton("📊 Analytics", callback_data='video_analytics')
            ],
            [InlineKeyboardButton(config.BTN_LABELS['back'], callback_data='admin_panel')]
        ]
        
        stats = db.get_stats()
        msg = (
            f"📹 **VIDEO MANAGEMENT**\n\n"
            f"🔞 Adult: {stats.get('adult_videos', 0)}\n"
            f"🎬 Movies: {stats.get('movie_videos', 0)}\n"
            f"📺 Series: {stats.get('series_videos', 0)}\n"
            f"📊 Total: {stats.get('total_videos', 0)}\n\n"
            f"Select category to view videos:"
        )
        
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error in manage_videos: {e}")

# ==================== LIST VIDEOS BY CATEGORY ====================

async def list_videos_by_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category=None):
    """List videos by category"""
    try:
        query = update.callback_query
        await query.answer()
        
        videos = db.get_all_videos(category, limit=10)
        
        if not videos:
            await query.edit_message_text(
                f"📹 No videos found in {category or 'all'} category!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(config.BTN_LABELS['back'], callback_data='manage_videos')]
                ]),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        msg = f"📹 **{category.upper() if category else 'ALL'} VIDEOS** (Latest 10)\n\n"
        
        keyboard = []
        for video in videos:
            emoji = get_category_emoji(video.get('category', 'other'))
            title = video.get('title', 'Untitled')[:40]
            
            msg += f"{emoji} {escape_markdown(title)}\n"
            msg += f"   🆔 `{video['video_id']}`\n"
            msg += f"   👁️ {video.get('views', 0)} views\n\n"
            
            keyboard.append([
                InlineKeyboardButton(f"✏️ {title[:30]}", callback_data=f"edit_{video['video_id']}"),
                InlineKeyboardButton("🗑️", callback_data=f"delete_{video['video_id']}")
            ])
        
        keyboard.append([InlineKeyboardButton(config.BTN_LABELS['back'], callback_data='manage_videos')])
        
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error in list_videos_by_category: {e}")

# ==================== BROADCAST ====================

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start broadcast process"""
    try:
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "📢 **BROADCAST MESSAGE**\n\n"
            "Send me the message you want to broadcast to all users.\n\n"
            "**Tips:**\n"
            "• You can send text, photo, video\n"
            "• Use markdown for formatting\n"
            "• Send /cancel to cancel\n\n"
            "⚠️ Be careful! This will send to ALL users.",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        context.user_data['awaiting'] = 'broadcast'
    except Exception as e:
        logger.error(f"Error in start_broadcast: {e}")

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast message"""
    try:
        users = db.get_all_users()
        total = len(users)
        
        progress_msg = await update.message.reply_text(
            f"📡 **Broadcasting...**\n\n"
            f"Total Users: {total}\n"
            f"Progress: 0/{total}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        success = 0
        failed = 0
        
        for i, user in enumerate(users, 1):
            try:
                if update.message.text:
                    await context.bot.send_message(
                        user['user_id'],
                        update.message.text,
                        parse_mode=ParseMode.MARKDOWN
                    )
                elif update.message.photo:
                    await context.bot.send_photo(
                        user['user_id'],
                        update.message.photo[-1].file_id,
                        caption=update.message.caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                elif update.message.video:
                    await context.bot.send_video(
                        user['user_id'],
                        update.message.video.file_id,
                        caption=update.message.caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                success += 1
                await asyncio.sleep(0.1)  # Rate limiting
                
            except Forbidden:
                failed += 1
            except Exception as e:
                logger.error(f"Broadcast error for user {user['user_id']}: {e}")
                failed += 1
            
            # Update progress every 10 users
            if i % 10 == 0 or i == total:
                try:
                    await progress_msg.edit_text(
                        f"📡 **Broadcasting...**\n\n"
                        f"Total: {total}\n"
                        f"✅ Success: {success}\n"
                        f"❌ Failed: {failed}\n"
                        f"📊 Progress: {i}/{total}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass
        
        await progress_msg.edit_text(
            f"✅ **Broadcast Complete!**\n\n"
            f"📊 Total Users: {total}\n"
            f"✅ Sent: {success}\n"
            f"❌ Failed: {failed}\n\n"
            f"Success Rate: {(success/total*100):.1f}%" if total > 0 else "No users",
            parse_mode=ParseMode.MARKDOWN
        )
        
        context.user_data.clear()
    except Exception as e:
        logger.error(f"Error in handle_broadcast: {e}")

# ==================== STATISTICS ====================

async def show_full_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed statistics"""
    try:
        query = update.callback_query
        await query.answer()
        
        stats = db.get_stats()
        popular = db.get_popular_videos(days=7, limit=5)
        
        msg = (
            f"📊 **DETAILED STATISTICS**\n\n"
            f"**Users:**\n"
            f"👥 Total: {stats.get('total_users', 0)}\n"
            f"➕ Today: {stats.get('new_users_today', 0)}\n\n"
            f"**Videos:**\n"
            f"🎬 Total: {stats.get('total_videos', 0)}\n"
            f"🔞 Adult: {stats.get('adult_videos', 0)}\n"
            f"🎬 Movies: {stats.get('movie_videos', 0)}\n"
            f"📺 Series: {stats.get('series_videos', 0)}\n"
            f"➕ Added Today: {stats.get('new_videos_today', 0)}\n\n"
            f"**Top 5 Popular (Last 7 Days):**\n"
        )
        
        for i, video in enumerate(popular, 1):
            emoji = get_category_emoji(video.get('category'))
            msg += f"{i}. {emoji} {escape_markdown(video.get('title', 'Unknown')[:30])}\n"
            msg += f"   👁️ {video.get('request_count', 0)} requests\n"
        
        if not popular:
            msg += "No data available\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data='full_stats')],
            [InlineKeyboardButton(config.BTN_LABELS['back'], callback_data='admin_panel')]
        ]
        
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error in show_full_stats: {e}")

# ==================== CALLBACK QUERY HANDLER ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button callbacks"""
    try:
        query = update.callback_query
        data = query.data
        
        # Admin panel
        if data == 'admin_panel':
            await admin_panel(update, context)
        
        # Help
        elif data == 'help':
            await help_command(update, context)
        
        # Back to start
        elif data == 'back_to_start':
            await query.answer()
            await start(update, context)
        
        # Video request check
        elif data.startswith('check_'):
            video_id = data.split('_', 1)[1]
            await handle_video_request(update, context, video_id)
        
        # Manage videos
        elif data == 'manage_videos':
            await manage_videos(update, context)
        
        # List videos by category
        elif data == 'list_adult':
            await list_videos_by_category(update, context, 'adult')
        elif data == 'list_movie':
            await list_videos_by_category(update, context, 'movie')
        elif data == 'list_series':
            await list_videos_by_category(update, context, 'series')
        elif data == 'list_all':
            await list_videos_by_category(update, context, None)
        
        # Broadcast
        elif data == 'broadcast':
            await start_broadcast(update, context)
        
        # Statistics
        elif data == 'full_stats':
            await show_full_stats(update, context)
        
        # Copy video code
        elif data.startswith('copy_'):
            video_id = data.split('_', 1)[1]
            video = db.get_video(video_id)
            if video:
                code = generate_sheet_code(video)
                await query.answer(f"Code: {code}\n\n✅ Copy this!", show_alert=True)
        
        # Delete video
        elif data.startswith('delete_'):
            video_id = data.split('_', 1)[1]
            if db.delete_video(video_id):
                await query.answer("✅ Video deleted!", show_alert=True)
                await manage_videos(update, context)
            else:
                await query.answer("❌ Failed to delete!", show_alert=True)
        
        # Handle other callbacks
        else:
            await query.answer("⚠️ Action not implemented yet", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error in button_callback: {e}")
        try:
            await query.answer("❌ An error occurred!", show_alert=True)
        except:
            pass

# ==================== MESSAGE HANDLER ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    try:
        user_id = update.effective_user.id
        
        # Only admin
        if str(user_id) != str(config.ADMIN_ID):
            return
        
        awaiting = context.user_data.get('awaiting')
        
        # Cancel
        if update.message.text == '/cancel':
            context.user_data.clear()
            await update.message.reply_text("❌ Cancelled")
            return
        
        # Broadcast
        if awaiting == 'broadcast':
            await handle_broadcast(update, context)
    except Exception as e:
        logger.error(f"Error in handle_message: {e}")

# ==================== ERROR HANDLER ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    
    # Log error to admin
    try:
        error_msg = f"❌ **Bot Error**\n\n```\n{context.error}\n```"
        await context.bot.send_message(
            config.ADMIN_ID,
            error_msg,
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass

# ==================== MAIN FUNCTION ====================

def main():
    """Start the bot"""
    try:
        logger.info("🤖 Starting Cineflix Premium Bot...")
        
        # Create application
        application = Application.builder().token(config.BOT_TOKEN).build()
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Channel post handler for database channels
        application.add_handler(MessageHandler(filters.ChatType.CHANNEL, save_channel_video))
        
        # Start bot
        logger.info("✅ Bot started successfully!")
        logger.info(f"👤 Admin ID: {config.ADMIN_ID}")
        logger.info(f"💾 Database Channels: {len(config.DATABASE_CHANNELS)}")
        logger.info(f"📢 Force Join Channels: {len(config.FORCE_SUB_CHANNELS)}")
        
        # Run bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")

if __name__ == '__main__':
    main()
