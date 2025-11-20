import os
import threading
import time
import requests
import textwrap
import google.generativeai as genai
import json
import feedparser
from flask import Flask
from telegram import Update, ParseMode, InputMediaPhoto
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# --- CẤU HÌNH ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MY_USER_ID = os.environ.get("MY_USER_ID") 

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

app = Flask(__name__)

# --- CẤU HÌNH SPY ---
KEYWORDS = [# --- Địa danh & Từ khóa chung ---
    "nha trang", "khánh hòa", "cam ranh", "diên khánh", "vân phong", 
    "cao tốc", "quy hoạch", "sân bay", "cảng biển", "caraworld", "la tiên", "paramount",

    # --- Cá Mập & Dự án lớn ---
    "vingroup", "vinpearl", "vinhomes",
    "kdi", "vega city",               # KDI Holdings (Dự án Vega City)
    "kn holdings", "kn paradise",     # KN Holdings (Dự án KN Paradise)
    "sungroup", "sun group",          # Sun Group
    "crystal bay",                    # Crystal Bay (Cũng rất mạnh ở Nha Trang)
    "hưng thịnh",                     # Hưng Thịnh (Nhiều dự án ở Bắc Bán Đảo)
    "novaland"]
RSS_FEEDS = [
    "https://vnexpress.net/rss/kinh-doanh/bat-dong-san.rss",
    "https://cafef.vn/bat-dong-san.rss",
    "https://thanhnien.vn/rss/kinh-te/bat-dong-san.rss"
]
seen_links = [] 

@app.route('/')
def index(): return "Bot Content Spy Running!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- RADAR SĂN TIN ---
def check_news_updates(updater):
    while True:
        print("🛰️ Đang quét tin...")
        found_new = False
        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    if entry.link in seen_links: continue
                    
                    title_lower = entry.title.lower()
                    summary_lower = entry.summary.lower() if 'summary' in entry else ""
                    
                    if any(kw in title_lower or kw in summary_lower for kw in KEYWORDS):
                        msg = f"🔥 **TIN HOT THỊ TRƯỜNG!**\n\n📰 **{entry.title}**\n\n🔗 {entry.link}\n\n👇 *Copy link hoặc tiêu đề gửi lại cho tôi để tôi viết bài phân tích ngay!*"
                        if MY_USER_ID:
                            updater.bot.send_message(chat_id=MY_USER_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
                        seen_links.append(entry.link)
                        if len(seen_links) > 100: seen_links.pop(0)
                        found_new = True
            except Exception as e:
                print(f"Lỗi RSS: {e}")
        time.sleep(1800) # 30 phút quét 1 lần

# --- HỌA SĨ VẼ ẢNH (STYLE DILAND) ---
def draw_wrapped_text(draw, text, font, text_color, x, y, max_width, line_spacing=10):
    lines = []
    words = text.split(' ')
    current_line = words[0]
    for word in words[1:]:
        bbox = draw.textbbox((0, 0), current_line + ' ' + word, font=font)
        if bbox[2] <= max_width:
            current_line += ' ' + word
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)
    
    current_y = y
    for line in lines:
        draw.text((x, current_y), line, font=font, fill=text_color)
        bbox = draw.textbbox((0, 0), line, font=font)
        current_y += (bbox[3] - bbox[1]) + line_spacing
    return current_y

