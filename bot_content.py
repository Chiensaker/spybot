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
from bs4 import BeautifulSoup # Thư viện đọc web

# ==============================================================================
# 1. CẤU HÌNH HỆ THỐNG
# ==============================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MY_USER_ID = os.environ.get("MY_USER_ID") 

# Cấu hình AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Web Server ảo để giữ Bot sống
app = Flask(__name__)

@app.route('/')
def index(): return "Bot Content Ultimate Running!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ==============================================================================
# 2. CẤU HÌNH SĂN TIN (SPY)
# ==============================================================================
# Bộ lọc từ khóa chuẩn Local Khánh Hòa
KEYWORDS = [
    "nha trang", "khánh hòa", "cam ranh", "diên khánh", 
    "vân phong", "cam lâm", "bãi dài", "ninh hòa",
    "vega city", "kn paradise", "vinpearl", 
    "hòn tre", "bắc bán đảo", "đầm thủy triều",
    "tỉnh khánh hòa", "tp nha trang"
]

RSS_FEEDS = [
    "https://vnexpress.net/rss/kinh-doanh/bat-dong-san.rss",
    "https://cafef.vn/bat-dong-san.rss",
    "https://thanhnien.vn/rss/kinh-te/bat-dong-san.rss"
]
seen_links = [] 

