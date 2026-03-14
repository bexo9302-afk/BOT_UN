import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
import os
import psycopg2
from psycopg2.extras import Json
from datetime import datetime
from flask import Flask
import threading
import json
import random

# التوكن من متغيرات البيئة
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
DATABASE_URL = os.environ.get('DATABASE_URL')  # رابط قاعدة البيانات من Railway

# تهيئة البوت
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ==================== قاعدة البيانات ====================

def get_db_connection():
    """الاتصال بقاعدة البيانات"""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_database():
    """تهيئة جداول قاعدة البيانات"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # جدول المواد
    cur.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id SERIAL PRIMARY KEY,
            subject_key VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL
        )
    ''')
    
    # جدول الملفات
    cur.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id SERIAL PRIMARY KEY,
            subject_key VARCHAR(50) NOT NULL,
            file_type VARCHAR(20) NOT NULL,
            file_name TEXT NOT NULL,
            file_id TEXT NOT NULL,
            caption TEXT,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_key) REFERENCES subjects(subject_key)
        )
    ''')
    
    # جدول الجدول الدراسي
    cur.execute('''
        CREATE TABLE IF NOT EXISTS schedule (
            id SERIAL PRIMARY KEY,
            file_id TEXT NOT NULL,
            update_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # جدول العشوائيات (الملفات المتنوعة)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS random_files (
            id SERIAL PRIMARY KEY,
            subject_key VARCHAR(50) NOT NULL,
            file_name TEXT NOT NULL,
            file_id TEXT NOT NULL,
            caption TEXT,
            file_type VARCHAR(50),
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_key) REFERENCES subjects(subject_key)
        )
    ''')
    
    # جدول مؤقت لتخزين الملفات قبل الحفظ (لخاصية تغيير الاسم)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS temp_files (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            file_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            subject_key VARCHAR(50),
            file_type VARCHAR(20),
            caption TEXT,
            is_random BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # إضافة المواد الأساسية
    subjects = [
        ('prog2', '💻 Computer Programming II'),
        ('business', '📊 Computer Applications in Business'),
        ('fundamentals', '🖥️ Computer Fundamentals'),
        ('discrete', '🔢 Discrete Structures'),
        ('arabic', '📖 Arabic Language')
    ]
    
    for key, name in subjects:
        cur.execute('''
            INSERT INTO subjects (subject_key, name) 
            VALUES (%s, %s) 
            ON CONFLICT (subject_key) DO NOTHING
        ''', (key, name))
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ تم تهيئة قاعدة البيانات")

# تهيئة قاعدة البيانات عند التشغيل
init_database()

# ==================== دوال قاعدة البيانات ====================

def save_temp_file(chat_id, file_id, file_name, subject_key, file_type, caption="", is_random=False):
    """حفظ ملف مؤقت قبل تغيير الاسم"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # حذف أي ملفات مؤقتة سابقة لنفس المحادثة
        cur.execute('DELETE FROM temp_files WHERE chat_id = %s', (chat_id,))
        
        cur.execute('''
            INSERT INTO temp_files (chat_id, file_id, file_name, subject_key, file_type, caption, is_random)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (chat_id, file_id, file_name, subject_key, file_type, caption, is_random))
        
        conn.commit()
        print(f"✅ تم حفظ الملف المؤقت: {file_name}")
        return True
    except Exception as e:
        print(f"❌ خطأ في حفظ الملف المؤقت: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

def get_temp_file(chat_id):
    """جلب الملف المؤقت لمحادثة معينة"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT file_id, file_name, subject_key, file_type, caption, is_random
        FROM temp_files 
        WHERE chat_id = %s
        ORDER BY created_at DESC 
        LIMIT 1
    ''', (chat_id,))
    
    result = cur.fetchone()
    
    cur.close()
    conn.close()
    
    if result:
        return {
            'file_id': result[0],
            'file_name': result[1],
            'subject_key': result[2],
            'file_type': result[3],
            'caption': result[4] or '',
            'is_random': result[5]
        }
    return None

