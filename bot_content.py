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
KEYWORDS = [
    # 1. Địa danh (Bắt buộc phải có để định vị thị trường)
    "nha trang", "khánh hòa", "cam ranh", "diên khánh", 
    "vân phong", "cam lâm", "bãi dài", "ninh hòa",
    
    # 2. Các dự án/địa điểm đặc thù (Nhắc tên là biết ở Khánh Hòa)
    "vega city", "kn paradise", "vinpearl nha trang", 
    "hòn tre", "bắc bán đảo", "đầm thủy triều",
    
    # 3. Các từ khóa hẹp đi kèm địa phương (tránh bắt nhầm)
    "tỉnh khánh hòa", "tp nha trang"
]
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

# ==========================================
# PHẦN 1: CHỨC NĂNG SPY (SĂN TIN) - ĐÃ NÂNG CẤP
# ==========================================
def check_news_updates(updater):
    """Chạy ngầm 30 phút/lần, chỉ gửi tối đa 5 tin mỗi lần"""
    while True:
        print("🛰️ Đang quét tin tức thị trường...")
        
        # Danh sách chứa các tin mới tìm được trong đợt quét này
        found_entries = []
        
        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    # 1. Kiểm tra xem tin này đã báo chưa
                    if entry.link in seen_links:
                        continue
                    
                    # 2. Kiểm tra xem đã có trong danh sách chờ chưa (tránh trùng lặp giữa các báo)
                    if any(e.link == entry.link for e in found_entries):
                        continue

                    # 3. Kiểm tra từ khóa
                    title_lower = entry.title.lower()
                    summary_lower = entry.summary.lower() if 'summary' in entry else ""
                    
                    if any(kw in title_lower or kw in summary_lower for kw in KEYWORDS):
                        found_entries.append(entry)
                        
            except Exception as e:
                print(f"Lỗi đọc RSS {feed_url}: {e}")
        
        # --- LỌC VÀ GỬI TIN ---
        if found_entries:
            # Chỉ lấy tối đa 5 bài đầu tiên (Thường là mới nhất)
            # Bạn có thể sửa số 5 thành số khác tùy ý
            top_picks = found_entries[:5]
            
            print(f"Tìm thấy {len(found_entries)} tin, sẽ gửi {len(top_picks)} tin.")

            for entry in top_picks:
                msg = f"🔥 **TIN HOT THỊ TRƯỜNG!**\n\n📰 **{entry.title}**\n\n🔗 {entry.link}\n\n👇 *Copy tiêu đề gửi lại cho tôi để phân tích!*"
                
                # Gửi cho Sếp
                if MY_USER_ID:
                    try:
                        updater.bot.send_message(chat_id=MY_USER_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
                        # Chỉ khi gửi thành công mới đánh dấu là đã xem
                        seen_links.append(entry.link)
                    except Exception as e:
                        print(f"Lỗi gửi tin spy: {e}")
                
                # Nghỉ 2 giây giữa các tin để tránh bị Telegram chặn spam
                time.sleep(2)

            # Xóa bớt bộ nhớ đệm nếu quá đầy
            if len(seen_links) > 200: 
                del seen_links[:50]
        else:
            print("Không có tin mới phù hợp.")
            
        # Ngủ 30 phút (1800 giây) rồi quét tiếp
        time.sleep(1800)

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