def check_news_updates(updater):
    """Chạy ngầm 30 phút/lần để quét báo"""
    while True:
        print("🛰️ Đang quét tin tức thị trường...")
        found_new = False
        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    if entry.link in seen_links: continue
                    
                    title_lower = entry.title.lower()
                    summary_lower = entry.summary.lower() if 'summary' in entry else ""
                    
                    if any(kw in title_lower or kw in summary_lower for kw in KEYWORDS):
                        msg = f"🔥 **TIN HOT KHÁNH HÒA!**\n\n📰 **{entry.title}**\n\n🔗 {entry.link}\n\n👇 *Gửi Link này cho tôi để phân tích ngay!*"
                        if MY_USER_ID:
                            updater.bot.send_message(chat_id=MY_USER_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
                        seen_links.append(entry.link)
                        if len(seen_links) > 100: seen_links.pop(0)
                        found_new = True
            except Exception as e:
                print(f"Lỗi RSS: {e}")
        time.sleep(1800)

# ==============================================================================
# 3. CHỨC NĂNG ĐỌC BÁO TỪ LINK
# ==============================================================================
def get_article_content(url):
    """Truy cập link và lấy nội dung chữ"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Lấy toàn bộ thẻ <p> (đoạn văn)
        paragraphs = soup.find_all('p')
        content = "\n".join([p.get_text() for p in paragraphs])
        
        # Cắt bớt nếu quá dài (để tránh lỗi AI quá tải token)
        return content[:8000] 
    except Exception as e:
        print(f"Lỗi đọc link: {e}")
        return None

# ==============================================================================
# 4. CHỨC NĂNG VẼ ẢNH (DESIGNER)
# ==============================================================================
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
    # Cấu hình màu sắc DILAND
    W, H = 1080, 1080
    BG_COLOR = "#051622"      # Xanh đen đậm
    TEXT_WHITE = "#FFFFFF"
    TEXT_CYAN = "#00BAFF"     # Xanh sáng (Số thứ tự)
    TEXT_GOLD = "#D4AF37"     # Vàng đồng (Viền hộp)
    BOX_BG = "#0F2B3D"        # Nền hộp

    img = Image.new('RGB', (W, H), color=BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Load Font (Ưu tiên font upload, nếu không có dùng mặc định)
    try:
        font_big = ImageFont.truetype("bold.ttf", 300)
        font_title = ImageFont.truetype("bold.ttf", 70)
        font_body = ImageFont.truetype("regular.ttf", 50)
        font_box = ImageFont.truetype("regular.ttf", 45)
    except:
        font_big = ImageFont.load_default()
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_box = ImageFont.load_default()

    margin_left = 80
    
    # Vẽ Số
    draw.text((margin_left, 150), str(index), font=font_big, fill=TEXT_CYAN)
    
    # Vẽ Tiêu đề (Ngang hàng với số)
    draw_wrapped_text(draw, title.upper(), font_title, TEXT_WHITE, 400, 200, 600)
    
    # Đường kẻ phân cách
    draw.line([(margin_left, 550), (W - margin_left, 550)], fill="#334E68", width=3)
    
    # Vẽ Nội dung chính
    next_y = draw_wrapped_text(draw, content, font_body, TEXT_WHITE, margin_left, 600, W - 2*margin_left, line_spacing=20)

    # Vẽ Hộp thông tin (Footer)
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

# ==============================================================================
# 5. CHỨC NĂNG TRÍ TUỆ NHÂN TẠO (GEMINI)
# ==============================================================================
def generate_content(input_text, is_link=False):
    context_prompt = f"Bài báo có nội dung: '{input_text}'" if is_link else f"Chủ đề: '{input_text}'"
    
    prompt = f"""
    Bạn là Chuyên gia Marketing Bất Động Sản Khánh Hòa.
    {context_prompt}
    
    Nhiệm vụ: Phân tích và viết nội dung Slide Facebook.
    Nếu thông tin quá ngắn, HÃY TỰ SÁNG TẠO thêm dựa trên kiến thức chuyên gia của bạn để đủ 3 ý.
    
    Yêu cầu Output JSON (Bắt buộc đúng định dạng):
    {{
        "title_text": "Tiêu đề ngắn gọn, giật gân, viết hoa (để làm ảnh bìa)",
        "slides": [
            {{ "title": "TIÊU ĐỀ Ý 1", "content": "Nội dung ý 1 ngắn gọn (tối đa 40 từ)." }},
            {{ "title": "TIÊU ĐỀ Ý 2", "content": "Nội dung ý 2 ngắn gọn..." }},
            {{ "title": "TIÊU ĐỀ Ý 3", "content": "Nội dung ý 3 ngắn gọn..." }}
        ],
        "caption": "Caption Facebook hấp dẫn, chuyên nghiệp, có hashtag."
    }}
    """
    try:
        response = model.generate_content(prompt)
        raw_text = response.text
        
        # --- XỬ LÝ LỖI JSON (QUAN TRỌNG) ---
        # Tìm và cắt đúng đoạn JSON, bỏ qua các lời dẫn của AI
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}') + 1
        
        if start_idx != -1 and end_idx != -1:
            clean_json = raw_text[start_idx:end_idx]
            return json.loads(clean_json)
        else:
            print(f"Lỗi format AI: {raw_text}")
            return None
            
    except Exception as e:
        print(f"Lỗi AI System: {e}") 
        return None

# ==============================================================================
# 6. XỬ LÝ TIN NHẮN ĐẾN
# ==============================================================================
def handle_message(update: Update, context: CallbackContext):
    user_input = update.message.text
    chat_id = update.message.chat_id
    
    # Kiểm tra xem có phải Link báo không?
    is_link = False
    content_to_process = user_input
    
    if "http" in user_input:
        update.message.reply_text("🔗 Phát hiện Link báo. Đang đọc nội dung...")
        article_content = get_article_content(user_input)
        if article_content:
            content_to_process = article_content
            is_link = True
            update.message.reply_text("✅ Đã đọc xong. Đang phân tích & vẽ ảnh...")
        else:
            update.message.reply_text("⚠️ Không đọc được link này (bị chặn). Bot sẽ chém gió dựa trên URL nhé.")
    else:
        update.message.reply_text(f"🧠 Đang suy nghĩ về: '{user_input}'...")

    # Gọi AI
    data = generate_content(content_to_process, is_link)
    
    if not data:
        update.message.reply_text("❌ AI đang bận hoặc lỗi dữ liệu. Thử lại sau.")
        return

    # Gửi kết quả
    update.message.reply_text(f"🎯 **TITLE BÌA:**\n`{data['title_text']}`", parse_mode=ParseMode.MARKDOWN)
    
    album = []
    for i, slide in enumerate(data['slides'], 1):
        img_bio = create_modern_slide(slide['title'], slide['content'], index=i)
        # Gắn caption vào ảnh đầu tiên
        if i == 1:
            album.append(InputMediaPhoto(media=img_bio, caption=data['caption']))
        else:
            album.append(InputMediaPhoto(media=img_bio))

    try:
        context.bot.send_media_group(chat_id=chat_id, media=album)
        update.message.reply_text("✅ Xong! Forward sang Bot Đăng Bài nhé.")
    except Exception as e:
        update.message.reply_text(f"❌ Lỗi gửi ảnh: {e}")

# ==============================================================================
# 7. CHẠY BOT
# ==============================================================================
if __name__ == '__main__':
    # Chạy Web Server
    threading.Thread(target=run_web_server).start()
    
    # Chạy Bot
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    # Chạy Radar săn tin
    spy_thread = threading.Thread(target=check_news_updates, args=(updater,))
    spy_thread.start()
    
    print("Bot Content Ultimate Ready...")
    updater.start_polling()
    updater.idle()