def delete_temp_file(chat_id):
    """حذف الملف المؤقت"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('DELETE FROM temp_files WHERE chat_id = %s', (chat_id,))
    conn.commit()
    
    cur.close()
    conn.close()

def save_file(subject_key, file_type, file_name, file_id, caption=""):
    """حفظ ملف في قاعدة البيانات"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('''
            INSERT INTO files (subject_key, file_type, file_name, file_id, caption)
            VALUES (%s, %s, %s, %s, %s)
        ''', (subject_key, file_type, file_name, file_id, caption))
        
        conn.commit()
        print(f"✅ تم حفظ الملف: {file_name}")
        return True
    except Exception as e:
        print(f"❌ خطأ في حفظ الملف: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

def save_random_file(subject_key, file_name, file_id, caption="", file_type=""):
    """حفظ ملف عشوائي في قاعدة البيانات"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('''
            INSERT INTO random_files (subject_key, file_name, file_id, caption, file_type)
            VALUES (%s, %s, %s, %s, %s)
        ''', (subject_key, file_name, file_id, caption, file_type))
        
        conn.commit()
        print(f"✅ تم حفظ الملف العشوائي: {file_name}")
        return True
    except Exception as e:
        print(f"❌ خطأ في حفظ الملف العشوائي: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

def save_schedule(file_id):
    """حفظ الجدول الدراسي"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # حذف الجدول القديم
        cur.execute('DELETE FROM schedule')
        # إضافة الجدول الجديد
        cur.execute('INSERT INTO schedule (file_id) VALUES (%s)', (file_id,))
        
        conn.commit()
        print("✅ تم حفظ الجدول")
        return True
    except Exception as e:
        print(f"❌ خطأ في حفظ الجدول: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

def get_files(subject_key=None, file_type=None):
    """جلب الملفات من قاعدة البيانات"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = "SELECT file_name, file_id, caption, upload_date FROM files"
    params = []
    
    if subject_key and file_type:
        query += " WHERE subject_key = %s AND file_type = %s"
        params = [subject_key, file_type]
    elif subject_key:
        query += " WHERE subject_key = %s"
        params = [subject_key]
    elif file_type:
        query += " WHERE file_type = %s"
        params = [file_type]
    
    query += " ORDER BY upload_date DESC"
    
    cur.execute(query, params)
    files = cur.fetchall()
    
    cur.close()
    conn.close()
    
    # تحويل النتائج إلى قاموس
    result = {}
    for file_name, file_id, caption, upload_date in files:
        result[file_name] = {
            'file_id': file_id,
            'caption': caption or '',
            'date': upload_date.strftime('%Y-%m-%d %H:%M') if upload_date else ''
        }
    
    return result

def get_random_files(subject_key=None):
    """جلب الملفات العشوائية من قاعدة البيانات"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    if subject_key:
        cur.execute('''
            SELECT file_name, file_id, caption, upload_date, file_type 
            FROM random_files 
            WHERE subject_key = %s 
            ORDER BY upload_date DESC
        ''', (subject_key,))
    else:
        cur.execute('''
            SELECT file_name, file_id, caption, upload_date, file_type 
            FROM random_files 
            ORDER BY upload_date DESC
        ''')
    
    files = cur.fetchall()
    
    cur.close()
    conn.close()
    
    # تحويل النتائج إلى قاموس
    result = {}
    for file_name, file_id, caption, upload_date, file_type in files:
        result[file_name] = {
            'file_id': file_id,
            'caption': caption or '',
            'date': upload_date.strftime('%Y-%m-%d %H:%M') if upload_date else '',
            'file_type': file_type or ''
        }
    
    return result

def get_schedule():
    """جلب الجدول الدراسي"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT file_id FROM schedule ORDER BY update_date DESC LIMIT 1')
    result = cur.fetchone()
    
    cur.close()
    conn.close()
    
    return result[0] if result else None

def get_stats():
    """الحصول على إحصائيات"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    stats = {}
    
    for subject_key, subject_name in [
        ('prog2', '💻 Computer Programming II'),
        ('business', '📊 Computer Applications in Business'),
        ('fundamentals', '🖥️ Computer Fundamentals'),
        ('discrete', '🔢 Discrete Structures'),
        ('arabic', '📖 Arabic Language')
    ]:
        cur.execute('''
            SELECT 
                COUNT(CASE WHEN file_type = 'lecture' THEN 1 END) as lectures,
                COUNT(CASE WHEN file_type = 'summary' THEN 1 END) as summaries,
                COUNT(CASE WHEN file_type = 'assignment' THEN 1 END) as assignments
            FROM files 
            WHERE subject_key = %s
        ''', (subject_key,))
        
        lectures, summaries, assignments = cur.fetchone()
        
        cur.execute('SELECT COUNT(*) FROM random_files WHERE subject_key = %s', (subject_key,))
        random_count = cur.fetchone()[0]
        
        stats[subject_name] = {
            'lectures': lectures or 0,
            'summaries': summaries or 0,
            'assignments': assignments or 0,
            'random': random_count or 0
        }
    
    cur.execute('SELECT COUNT(*) FROM schedule')
    has_schedule = cur.fetchone()[0] > 0
    
    cur.close()
    conn.close()
    
    return stats, has_schedule

# ==================== القوائم ====================

def main_menu():
    """القائمة الرئيسية"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("📚 المواد الدراسية", callback_data="subjects"),
        InlineKeyboardButton("📅 الجدول الدراسي", callback_data="schedule"),
        InlineKeyboardButton("❓ مساعدة", callback_data="help")
    ]
    
    global current_user_id
    if current_user_id == ADMIN_ID:
        buttons.append(InlineKeyboardButton("⚙️ تحكم الأدمن", callback_data="admin"))
    
    keyboard.add(*buttons)
    return keyboard

def subjects_menu():
    """قائمة المواد"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    subjects = [
        ('prog2', '💻 Computer Programming II'),
        ('business', '📊 Computer Applications in Business'),
        ('fundamentals', '🖥️ Computer Fundamentals'),
        ('discrete', '🔢 Discrete Structures'),
        ('arabic', '📖 Arabic Language')
    ]
    
    for key, name in subjects:
        keyboard.add(InlineKeyboardButton(name, callback_data=f"sub_{key}"))
    
    keyboard.add(InlineKeyboardButton("🔙 رجوع", callback_data="main"))
    return keyboard

def subject_menu(subject_id):
    """قائمة محتوى المادة (مع زر العشوائيات)"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("📚 محاضرات", callback_data=f"show_{subject_id}_lecture"),
        InlineKeyboardButton("📝 ملخصات", callback_data=f"show_{subject_id}_summary"),
        InlineKeyboardButton("📋 واجبات", callback_data=f"show_{subject_id}_assignment"),
        InlineKeyboardButton("🎲 عشوائيات", callback_data=f"show_{subject_id}_random"),
        InlineKeyboardButton("🔙 رجوع", callback_data="subjects")
    ]
    keyboard.add(*buttons)
    return keyboard

def admin_menu():
    """قائمة الأدمن"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("📤 رفع جدول", callback_data="up_schedule"),
        InlineKeyboardButton("📤 رفع محاضرة", callback_data="up_lecture"),
        InlineKeyboardButton("📤 رفع ملخص", callback_data="up_summary"),
        InlineKeyboardButton("📤 رفع واجب", callback_data="up_assignment"),
        InlineKeyboardButton("🎲 رفع عشوائيات", callback_data="up_random"),
        InlineKeyboardButton("📊 الإحصائيات", callback_data="stats"),
        InlineKeyboardButton("🔙 رجوع", callback_data="main")
    ]
    keyboard.add(*buttons)
    return keyboard

def subject_choice_menu(action):
    """قائمة اختيار المادة للأدمن"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    subjects = [
        ('prog2', '💻 Computer Programming II'),
        ('business', '📊 Computer Applications in Business'),
        ('fundamentals', '🖥️ Computer Fundamentals'),
        ('discrete', '🔢 Discrete Structures'),
        ('arabic', '📖 Arabic Language')
    ]
    
    for key, name in subjects:
        keyboard.add(InlineKeyboardButton(name, callback_data=f"choose_{key}_{action}"))
    
    keyboard.add(InlineKeyboardButton("🔙 رجوع", callback_data="admin"))
    return keyboard

def filename_choice_menu():
    """قائمة اختيار اسم الملف"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("✏️ تغيير الاسم", callback_data="filename_change"),
        InlineKeyboardButton("✅ حفظ كما هو", callback_data="filename_keep"),
        InlineKeyboardButton("❌ إلغاء", callback_data="filename_cancel")
    ]
    keyboard.add(*buttons)
    return keyboard

# ==================== المتغيرات العامة ====================

user_state = {}
current_user_id = None
waiting_for_filename = {}  # لتخزين من ينتظر إدخال اسم ملف جديد

# ==================== الأوامر ====================

@bot.message_handler(commands=['start'])
def start(message):
    """أمر بدء البوت"""
    global current_user_id
    current_user_id = message.from_user.id
    
    welcome_text = f"""
🎓 حياك 🤠 {message.from_user.first_name} 

اختار:
    """
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=main_menu()
    )

@bot.message_handler(commands=['admin'])
def admin(message):
    """أمر دخول لوحة التحكم"""
    if message.from_user.id == ADMIN_ID:
        bot.send_message(
            message.chat.id,
            "⚙️ لوحة تحكم الأدمن",
            reply_markup=admin_menu()
        )
    else:
        bot.send_message(
            message.chat.id,
            "❌ لالا هذا بس الي 🤨!"
        )

# ==================== معالجة الأزرار ====================

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """معالجة جميع الأزرار"""
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    user_id = call.from_user.id
    
    try:
        # ===== القوائم العامة =====
        if call.data == "main":
            bot.edit_message_text(
                "🎓 القائمة الرئيسية",
                chat_id,
                message_id,
                reply_markup=main_menu()
            )
        
        elif call.data == "subjects":
            bot.edit_message_text(
                "📚 اختار المادة الي تريدها:",
                chat_id,
                message_id,
                reply_markup=subjects_menu()
            )
        
        elif call.data == "schedule":
            schedule_file = get_schedule()
            if schedule_file:
                try:
                    bot.send_document(
                        chat_id,
                        schedule_file,
                        caption="📅 الجدول الدراسي",
                        reply_markup=main_menu()
                    )
                except Exception as e:
                    print(f"خطأ في إرسال الجدول: {e}")
                    bot.send_message(
                        chat_id,
                        "❌ حدث خطأ في إرسال الجدول",
                        reply_markup=main_menu()
                    )
            else:
                bot.send_message(
                    chat_id,
                    "📅 لا يوجد جدول دراسي بعد",
                    reply_markup=main_menu()
                )
        
        elif call.data == "help":
            help_text = """
❓ **مساعدة**

📚 **ماكو مساعده دبر روحك بروحك 🙄🤨:**
            """
            bot.send_message(chat_id, help_text, parse_mode='Markdown', reply_markup=main_menu())
        
        # ===== قوائم المواد =====
        elif call.data.startswith("sub_"):
            subject_id = call.data[4:]
            subject_names = {
                'prog2': '💻 Computer Programming II',
                'business': '📊 Computer Applications in Business',
                'fundamentals': '🖥️ Computer Fundamentals',
                'discrete': '🔢 Discrete Structures',
                'arabic': '📖 Arabic Language'
            }
            bot.edit_message_text(
                f"📚 {subject_names.get(subject_id, subject_id)}",
                chat_id,
                message_id,
                reply_markup=subject_menu(subject_id)
            )
        
        # ===== عرض الملفات =====
        elif call.data.startswith("show_"):
            parts = call.data.split("_")
            subject_id = parts[1]
            content_type = parts[2]
            
            type_names = {
                'lecture': 'محاضرات',
                'summary': 'ملخصات',
                'assignment': 'واجبات',
                'random': 'عشوائيات'
            }
            
            if content_type == 'random':
                files = get_random_files(subject_id)
            else:
                files = get_files(subject_id, content_type)
            
            if not files:
                bot.send_message(
                    chat_id,
                    f"❌ لا توجد {type_names[content_type]} لهذه المادة بعد",
                    reply_markup=subject_menu(subject_id)
                )
            else:
                bot.send_message(
                    chat_id,
                    f"📂 جاري إرسال {type_names[content_type]}..."
                )
                for file_name, file_info in files.items():
                    try:
                        # إضافة نوع الملف في الكابشن للعشوائيات
                        caption = f"📄 **{file_name}**\n📅 {file_info.get('date', '')}"
                        if content_type == 'random' and file_info.get('file_type'):
                            caption += f"\n📁 نوع: {file_info['file_type']}"
                        
                        bot.send_document(
                            chat_id,
                            file_info['file_id'],
                            caption=caption,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        print(f"خطأ في إرسال الملف {file_name}: {e}")
                        continue
                bot.send_message(chat_id, "✅ تم إرسال جميع الملفات", reply_markup=subject_menu(subject_id))
        
        # ===== قوائم الأدمن =====
        elif user_id == ADMIN_ID:
            if call.data == "admin":
                bot.edit_message_text(
                    "⚙️ لوحة التحكم",
                    chat_id,
                    message_id,
                    reply_markup=admin_menu()
                )
            
            elif call.data == "up_schedule":
                bot.send_message(
                    chat_id,
                    "📤 **رفع جدول دراسي**\n\nأرسل الجدول (PDF أو صورة)",
                    parse_mode='Markdown'
                )
                user_state[chat_id] = 'schedule'
            
            elif call.data == "up_lecture":
                bot.edit_message_text(
                    "📤 **رفع محاضرة**\n\nاختر المادة:",
                    chat_id,
                    message_id,
                    reply_markup=subject_choice_menu('lecture'),
                    parse_mode='Markdown'
                )
            
            elif call.data == "up_summary":
                bot.edit_message_text(
                    "📤 **رفع ملخص**\n\nاختر المادة:",
                    chat_id,
                    message_id,
                    reply_markup=subject_choice_menu('summary'),
                    parse_mode='Markdown'
                )
            
            elif call.data == "up_assignment":
                bot.edit_message_text(
                    "📤 **رفع واجب**\n\nاختر المادة:",
                    chat_id,
                    message_id,
                    reply_markup=subject_choice_menu('assignment'),
                    parse_mode='Markdown'
                )
            
            elif call.data == "up_random":
                bot.edit_message_text(
                    "🎲 **رفع عشوائيات**\n\nاختر المادة:",
                    chat_id,
                    message_id,
                    reply_markup=subject_choice_menu('random'),
                    parse_mode='Markdown'
                )
            
            elif call.data.startswith("choose_"):
                parts = call.data.split("_")
                subject_id = parts[1]
                file_type = parts[2]
                
                subject_names = {
                    'prog2': '💻 Computer Programming II',
                    'business': '📊 Computer Applications in Business',
                    'fundamentals': '🖥️ Computer Fundamentals',
                    'discrete': '🔢 Discrete Structures',
                    'arabic': '📖 Arabic Language'
                }
                
                type_names = {
                    'lecture': 'المحاضرة',
                    'summary': 'الملخص',
                    'assignment': 'الواجب',
                    'random': 'عشوائيات'
                }
                
                bot.edit_message_text(
                    f"📤 **رفع {type_names[file_type]}**\n"
                    f"المادة: {subject_names.get(subject_id, subject_id)}\n\n"
                    f"أرسل الملف (أي نوع ملف)",
                    chat_id,
                    message_id,
                    parse_mode='Markdown'
                )
                
                user_state[chat_id] = {
                    'action': 'upload',
                    'subject': subject_id,
                    'type': file_type
                }
            
            elif call.data == "stats":
                stats, has_schedule = get_stats()
                total_files = 0
                total_random = 0
                stats_text = "📊 **إحصائيات البوت:**\n\n"
                
                for subject_name, counts in stats.items():
                    total = counts['lectures'] + counts['summaries'] + counts['assignments']
                    total_files += total
                    total_random += counts['random']
                    
                    stats_text += f"**{subject_name}:**\n"
                    stats_text += f"  📚 محاضرات: {counts['lectures']}\n"
                    stats_text += f"  📝 ملخصات: {counts['summaries']}\n"
                    stats_text += f"  📋 واجبات: {counts['assignments']}\n"
                    stats_text += f"  🎲 عشوائيات: {counts['random']}\n\n"
                
                stats_text += f"**📁 إجمالي الملفات:** {total_files}\n"
                stats_text += f"**🎲 إجمالي العشوائيات:** {total_random}\n"
                stats_text += f"**📅 الجدول:** {'✅ موجود' if has_schedule else '❌ غير موجود'}"
                
                bot.send_message(chat_id, stats_text, parse_mode='Markdown', reply_markup=admin_menu())
            
            # ===== معالجة خيارات اسم الملف =====
            elif call.data == "filename_change":
                bot.send_message(
                    chat_id,
                    "✏️ **أرسل الاسم الجديد للملف** (بدون امتداد)",
                    parse_mode='Markdown'
                )
                waiting_for_filename[chat_id] = True
            
            elif call.data == "filename_keep":
                # حفظ الملف باسمه الحالي
                temp_file = get_temp_file(chat_id)
                if temp_file:
                    if temp_file['is_random']:
                        success = save_random_file(
                            temp_file['subject_key'],
                            temp_file['file_name'],
                            temp_file['file_id'],
                            temp_file['caption'],
                            "ملف عشوائي"
                        )
                    else:
                        success = save_file(
                            temp_file['subject_key'],
                            temp_file['file_type'],
                            temp_file['file_name'],
                            temp_file['file_id'],
                            temp_file['caption']
                        )
                    
                    if success:
                        type_names = {
                            'lecture': 'المحاضرة',
                            'summary': 'الملخص',
                            'assignment': 'الواجب',
                            'random': 'العشوائيات'
                        }
                        subject_names = {
                            'prog2': '💻 Computer Programming II',
                            'business': '📊 Computer Applications in Business',
                            'fundamentals': '🖥️ Computer Fundamentals',
                            'discrete': '🔢 Discrete Structures',
                            'arabic': '📖 Arabic Language'
                        }
                        
                        file_type_display = 'random' if temp_file['is_random'] else temp_file['file_type']
                        
                        bot.send_message(
                            chat_id,
                            f"✅ **تم حفظ {type_names.get(file_type_display, 'الملف')} بنجاح!**\n"
                            f"📁 المادة: {subject_names.get(temp_file['subject_key'], temp_file['subject_key'])}\n"
                            f"📄 الملف: {temp_file['file_name']}",
                            parse_mode='Markdown',
                            reply_markup=admin_menu()
                        )
                    else:
                        bot.send_message(
                            chat_id,
                            "❌ **فشل في حفظ الملف**",
                            parse_mode='Markdown',
                            reply_markup=admin_menu()
                        )
                    
                    # حذف الملف المؤقت
                    delete_temp_file(chat_id)
                else:
                    bot.send_message(chat_id, "❌ لا يوجد ملف مؤقت", reply_markup=admin_menu())
            
            elif call.data == "filename_cancel":
                delete_temp_file(chat_id)
                bot.send_message(
                    chat_id,
                    "❌ **تم إلغاء رفع الملف**",
                    parse_mode='Markdown',
                    reply_markup=admin_menu()
                )
    
    except Exception as e:
        print(f"خطأ في معالجة الزر: {e}")
        bot.send_message(chat_id, "❌ حدث خطأ، الرجاء المحاولة مرة أخرى", reply_markup=main_menu())

# ==================== استقبال الملفات ====================

@bot.message_handler(content_types=['document', 'photo', 'video', 'audio', 'voice'])
def handle_files(message):
    """معالجة الملفات المرفوعة من الأدمن"""
    chat_id = message.chat.id
    
    # التحقق من الصلاحية
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ أنت غير مخول برفع الملفات")
        return
    
    # التحقق من وجود حالة
    if chat_id not in user_state:
        bot.reply_to(message, "❌ الرجاء اختيار نوع الملف أولاً من لوحة التحكم (/admin)")
        return
    
    state = user_state[chat_id]
    print(f"📥 استقبال ملف من الأدمن - الحالة: {state}")
    
    # تحديد معلومات الملف
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        file_type = "document"
        print(f"📄 ملف مستند: {file_name}")
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = f"صورة_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        file_type = "photo"
        print(f"🖼️ صورة: {file_name}")
    elif message.video:
        file_id = message.video.file_id
        file_name = f"فيديو_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        file_type = "video"
        print(f"🎥 فيديو: {file_name}")
    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or f"صوت_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
        file_type = "audio"
        print(f"🎵 صوت: {file_name}")
    elif message.voice:
        file_id = message.voice.file_id
        file_name = f"تسجيل_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ogg"
        file_type = "voice"
        print(f"🎤 تسجيل: {file_name}")
    else:
        bot.reply_to(message, "❌ نوع ملف غير مدعوم")
        return
    
    caption = message.caption or ""
    
    # ===== حفظ الجدول =====
    if state == 'schedule':
        if save_schedule(file_id):
            bot.reply_to(
                message, 
                "✅ **تم حفظ الجدول بنجاح!**", 
                parse_mode='Markdown',
                reply_markup=admin_menu()
            )
        else:
            bot.reply_to(
                message, 
                "❌ **فشل في حفظ الجدول**", 
                parse_mode='Markdown',
                reply_markup=admin_menu()
            )
        # مسح الحالة
        del user_state[chat_id]
    
    # ===== حفظ محتوى المواد =====
    elif isinstance(state, dict) and state.get('action') == 'upload':
        subject_id = state['subject']
        file_content_type = state['type']  # lecture, summary, assignment, random
        is_random = (file_content_type == 'random')
        
        # حفظ الملف مؤقتاً
        save_temp_file(chat_id, file_id, file_name, subject_id, file_content_type, caption, is_random)
        
        # عرض خيارات اسم الملف
        bot.send_message(
            chat_id,
            f"📄 **اسم الملف:** {file_name}\n\n"
            f"ماذا تريد أن تفعل؟",
            parse_mode='Markdown',
            reply_markup=filename_choice_menu()
        )
        
        # مسح الحالة مؤقتاً (سنكمل بعد اختيار اسم الملف)
        # لا نحذف user_state هنا لأننا بنستخدم temp_file بدلاً منه

# ==================== استقبال أسماء الملفات الجديدة ====================

@bot.message_handler(func=lambda message: message.chat.id in waiting_for_filename and waiting_for_filename[message.chat.id])
def handle_new_filename(message):
    """معالجة اسم الملف الجديد"""
    chat_id = message.chat.id
    new_filename = message.text.strip()
    
    # إزالة الامتداد إذا كان موجوداً
    if '.' in new_filename:
        new_filename = new_filename.split('.')[0]
    
    # جلب الملف المؤقت
    temp_file = get_temp_file(chat_id)
    if not temp_file:
        bot.send_message(chat_id, "❌ لا يوجد ملف مؤقت", reply_markup=admin_menu())
        waiting_for_filename[chat_id] = False
        return
    
    # الحصول على الامتداد الأصلي
    old_filename = temp_file['file_name']
    extension = ''
    if '.' in old_filename:
        extension = '.' + old_filename.split('.')[-1]
    
    # تكوين الاسم الجديد
    new_full_filename = new_filename + extension
    
    # حفظ الملف بالاسم الجديد
    if temp_file['is_random']:
        success = save_random_file(
            temp_file['subject_key'],
            new_full_filename,
            temp_file['file_id'],
            temp_file['caption'],
            "ملف عشوائي"
        )
    else:
        success = save_file(
            temp_file['subject_key'],
            temp_file['file_type'],
            new_full_filename,
            temp_file['file_id'],
            temp_file['caption']
        )
    
    if success:
        type_names = {
            'lecture': 'المحاضرة',
            'summary': 'الملخص',
            'assignment': 'الواجب',
            'random': 'العشوائيات'
        }
        subject_names = {
            'prog2': '💻 Computer Programming II',
            'business': '📊 Computer Applications in Business',
            'fundamentals': '🖥️ Computer Fundamentals',
            'discrete': '🔢 Discrete Structures',
            'arabic': '📖 Arabic Language'
        }
        
        file_type_display = 'random' if temp_file['is_random'] else temp_file['file_type']
        
        bot.send_message(
            chat_id,
            f"✅ **تم حفظ {type_names.get(file_type_display, 'الملف')} بنجاح!**\n"
            f"📁 المادة: {subject_names.get(temp_file['subject_key'], temp_file['subject_key'])}\n"
            f"📄 الملف: {new_full_filename}",
            parse_mode='Markdown',
            reply_markup=admin_menu()
        )
    else:
        bot.send_message(
            chat_id,
            "❌ **فشل في حفظ الملف**",
            parse_mode='Markdown',
            reply_markup=admin_menu()
        )
    
    # تنظيف
    delete_temp_file(chat_id)
    waiting_for_filename[chat_id] = False
    
    # حذف الحالة الأصلية إذا كانت موجودة
    if chat_id in user_state:
        del user_state[chat_id]

# ==================== تشغيل البوت ====================

@app.route('/')
def home():
    return "✅ البوت شغال مع PostgreSQL!"

def run_bot():
    print("✅ البوت يعمل مع PostgreSQL...")
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"خطأ في البوت: {e}")

if __name__ == '__main__':
    # تشغيل البوت في خلفية
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # تشغيل خادم Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
