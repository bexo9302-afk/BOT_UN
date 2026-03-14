import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import psycopg2
from psycopg2.extras import Json
from datetime import datetime
from flask import Flask
import threading
import json

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
        stats[subject_name] = {
            'lectures': lectures or 0,
            'summaries': summaries or 0,
            'assignments': assignments or 0
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
    """قائمة محتوى المادة"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("📚 محاضرات", callback_data=f"show_{subject_id}_lecture"),
        InlineKeyboardButton("📝 ملخصات", callback_data=f"show_{subject_id}_summary"),
        InlineKeyboardButton("📋 واجبات", callback_data=f"show_{subject_id}_assignment"),
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

# ==================== المتغيرات العامة ====================

user_state = {}
current_user_id = None

# ==================== الأوامر ====================

@bot.message_handler(commands=['start'])
def start(message):
    """أمر بدء البوت"""
    global current_user_id
    current_user_id = message.from_user.id
    
    welcome_text = f"""
🎓 حياك🤠 {message.from_user.first_name} 

اختار :
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
            "❌لالا هذا بس الي 🤨!"
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
                "📚 اختر المادة التي تريدها:",
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

📚 **ماكو مساعده دبر روحك. بروحك🙄🤨:**

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
            file_type = parts[2]
            
            type_names = {
                'lecture': 'محاضرات',
                'summary': 'ملخصات',
                'assignment': 'واجبات'
            }
            
            files = get_files(subject_id, file_type)
            
            if not files:
                bot.send_message(
                    chat_id,
                    f"❌ لا توجد {type_names[file_type]} لهذه المادة بعد",
                    reply_markup=subject_menu(subject_id)
                )
            else:
                bot.send_message(
                    chat_id,
                    f"📂 جاري إرسال {type_names[file_type]}..."
                )
                for file_name, file_info in files.items():
                    try:
                        bot.send_document(
                            chat_id,
                            file_info['file_id'],
                            caption=f"📄 **{file_name}**\n📅 {file_info.get('date', '')}",
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
                    'assignment': 'الواجب'
                }
                
                bot.edit_message_text(
                    f"📤 **رفع {type_names[file_type]}**\n"
                    f"المادة: {subject_names.get(subject_id, subject_id)}\n\n"
                    f"أرسل الملف (PDF أو صورة)",
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
                stats_text = "📊 **إحصائيات البوت:**\n\n"
                
                for subject_name, counts in stats.items():
                    total = counts['lectures'] + counts['summaries'] + counts['assignments']
                    total_files += total
                    
                    stats_text += f"**{subject_name}:**\n"
                    stats_text += f"  📚 محاضرات: {counts['lectures']}\n"
                    stats_text += f"  📝 ملخصات: {counts['summaries']}\n"
                    stats_text += f"  📋 واجبات: {counts['assignments']}\n\n"
                
                stats_text += f"**📁 إجمالي الملفات:** {total_files}\n"
                stats_text += f"**📅 الجدول:** {'✅ موجود' if has_schedule else '❌ غير موجود'}"
                
                bot.send_message(chat_id, stats_text, parse_mode='Markdown', reply_markup=admin_menu())
    
    except Exception as e:
        print(f"خطأ في معالجة الزر: {e}")
        bot.send_message(chat_id, "❌ حدث خطأ، الرجاء المحاولة مرة أخرى", reply_markup=main_menu())

# ==================== استقبال الملفات ====================

@bot.message_handler(content_types=['document', 'photo'])
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
        print(f"📄 ملف مستند: {file_name}")
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = f"صورة_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        print(f"🖼️ صورة: {file_name}")
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
    
    # ===== حفظ محتوى المواد =====
    elif isinstance(state, dict) and state.get('action') == 'upload':
        subject_id = state['subject']
        file_type = state['type']  # lecture, summary, assignment
        
        type_names = {
            'lecture': 'المحاضرة',
            'summary': 'الملخص',
            'assignment': 'الواجب'
        }
        
        subject_names = {
            'prog2': '💻 Computer Programming II',
            'business': '📊 Computer Applications in Business',
            'fundamentals': '🖥️ Computer Fundamentals',
            'discrete': '🔢 Discrete Structures',
            'arabic': '📖 Arabic Language'
        }
        
        # حفظ الملف في قاعدة البيانات
        if save_file(subject_id, file_type, file_name, file_id, caption):
            bot.reply_to(
                message,
                f"✅ **تم حفظ {type_names[file_type]} بنجاح!**\n"
                f"📁 المادة: {subject_names.get(subject_id, subject_id)}\n"
                f"📄 الملف: {file_name}",
                parse_mode='Markdown',
                reply_markup=admin_menu()
            )
        else:
            bot.reply_to(
                message,
                f"❌ **فشل في حفظ {type_names[file_type]}**",
                parse_mode='Markdown',
                reply_markup=admin_menu()
            )
    
    # مسح الحالة
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