def create_modern_slide(title, content, index):
    W, H = 1080, 1080
    BG_COLOR = "#051622" # Xanh đen
    TEXT_WHITE = "#FFFFFF"
    TEXT_CYAN = "#00BAFF" # Xanh sáng
    TEXT_GOLD = "#D4AF37" # Vàng đồng
    BOX_BG = "#0F2B3D"

    img = Image.new('RGB', (W, H), color=BG_COLOR)
    draw = ImageDraw.Draw(img)

    try:
        font_big = ImageFont.truetype("bold.otf", 300)
        font_title = ImageFont.truetype("bold.otf", 70)
        font_body = ImageFont.truetype("regular.otf", 50)
        font_box = ImageFont.truetype("regular.otf", 45)
    except:
        font_big = ImageFont.load_default()
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_box = ImageFont.load_default()

    margin_left = 80
    draw.text((margin_left, 150), str(index), font=font_big, fill=TEXT_CYAN)
    draw_wrapped_text(draw, title.upper(), font_title, TEXT_WHITE, 400, 200, 600)
    draw.line([(margin_left, 550), (W - margin_left, 550)], fill="#334E68", width=3)
    next_y = draw_wrapped_text(draw, content, font_body, TEXT_WHITE, margin_left, 600, W - 2*margin_left, line_spacing=20)

    box_y = next_y + 80
    box_height = 250
    if box_y + box_height < H - 50:
        draw.rounded_rectangle([(margin_left, box_y), (W - margin_left, box_y + box_height)], radius=30, fill=BOX_BG, outline=TEXT_GOLD, width=2)
        draw.ellipse([(margin_left + 40, box_y + 40), (margin_left + 60, box_y + 60)], fill="red")
        quote = "DILAND: Giá trị thật - Nhu cầu thật."
        draw_wrapped_text(draw, quote, font_box, TEXT_WHITE, margin_left + 90, box_y + 35, W - 2*margin_left - 100)

    bio = BytesIO()
    img.save(bio, 'JPEG', quality=95)
    bio.seek(0)
    return bio

# --- TRÍ TUỆ NHÂN TẠO (GEMINI) ---
def generate_content(topic):
    prompt = f"""
    Bạn là Chuyên gia Content BĐS Khánh Hòa.
    Chủ đề: "{topic}".
    Viết nội dung dạng Slide Facebook.
    Yêu cầu Output JSON:
    {{
        "title_text": "Tiêu đề ngắn gọn, viết hoa, giật gân (để làm ảnh bìa)",
        "slides": [
            {{ "title": "TIÊU ĐỀ Ý 1", "content": "Nội dung ý 1 (tối đa 40 từ)." }},
            {{ "title": "TIÊU ĐỀ Ý 2", "content": "Nội dung ý 2..." }},
            {{ "title": "TIÊU ĐỀ Ý 3", "content": "Nội dung ý 3..." }}
        ],
        "caption": "Caption Facebook hấp dẫn, chuẩn SEO."
    }}
    """
    try:
        response = model.generate_content(prompt)
        clean_json = response.text.replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except: return None

def handle_message(update: Update, context: CallbackContext):
    user_input = update.message.text
    chat_id = update.message.chat_id
    print(f"User ID cua ban la: {chat_id}") # In ra log để bạn lấy ID

    update.message.reply_text(f"🧠 Đang phân tích: '{user_input}'...")
    data = generate_content(user_input)
    
    if not data:
        update.message.reply_text("❌ AI đang bận. Thử lại sau.")
        return

    update.message.reply_text(f"🎯 **TITLE BÌA:**\n`{data['title_text']}`", parse_mode=ParseMode.MARKDOWN)
    update.message.reply_text("🎨 Đang vẽ slide...")
    
    album = []
    for i, slide in enumerate(data['slides'], 1):
        img_bio = create_modern_slide(slide['title'], slide['content'], index=i)
        if i == 1:
            album.append(InputMediaPhoto(media=img_bio, caption=data['caption']))
        else:
            album.append(InputMediaPhoto(media=img_bio))

    try:
        context.bot.send_media_group(chat_id=chat_id, media=album)
        update.message.reply_text("✅ Xong! Forward sang Bot Đăng Bài nhé.")
    except Exception as e:
        update.message.reply_text(f"❌ Lỗi gửi ảnh: {e}")

if __name__ == '__main__':
    threading.Thread(target=run_web_server).start()
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    spy_thread = threading.Thread(target=check_news_updates, args=(updater,))
    spy_thread.start()
    
    print("Bot Content Ready...")
    updater.start_polling()

    updater.idle()
