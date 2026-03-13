import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import json
from datetime import datetime
from flask import Flask
import threading

# التوكن من متغيرات البيئة
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))

# تهيئة البوت
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ملف قاعدة البيانات
DATA_FILE = 'database.json'

# المواد الدراسية
SUBJECTS = {
    'prog2': '💻 Computer Programming II',
    'business': '📊 Computer Applications in Business',
    'fundamentals': '🖥️ Computer Fundamentals',
    'discrete': '🔢 Discrete Structures',
    'arabic': '📖 Arabic Language'
}

# تحميل البيانات
def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"خطأ في تحميل البيانات: {e}")
    
    return {
        'schedule': None,
        'subjects': {
            sid: {
                'lectures': {},
                'summaries': {},
                'assignments': {}
            } for sid in SUBJECTS.keys()
        }
    }

# حفظ البيانات
def save_data(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"خطأ في حفظ البيانات: {e}")

data = load_data()
user_state = {}
current_user_id = None

# ==================== القوائم ====================

def main_menu():
    """القائمة الرئيسية"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("📚 المواد الدراسية", callback_data="subjects"),
        InlineKeyboardButton("📅 الجدول الدراسي", callback_data="schedule"),
        InlineKeyboardButton("❓ مساعدة", callback_data="help")
    ]
    
    if current_user_id == ADMIN_ID:
        buttons.append(InlineKeyboardButton("⚙️ تحكم الأدمن", callback_data="admin"))
    
    keyboard.add(*buttons)
    return keyboard

def subjects_menu():
    """قائمة المواد"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    for sid, name in SUBJECTS.items():
        keyboard.add(InlineKeyboardButton(name, callback_data=f"sub_{sid}"))
    keyboard.add(InlineKeyboardButton("🔙 رجوع", callback_data="main"))
    return keyboard

def subject_menu(subject_id):
    """قائمة محتوى المادة"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("📚 محاضرات", callback_data=f"show_{subject_id}_lectures"),
        InlineKeyboardButton("📝 ملخصات", callback_data=f"show_{subject_id}_summaries"),
        InlineKeyboardButton("📋 واجبات", callback_data=f"show_{subject_id}_assignments"),
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

# ==================== الأوامر ====================

@bot.message_handler(commands=['start'])
def start(message):
    """أمر بدء البوت"""
    global current_user_id
    current_user_id = message.from_user.id
    
    welcome_text = f"""
🎓 مرحباً بك {message.from_user.first_name} في بوت كلية نظم المعلومات

اختر ما تريد من القائمة:
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
            "❌ هذا الأمر للأدمن فقط!"
        )

# ==================== معالجة الأزرار ====================

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """معالجة جميع الأزرار"""
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    user_id = call.from_user.id
    
    try:
        # القوائم العامة
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
            if data['schedule']:
                try:
                    bot.send_document(
                        chat_id,
                        data['schedule'],
                        caption="📅 الجدول الدراسي",
                        reply_markup=main_menu()
                    )
                except:
                    bot.send_message(
                        chat_id,
                        "❌ حدث خطأ في إرسال الجدول"
                    )
            else:
                bot.send_message(
                    chat_id,
                    "📅 لا يوجد جدول دراسي بعد",
                    reply_markup=main_menu()
                )
        
        elif call.data == "help":
            help_text = """
❓ مساعدة البوت

📚 المواد الدراسية:
   اختر المادة ثم:
   • 📚 محاضرات
   • 📝 ملخصات
   • 📋 واجبات

📅 الجدول الدراسي:
   يعرض الجدول إذا كان متوفر

للتواصل: @YourChannel
            """
            bot.send_message(chat_id, help_text, reply_markup=main_menu())
        
        # قوائم المواد
        elif call.data.startswith("sub_"):
            subject_id = call.data[4:]
            bot.edit_message_text(
                f"📚 {SUBJECTS[subject_id]}",
                chat_id,
                message_id,
                reply_markup=subject_menu(subject_id)
            )
        
        # عرض الملفات
        elif call.data.startswith("show_"):
            parts = call.data.split("_")
            subject_id = parts[1]
            content_type = parts[2]
            
            files = data['subjects'][subject_id][content_type]
            
            if not files:
                content_names = {
                    'lectures': 'محاضرات',
                    'summaries': 'ملخصات',
                    'assignments': 'واجبات'
                }
                bot.send_message(
                    chat_id,
                    f"❌ لا توجد {content_names[content_type]} لهذه المادة بعد",
                    reply_markup=main_menu()
                )
            else:
                for file_name, file_info in files.items():
                    try:
                        bot.send_document(
                            chat_id,
                            file_info['file_id'],
                            caption=f"📄 {file_name}\n📅 {file_info.get('date', '')}",
                            reply_markup=main_menu()
                        )
                    except:
                        continue
        
        # قوائم الأدمن
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
                    "📤 أرسل الجدول الدراسي (PDF أو صورة)"
                )
                user_state[chat_id] = 'schedule'
            
            elif call.data == "up_lecture":
                bot.send_message(
                    chat_id,
                    "📤 أرسل المحاضرة (PDF)\nاكتب اسم المادة في التعليق"
                )
                user_state[chat_id] = 'lecture'
            
            elif call.data == "up_summary":
                bot.send_message(
                    chat_id,
                    "📤 أرسل الملخص (PDF)\nاكتب اسم المادة في التعليق"
                )
                user_state[chat_id] = 'summary'
            
            elif call.data == "up_assignment":
                bot.send_message(
                    chat_id,
                    "📤 أرسل الواجب (PDF)\nاكتب اسم المادة في التعليق"
                )
                user_state[chat_id] = 'assignment'
            
            elif call.data == "stats":
                total_files = 0
                stats_text = "📊 إحصائيات البوت:\n\n"
                
                for sid, name in SUBJECTS.items():
                    sub = data['subjects'][sid]
                    lec_count = len(sub['lectures'])
                    sum_count = len(sub['summaries'])
                    ass_count = len(sub['assignments'])
                    total = lec_count + sum_count + ass_count
                    total_files += total
                    
                    stats_text += f"{name}:\n"
                    stats_text += f"  📚 محاضرات: {lec_count}\n"
                    stats_text += f"  📝 ملخصات: {sum_count}\n"
                    stats_text += f"  📋 واجبات: {ass_count}\n\n"
                
                stats_text += f"📁 إجمالي الملفات: {total_files}\n"
                stats_text += f"📅 الجدول: {'✅ موجود' if data['schedule'] else '❌ غير موجود'}"
                
                bot.send_message(chat_id, stats_text, reply_markup=admin_menu())
    
    except Exception as e:
        print(f"خطأ في معالجة الزر: {e}")
        # إذا فشل التعديل، نرسل رسالة جديدة
        bot.send_message(chat_id, "حدث خطأ، الرجاء المحاولة مرة أخرى", reply_markup=main_menu())

