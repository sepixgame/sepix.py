import sqlite3
import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ConversationHandler, ContextTypes
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)
db_path = 'telegram_users.db'

def create_tables():
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                            chat_id INTEGER PRIMARY KEY,
                            name TEXT,
                            age INTEGER,
                            gender TEXT,
                            chatting_with INTEGER,
                            owner_id INTEGER
                         )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            owner_id INTEGER,
                            sender_id INTEGER,
                            sender_name TEXT,
                            message TEXT,
                            message_type TEXT,
                            media_file_id TEXT,
                            is_read INTEGER DEFAULT 0
                         )''')
        conn.commit()

create_tables()

def load_user(chat_id):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
        user = cursor.fetchone()
        logger.debug(f"Loaded user {chat_id}: {user}")
        return user

def save_user(chat_id, name=None, age=None, gender=None, chatting_with=None, owner_id='__NO_UPDATE__'):
    user = load_user(chat_id)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        if user:
            fields = []
            values = []
            if name is not None:
                fields.append('name = ?')
                values.append(name)
            if age is not None:
                fields.append('age = ?')
                values.append(age)
            if gender is not None:
                fields.append('gender = ?')
                values.append(gender)
            if chatting_with is not None:
                fields.append('chatting_with = ?')
                values.append(chatting_with)
            if owner_id != '__NO_UPDATE__':
                fields.append('owner_id = ?')
                values.append(owner_id)
            if fields:
                query = f"UPDATE users SET {', '.join(fields)} WHERE chat_id = ?"
                values.append(chat_id)
                cursor.execute(query, values)
                logger.debug(f"Updating user {chat_id} with {fields}")
            else:
                logger.debug(f"No fields to update for user {chat_id}")
        else:
            logger.debug(f"Inserting new user {chat_id} with name={name}, age={age}, gender={gender}, chatting_with={chatting_with}, owner_id={owner_id}")
            cursor.execute('''INSERT INTO users (chat_id, name, age, gender, chatting_with, owner_id)
                              VALUES (?, ?, ?, ?, ?, ?)''', (chat_id, name, age, gender, chatting_with, None if owner_id == '__NO_UPDATE__' else owner_id))
        conn.commit()
    
    updated_user = load_user(chat_id)
    logger.debug(f"After update: {updated_user}")

def delete_chat_relation(chat_id):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET chatting_with = NULL WHERE chat_id = ?", (chat_id,))
        conn.commit()

def get_users_by_gender(chat_id, gender=None):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        if gender:
            cursor.execute("""
                SELECT chat_id, name 
                FROM users 
                WHERE gender = ? 
                AND chatting_with IS NULL 
                AND chat_id != ? 
            """, (gender, chat_id))
        else:
            cursor.execute("""
                SELECT chat_id, name 
                FROM users 
                WHERE chatting_with IS NULL 
                AND chat_id != ?
            """, (chat_id,))
        users = cursor.fetchall()
        logger.debug(f"Users found for gender '{gender}': {users}")
        return users

messages = {
    "welcome": "سلام خوش اومدی!👋 اسمت چیه؟",
    "already_registered": "قبلا ثبت نام کردی",
    "complete_registration": "فراینده ثبت نام رو کامل کن لطفا",
    "enter_age": "ممنون {name}! حالا بگو چند سالته (فقط عدد وارد کن)",
    "invalid_age": "فقط عدد وارد کن لطفا",
    "select_gender": "جنسیتت رو انتخاب کن👨👩",
    "gender_registered": "ثبت نام انجام شد برای شروع چت روی دکمه (شروع چت) کلیک کن😉",
    "no_users_available": "هیچ کاربری در دسترس نیست چند دقیقه دیگه دوباره تلاش کن🙏",
    "select_user": "کاربر مورد نظرت رو برای چت انتخاب کن",
    "request_sent": "درخواستت به کاربر ارسال شد منتظر جوابش باش",
    "chat_request": "{sender_name} میخواد باهات چت کنه قبول میکنی🤔?",
    "chat_accepted": "چت بین شما و {receiver_name} شروع شد",
    "chat_rejected": "{receiver_name} درخواست چت رو رد کرد☹️",
    "not_connected": "به هیچ کاربر متصل نیستی برای شروع چت روی دکمه (شروع چت) کلیک کن",
    "chat_ended": "چت به پایان رسید🔚",
    "exit_chat_to_continue": "برای انجام کار های دیگه اول باید از چت خارج بشی",
    "exit_chat_to_use_command": "برای اینکه از گزینه های دیگه استفاده کنی باید از چت خارج بشی",
    "info_prompt": "برای تغییر اطلاعات یکی از گزینه های زیر رو انتخاب کن",
    "link_generated": "لینکت برای اشتراک گذاری:\n{link}",
    "new_message_notification": "پیام جدید داری! برای دیدن پیام روی دکمه (پیام‌های جدید) کلیک کن",
    "you_are_not_in_chat": "الان تو چت با هیچ کسی نیستی",
    "message_sent": "پیامت ارسال شد به {owner_name}",
    "reply_prompt": "پیامت رو وارد کن تا به {receiver_name} جواب بدی",
    "reply_received": "جوابت به {sender_name} ارسال شد",
    "invalid_command": "دستور نامعتبر است."
}

NAME, AGE, GENDER, SEND_MESSAGE = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = load_user(chat_id)
    logger.info(f"/start called by user {chat_id}")

    args = context.args
    if args:
        try:
            owner_id = int(args[0])
        except ValueError:
            await update.message.reply_text("لینک اشتباهه")
            return ConversationHandler.END

        owner_user = load_user(owner_id)
        if owner_user:
            if owner_user[4]:
                await update.message.reply_text("کاربری که انتخاب کردی در حال چته")
                return ConversationHandler.END
            else:
                save_user(chat_id, owner_id=owner_id)
                logger.debug(f"User {chat_id} linked to owner_id {owner_id}")
                await update.message.reply_text(f"شما در حال پیام دادن به {owner_user[1]} هستید.\nپیامت را بنویس:")
                return SEND_MESSAGE
        else:
            await update.message.reply_text("صاحب لینک پیدا نشد")
            logger.warning(f"Owner {owner_id} not found in database.")
            return ConversationHandler.END
    else:
        if not user:
            save_user(chat_id)
            logger.debug(f"New user {chat_id} started registration")
            await update.message.reply_text(messages["welcome"])
            return NAME
        else:
            if all([user[1], user[2], user[3]]):
                bot_username = context.bot.username
                link = f"https://t.me/{bot_username}?start={chat_id}"
                await update.message.reply_text(
                    messages["already_registered"] + f"\n{messages['link_generated'].format(link=link)}",
                    reply_markup=main_keyboard(user)
                )
                return ConversationHandler.END
            else:
                await update.message.reply_text(messages["complete_registration"])
                if not user[1]:
                    return NAME
                elif not user[2]:
                    return AGE
                elif not user[3]:
                    return GENDER

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    name = update.message.text.strip()
    logger.info(f"User {chat_id} set name to {name}")
    save_user(chat_id, name=name)
    await update.message.reply_text(messages["enter_age"].format(name=name))
    return AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    age_text = update.message.text.strip()
    logger.info(f"User {chat_id} entered age: {age_text}")
    if age_text.isdigit():
        age = int(age_text)
        save_user(chat_id, age=age)
        keyboard = [
            [InlineKeyboardButton("مرد👨", callback_data='gender_male')],
            [InlineKeyboardButton("زن👩", callback_data='gender_female')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(messages["select_gender"], reply_markup=reply_markup)
        return GENDER
    else:
        await update.message.reply_text(messages["invalid_age"])
        return AGE

async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.from_user.id
    gender = query.data
    logger.info(f"User {chat_id} selected gender: {gender}")

    if gender == 'gender_male':
        save_user(chat_id, gender="مرد")
    elif gender == 'gender_female':
        save_user(chat_id, gender="زن")

    user = load_user(chat_id)
    await query.message.reply_text(
        messages["gender_registered"],
        reply_markup=main_keyboard(user)
    )
    await query.answer()
    return ConversationHandler.END

async def handle_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = load_user(chat_id)
    logger.info(f"User {chat_id} clicked 'شروع چت'")

    if not all([user[1], user[2], user[3]]):
        await update.message.reply_text(messages["complete_registration"])
        return

    if user[4]: 
        await update.message.reply_text(messages["exit_chat_to_use_command"])
        return

    keyboard = [
        [KeyboardButton("مرد👨"), KeyboardButton("زن👩"), KeyboardButton("شانسی🎲")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("یکی از گزینه‌ها رو انتخاب کن:", reply_markup=reply_markup)

async def handle_gender_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    logger.info(f"User {chat_id} selected gender choice for chat: {text}")

    if text == "مرد👨":
        users_list = get_users_by_gender(chat_id, gender="مرد")
    elif text == "زن👩":
        users_list = get_users_by_gender(chat_id, gender="زن")
    elif text == "شانسی🎲":
        users_list = get_users_by_gender(chat_id)
    else:
        await update.message.reply_text("گذینه ای که انتخاب کردی معتبر نیست")
        return

    if users_list:
        context.user_data["gender_choice"] = text
        await show_users(update, context, users_list, 0, text)
    else:
        await update.message.reply_text(messages["no_users_available"])

async def show_users(update: Update, context, users_list, page, gender_choice):
    users_per_page = 5
    total_pages = (len(users_list) + users_per_page - 1) // users_per_page

    start = page * users_per_page
    end = start + users_per_page
    users_to_show = users_list[start:end]

    keyboard = [[InlineKeyboardButton(user[1], callback_data=str(user[0]))] for user in users_to_show]

    pagination_buttons = create_pagination_buttons(page, total_pages)
    if pagination_buttons:
        keyboard.append(pagination_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(messages["select_user"], reply_markup=reply_markup)

def create_pagination_buttons(page, total_pages):
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("صفحه قبل", callback_data=f"prev_{page - 1}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("صفحه بعد", callback_data=f"next_{page + 1}"))
    return buttons

async def handle_user_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    selected_user_id = int(query.data)
    sender_id = query.from_user.id
    logger.info(f"User {sender_id} selected user {selected_user_id} for chat.")

    user = load_user(sender_id)
    if user and user[4]:
        await query.message.reply_text(messages["exit_chat_to_use_command"])
        await query.answer()
        return

    selected_user = load_user(selected_user_id)
    if selected_user:
        keyboard = [
            [InlineKeyboardButton("قبول کردن👍", callback_data=f"accept_{sender_id}")],
            [InlineKeyboardButton("رد کردن👎", callback_data=f"reject_{sender_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=selected_user_id,
            text=messages["chat_request"].format(sender_name=user[1]),
            reply_markup=reply_markup
        )
        await context.bot.send_message(
            chat_id=sender_id,
            text=messages["request_sent"]
        )

    await query.answer()

async def handle_chat_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    response_data = query.data.split('_')
    if len(response_data) != 2:
        logger.warning(f"Invalid callback data received: {query.data}")
        await query.answer("داده نامعتبر است.")
        return

    action, sender_id_str = response_data
    try:
        sender_id = int(sender_id_str)
    except ValueError:
        logger.warning(f"Invalid sender_id in callback data: {sender_id_str}")
        await query.answer("داده نامعتبر است.")
        return

    receiver_id = query.from_user.id
    logger.info(f"User {receiver_id} responded with {action} to chat request from {sender_id}.")

    sender_user = load_user(sender_id)
    receiver_user = load_user(receiver_id)

    if not sender_user or not receiver_user:
        await query.answer("کاربر یافت نشد.")
        return

    if action == 'accept':
        save_user(sender_id, chatting_with=receiver_id)
        save_user(receiver_id, chatting_with=sender_id)

        sender_name = sender_user[1]
        receiver_name = receiver_user[1]

        await context.bot.send_message(
            chat_id=sender_id,
            text=messages["chat_accepted"].format(receiver_name=receiver_name)
        )
        await context.bot.send_message(
            chat_id=receiver_id,
            text=messages["chat_accepted"].format(receiver_name=sender_name)
        )

        keyboard = [[KeyboardButton("اتمام چت")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await context.bot.send_message(
            chat_id=sender_id,
            text="برای پایان چت روی دکمه زیر کلیک کن",
            reply_markup=reply_markup
        )
        await context.bot.send_message(
            chat_id=receiver_id,
            text="برای پایان چت روی دکمه زیر کلیک کن",
            reply_markup=reply_markup
        )

    elif action == 'reject':
        sender_name = sender_user[1]
        receiver_name = receiver_user[1]
        await context.bot.send_message(
            chat_id=sender_id,
            text=f"{receiver_name} درخواست چت رو رد کرد."
        )
        await context.bot.send_message(
            chat_id=receiver_id,
            text="درخواست چت رو رد کردی."
        )

    else:
        logger.warning(f"Unknown action: {action}")

    await query.answer()

async def handle_end_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = load_user(chat_id)
    logger.info(f"User {chat_id} clicked 'اتمام چت'.")

    if user and user[4]:
        chatting_with = user[4]
        delete_chat_relation(chat_id)
        delete_chat_relation(chatting_with)

        user_after = load_user(chat_id)
        chatting_with_user = load_user(chatting_with)

        await context.bot.send_message(
            chat_id=chat_id,
            text=messages["chat_ended"],
            reply_markup=main_keyboard(user_after)
        )
        await context.bot.send_message(
            chat_id=chatting_with,
            text=messages["chat_ended"],
            reply_markup=main_keyboard(chatting_with_user)
        )

async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_chat.id
    user = load_user(sender_id)
    if user:
        owner_id = user[5] 
        chatting_with = user[4] 
        logger.debug(f"relay_message called by {sender_id}, owner_id={owner_id}, chatting_with={chatting_with}")

        if chatting_with:
            receiver_id = chatting_with
            receiver_user = load_user(receiver_id)
            if receiver_user:
                message_text = update.message.text if update.message.text else None
                media_file_id = None
                message_type = "text"

                if update.message.photo:
                    photo = update.message.photo[-1]
                    media_file_id = photo.file_id
                    message_type = "photo"
                elif update.message.video:
                    video = update.message.video
                    media_file_id = video.file_id
                    message_type = "video"

                try:
                    if message_type == "text" and message_text:
                        await context.bot.send_message(chat_id=receiver_id, text=f"{user[1]}: {message_text}")
                    elif message_type == "photo":
                        await context.bot.send_photo(chat_id=receiver_id, photo=media_file_id, caption=f"{user[1]} ارسال کرد.")
                    elif message_type == "video":
                        await context.bot.send_video(chat_id=receiver_id, video=media_file_id, caption=f"{user[1]} ارسال کرد.")
                except Exception as e:
                    logger.error(f"Error sending message from {sender_id} to {receiver_id}: {e}")

                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''INSERT INTO messages (owner_id, sender_id, sender_name, message, message_type, media_file_id)
                                      VALUES (?, ?, ?, ?, ?, ?)''',
                                   (receiver_id, sender_id, user[1], message_text, message_type, media_file_id))
                    conn.commit()

                logger.info(f"Relayed {message_type} message from {sender_id} to {receiver_id}")
            else:
                await update.message.reply_text("کاربر مورد نظر یافت نشد.")
                logger.warning(f"User {receiver_id} not found in database.")
        elif owner_id:
            owner_user = load_user(owner_id)
            if owner_user:
                message_text = update.message.text if update.message.text else None
                media_file_id = None
                message_type = "text"

                if update.message.photo:
                    photo = update.message.photo[-1]
                    media_file_id = photo.file_id
                    message_type = "photo"
                elif update.message.video:
                    video = update.message.video
                    media_file_id = video.file_id
                    message_type = "video"

                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''INSERT INTO messages (owner_id, sender_id, sender_name, message, message_type, media_file_id)
                                      VALUES (?, ?, ?, ?, ?, ?)''',
                                   (owner_id, sender_id, "کاربر ناشناس", message_text, message_type, media_file_id))
                    conn.commit()

                logger.info(f"Stored {message_type} message from {sender_id} to owner {owner_id}")

                try:
                    await context.bot.send_message(chat_id=owner_id, text=messages["new_message_notification"])
                except Exception as e:
                    logger.error(f"Error sending new message notification to owner {owner_id}: {e}")

                await update.message.reply_text(messages["message_sent"].format(owner_name=owner_user[1]))

                logger.debug(f"Setting owner_id to NULL for user {sender_id}")
                save_user(sender_id, owner_id=None)
                logger.info(f"Owner_id for user {sender_id} has been cleared after sending the first message via link.")
            else:
                await update.message.reply_text("صاحب لینک یافت نشد.")
                logger.warning(f"Owner {owner_id} not found in database.")
        else:
            await update.message.reply_text(messages["not_connected"])
    else:
        await update.message.reply_text(messages["not_connected"])

async def handle_new_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = load_user(chat_id)
    if user and not user[5]:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''SELECT sender_id, sender_name, message, message_type, media_file_id FROM messages 
                              WHERE owner_id = ? AND is_read = 0 AND sender_name = 'کاربر ناشناس' ''', (chat_id,))
            new_messages = cursor.fetchall()

            if new_messages:
                for sender_id, sender_name, message, message_type, media_file_id in new_messages:
                    keyboard = [
                        [InlineKeyboardButton("پاسخ✍️", callback_data=f"reply_{sender_id}")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    if message_type == "text":
                        await update.message.reply_text(f"ناشناس: {message}", reply_markup=reply_markup)
                    elif message_type == "photo":
                        await update.message.reply_photo(photo=media_file_id, caption="ناشناس: ارسال یک عکس", reply_markup=reply_markup)
                    elif message_type == "video":
                        await update.message.reply_video(video=media_file_id, caption="ناشناس: ارسال یک ویدیو", reply_markup=reply_markup)

                cursor.execute('''UPDATE messages SET is_read = 1 WHERE owner_id = ? AND is_read = 0 AND sender_name = 'کاربر ناشناس' ''', (chat_id,))
                conn.commit()
            else:
                await update.message.reply_text("پیام جدیدی نداری")
    else:
        await update.message.reply_text("دسترسی لازم رو نداری")

async def handle_reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data.startswith("reply_"):
        sender_id = int(data.split("_")[1])
        context.user_data['reply_to'] = sender_id
        await query.answer()
        await query.message.reply_text("جوابت رو بنویس✍️")
    else:
        await query.answer("داده نامعتبر است.")

async def receive_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'reply_to' in context.user_data:
        reply = update.message
        reply_text = reply.text if reply.text else None
        reply_photo = reply.photo[-1].file_id if reply.photo else None
        reply_video = reply.video.file_id if reply.video else None

        sender_id = context.user_data.pop('reply_to', None)
        if sender_id:
            sender_user = load_user(sender_id)
            owner_user = load_user(update.effective_chat.id)

            if sender_user and owner_user:
                try:
                    if reply_text:
                        await context.bot.send_message(
                            chat_id=sender_id,
                            text=f"پاسخ از {owner_user[1]}: {reply_text}"
                        )
                    elif reply_photo:
                        await context.bot.send_photo(
                            chat_id=sender_id,
                            photo=reply_photo,
                            caption=f"پاسخ از {owner_user[1]}"
                        )
                    elif reply_video:
                        await context.bot.send_video(
                            chat_id=sender_id,
                            video=reply_video,
                            caption=f"پاسخ از {owner_user[1]}"
                        )
                    else:
                        await update.message.reply_text("فرمت پیام پشتیبانی نمی‌شود.")
                        return

                    await update.message.reply_text(messages["reply_received"].format(sender_name=sender_user[1]))
                    logger.info(f"Owner {update.effective_chat.id} replied to {sender_id}")
                except Exception as e:
                    logger.error(f"Error sending reply from {update.effective_chat.id} to {sender_id}: {e}")
            else:
                await update.message.reply_text("کاربر مقصد یافت نشد.")
        else:
            await update.message.reply_text("داده ارسال‌کننده نامعتبر است.")
    else:
        await relay_message(update, context)

async def pagination_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split('_')
    if len(data) != 2:
        logger.warning(f"Invalid pagination callback data: {query.data}")
        await query.answer("داده نامعتبر است.")
        return

    action, page_str = data
    try:
        page = int(page_str)
    except ValueError:
        logger.warning(f"Invalid page number in callback data: {page_str}")
        await query.answer("داده نامعتبر است.")
        return

    logger.info(f"Pagination action: {action}, page: {page}")

    gender_choice = context.user_data.get("gender_choice")
    chat_id = query.from_user.id
    users_list = get_users_by_gender(
        chat_id,
        gender="مرد" if gender_choice == "مرد👨" else "زن" if gender_choice == "زن👩" else None
    )

    await show_users(update, context, users_list, page, gender_choice)
    await query.answer()

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data.startswith('prev_') or data.startswith('next_'):
        await pagination_handler(update, context)
    elif data.startswith('change_'):
        await change_user_info(update, context)
    elif data.startswith('reply_'):
        await handle_reply_button(update, context)
    else:
        logger.warning(f"Unknown callback data: {data}")
        await query.answer("داده نامعتبر است.")

async def change_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    info_type = query.data.split('_')[1]
    context.user_data['awaiting_info'] = info_type
    logger.info(f"User {query.from_user.id} is changing {info_type}")

    await query.answer()
    if info_type == 'name':
        await query.edit_message_text("اسم جدیدت رو وارد کن:")
    elif info_type == 'age':
        await query.edit_message_text("سن جدیدت رو وارد کن:")
    elif info_type == 'gender':
        keyboard = [
            [InlineKeyboardButton("مرد👨", callback_data='gender_male')],
            [InlineKeyboardButton("زن👩", callback_data='gender_female')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("جنسیت جدیدت رو انتخاب کن:", reply_markup=reply_markup)

async def process_user_info_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    info_type = context.user_data.pop('awaiting_info', None)
    logger.info(f"User {chat_id} is updating {info_type} with {text}")

    if info_type:
        if info_type == 'name':
            save_user(chat_id, name=text)
            user = load_user(chat_id)
            await update.message.reply_text("اسمت عوض شد!", reply_markup=main_keyboard(user))
        elif info_type == 'age':
            if text.isdigit():
                save_user(chat_id, age=int(text))
                user = load_user(chat_id)
                await update.message.reply_text("سنت عوض شد!", reply_markup=main_keyboard(user))
            else:
                await update.message.reply_text("لطفاً یک عدد معتبر وارد کنید.")
                context.user_data['awaiting_info'] = 'age'
                return
        elif info_type == 'gender':
            if text in ['مرد👨', 'زن👩']:
                gender = "مرد" if text == 'مرد👨' else "زن"
                save_user(chat_id, gender=gender)
                user = load_user(chat_id)
                await update.message.reply_text("جنسیتت عوض شد!", reply_markup=main_keyboard(user))
            else:
                await update.message.reply_text("یکی از گزینه‌های (مرد👨) و (زن👩) رو انتخاب کن")
                context.user_data['awaiting_info'] = 'gender'
                return
    else:
        await relay_message(update, context)

async def debug_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = load_user(chat_id)
    if user:
        info = (
            f"شناسه چت: {user[0]}\n"
            f"نام: {user[1]}\n"
            f"سن: {user[2]}\n"
            f"جنسیت: {user[3]}\n"
            f"در حال چت با: {user[4]}\n"
            f"owner_id: {user[5]}"
        )
        await update.message.reply_text(info)
    else:
        await update.message.reply_text("هنوز ثبت نام نکردی")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = 1877238598
    if update.effective_chat.id != admin_id:
        await update.message.reply_text("دسترسی ندارید.")
        return

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()

    if users:
        message = "لیست کاربران:\n"
        for user in users:
            message += (
                f"Chat ID: {user[0]}, "
                f"Name: {user[1]}, "
                f"Age: {user[2]}, "
                f"Gender: {user[3]}, "
                f"Chatting With: {user[4]}, "
                f"Owner ID: {user[5]}\n"
            )
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("هیچ کاربری ثبت‌نام نکرده است.")

async def add_test_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = 1877238598 
    if update.effective_chat.id != admin_id:
        await update.message.reply_text("دسترسی ندارید.")
        return

    args = context.args
    if len(args) != 3:
        await update.message.reply_text("استفاده صحیح: /add_test_user <chat_id> <name> <gender>\nمثال: /add_test_user 1234567890 Ali مرد")
        return

    try:
        test_chat_id = int(args[0])
    except ValueError:
        await update.message.reply_text("شناسه چت باید یک عدد باشد.")
        return

    name = args[1]
    gender = args[2]
    if gender not in ["مرد", "زن"]:
        await update.message.reply_text("جنسیت باید 'مرد' یا 'زن' باشد.")
        return

    existing_user = load_user(test_chat_id)
    if existing_user:
        await update.message.reply_text("کاربر با این chat_id قبلاً ثبت‌نام کرده است.")
        return

    save_user(test_chat_id, name=name, gender=gender)
    await update.message.reply_text(f"کاربر تستی {name} با chat_id {test_chat_id} اضافه شد.")

async def show_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = load_user(chat_id)
    logger.info(f"User {chat_id} requested info.")

    if user:
        bot_username = context.bot.username
        unique_link = f"https://t.me/{bot_username}?start={chat_id}"

        user_info = (
            f"نام: {user[1]}\n"
            f"سن: {user[2]}\n"
            f"جنسیت: {user[3]}\n"
            f"لینک شما برای اشتراک گذاری: <a href='{unique_link}'>لینک</a>"
        )

        keyboard = [
            [InlineKeyboardButton("تغییر نام", callback_data='change_name')],
            [InlineKeyboardButton("تغییر سن", callback_data='change_age')],
            [InlineKeyboardButton("تغییر جنسیت", callback_data='change_gender')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"اطلاعات شما:\n{user_info}",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text("شما هنوز ثبت‌نام نکرده‌اید.")

async def unified_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def main_keyboard(user):
    keyboard = [
        [KeyboardButton("شروع چت")],
        [KeyboardButton("اطلاعات شما")]
    ]

    logger.debug(f"User data: chat_id={user[0]}, owner_id={user[5]}")

    if not user[5]:
        keyboard.append([KeyboardButton("پیام‌های جدید")])
        logger.info(f"Added 'پیام‌های جدید' button for user {user[0]}")

    if user[4]:
        keyboard.append([KeyboardButton("اتمام چت")])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def send_message_via_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_chat.id
    user = load_user(sender_id)
    if user and user[5]:
        owner_id = user[5]
        owner_user = load_user(owner_id)
        if owner_user:
            message_text = update.message.text if update.message.text else None
            media_file_id = None
            message_type = "text"

            if update.message.photo:
                photo = update.message.photo[-1]
                media_file_id = photo.file_id
                message_type = "photo"
            elif update.message.video:
                video = update.message.video
                media_file_id = video.file_id
                message_type = "video"

            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''INSERT INTO messages (owner_id, sender_id, sender_name, message, message_type, media_file_id)
                                  VALUES (?, ?, ?, ?, ?, ?)''',
                               (owner_id, sender_id, "کاربر ناشناس", message_text, message_type, media_file_id))
                conn.commit()

            logger.info(f"Stored {message_type} message from {sender_id} to owner {owner_id}")

            try:
                await context.bot.send_message(chat_id=owner_id, text=messages["new_message_notification"])
            except Exception as e:
                logger.error(f"Error sending new message notification to owner {owner_id}: {e}")

            await update.message.reply_text(messages["message_sent"].format(owner_name=owner_user[1]))

            logger.debug(f"Setting owner_id to NULL for user {sender_id}")
            save_user(sender_id, owner_id=None)
            logger.info(f"Owner_id for user {sender_id} has been cleared after sending the first message via link.")

            return ConversationHandler.END
        else:
            await update.message.reply_text("صاحب لینک یافت نشد.")
            logger.warning(f"Owner {owner_id} not found in database.")
            return ConversationHandler.END
    else:
        await update.message.reply_text("دسترسی لازم رو نداری.")
        return ConversationHandler.END

if __name__ == '__main__':
    BOT_TOKEN = ""

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            GENDER: [CallbackQueryHandler(set_gender, pattern="^gender_")],
            SEND_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, send_message_via_link)]
        },
        fallbacks=[]
    )

    application.add_handler(conv_handler)

    application.add_handler(MessageHandler(filters.Regex("^شروع چت$"), handle_connect))
    application.add_handler(MessageHandler(filters.Regex("^(مرد👨|زن👩|شانسی🎲)$"), handle_gender_choice))
    application.add_handler(MessageHandler(filters.Regex("^اتمام چت$"), handle_end_chat))
    application.add_handler(MessageHandler(filters.Regex("^اطلاعات شما$"), show_user_info))
    application.add_handler(MessageHandler(filters.Regex("^پیام‌های جدید$"), handle_new_messages))
    application.add_handler(CallbackQueryHandler(handle_user_selection, pattern=r"^\d+$"))
    application.add_handler(CallbackQueryHandler(handle_chat_response, pattern=r'^(accept|reject)_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern='^(change_(name|age|gender)|prev_\d+|next_\d+|reply_\d+)$'))

    async def unified_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if 'reply_to' in context.user_data:
            await receive_reply(update, context)
        elif 'awaiting_info' in context.user_data:
            await process_user_info_change(update, context)
        else:
            await relay_message(update, context)

    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, unified_text_handler))
    application.add_handler(CommandHandler("info", show_user_info))
    application.add_handler(CommandHandler("debug_info", debug_info))
    application.add_handler(CommandHandler("list_users", list_users))
    application.add_handler(CommandHandler("add_test_user", add_test_user))

    application.add_error_handler(unified_error_handler)

    logger.info("Bot is starting...")
    application.run_polling()