# ==================== استقبال الملفات ====================

@bot.message_handler(content_types=['document', 'photo'])
def handle_files(message):
    """معالجة الملفات المرفوعة من الأدمن"""
    chat_id = message.chat.id
    
    # التحقق من الصلاحية
    if message.from_user.id != ADMIN_ID:
        return
    
    # التحقق من وجود حالة
    if chat_id not in user_state:
        bot.send_message(chat_id, "الرجاء اختيار نوع الملف أولاً من لوحة التحكم")
        return
    
    # تحديد نوع الملف
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = f"صورة_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    else:
        bot.send_message(chat_id, "❌ نوع ملف غير مدعوم")
        return
    
    caption = message.caption or ""
    action = user_state[chat_id]
    
    # حفظ الجدول
    if action == 'schedule':
        data['schedule'] = file_id
        save_data(data)
        bot.send_message(chat_id, "✅ تم حفظ الجدول بنجاح!", reply_markup=admin_menu())
    
    # حفظ محتوى المواد
    elif action in ['lecture', 'summary', 'assignment']:
        # تحويل نوع المحتوى لصيغة الجمع
        content_type = action + 's'
        
        # البحث عن المادة في التعليق
        found = False
        caption_lower = caption.lower()
        
        for subject_id, subject_name in SUBJECTS.items():
            # البحث عن اسم المادة في التعليق
            if (subject_id in caption_lower or 
                any(word in caption_lower for word in subject_name.lower().split())):
                
                # حفظ الملف
                data['subjects'][subject_id][content_type][file_name] = {
                    'file_id': file_id,
                    'date': datetime.now().strftime('%Y-%m-%d %H:%M')
                }
                save_data(data)
                
                type_names = {
                    'lectures': 'المحاضرة',
                    'summaries': 'الملخص',
                    'assignments': 'الواجب'
                }
                
                bot.send_message(
                    chat_id,
                    f"✅ تم حفظ {type_names[content_type]} في مادة {subject_name}!",
                    reply_markup=admin_menu()
                )
                found = True
                break
        
        if not found:
            subjects_list = "\n".join([f"• {name}" for name in SUBJECTS.values()])
            bot.send_message(
                chat_id,
                f"❌ لم أتمكن من تحديد المادة\n\n"
                f"المواد المتاحة:\n{subjects_list}\n\n"
                f"يرجى كتابة اسم المادة في التعليق عند رفع الملف",
                reply_markup=admin_menu()
            )
    
    # مسح الحالة بأمان
    if chat_id in user_state:
        del user_state[chat_id]

# ==================== تشغيل البوت ====================

@app.route('/')
def home():
    return "✅ البوت شغال!"

def run_bot():
    print("✅ البوت يعمل...")
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
