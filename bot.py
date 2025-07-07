from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import aiohttp
import asyncio
import hashlib
import time
import re
import socket
from urllib.parse import urlparse, parse_qs, unquote
import requests

BOT_TOKEN = "7754314760:AAGQo3ieE17vOibQUqcKmgTxIxuVYbYLKmw"
APP_KEY = "509038"
APP_SECRET = "gbDEssB1M3LYH8abuIQB57sQDrO47hln"
TRACKING_ID = "default"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Connection": "keep-alive"
}

async def retry(func, retries=2, delay=3, *args, **kwargs):
    for attempt in range(retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            print(f"[debug] محاولة {attempt + 1} فشلت: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
    return None

async def generate_affiliate_link(url, session):
    async def inner():
        timestamp = str(int(time.time() * 1000))
        api_url = "https://api-sg.aliexpress.com/sync"
        params = {
            "app_key": APP_KEY,
            "method": "aliexpress.affiliate.link.generate",
            "timestamp": timestamp,
            "sign_method": "md5",
            "format": "json",
            "v": "1.0",
            "promotion_link_type": "2",
            "source_values": url,
            "tracking_id": TRACKING_ID
        }

        def generate_signature(params, secret):
            sorted_params = sorted(params.items())
            base_string = secret + ''.join(f"{k}{v}" for k, v in sorted_params) + secret
            return hashlib.md5(base_string.encode('utf-8')).hexdigest().upper()

        params["sign"] = generate_signature(params, APP_SECRET)

        async with session.get(api_url, params=params, timeout=5) as res:
            data = await res.json()
            return data["aliexpress_affiliate_link_generate_response"]["resp_result"]["result"]["promotion_links"]["promotion_link"][0]["promotion_link"]

    return await retry(inner)

async def get_title_from_item(product_id):
    async def inner():
        url = f"https://www.aliexpress.com/item/{product_id}.html"
        resolver = aiohttp.AsyncResolver(nameservers=["8.8.8.8", "1.1.1.1"])
        connector = aiohttp.TCPConnector(
            resolver=resolver, family=socket.AF_INET, limit=6, enable_cleanup_closed=True
        )
        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            async with session.get(url, timeout=5) as resp:
                print(f"[debug] title status: {resp.status}")
                html = await resp.text()
                match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
                if match:
                    return match.group(1)
        return "❌ ما قدرناش نجيبو عنوان المنتج."
    return await retry(inner)

async def get_image_from_item(product_id):
    async def inner():
        url = f"https://www.aliexpress.com/item/{product_id}.html"
        resolver = aiohttp.AsyncResolver(nameservers=["8.8.8.8", "1.1.1.1"])
        connector = aiohttp.TCPConnector(
            resolver=resolver, family=socket.AF_INET, limit=6, enable_cleanup_closed=True
        )
        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            async with session.get(url, timeout=5) as resp:
                print(f"[debug] image status: {resp.status}")
                html = await resp.text()
                match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                if match:
                    return match.group(1)
        return None
    return await retry(inner)

def resolve_real_url(short_url):
    try:
        session = requests.Session()
        response = session.get(short_url, allow_redirects=True, timeout=5)
        for r in response.history + [response]:
            if "BundleDeals" in r.url or "/ssr/" in r.url:
                return r.url
        qs = parse_qs(urlparse(response.url).query)
        if "redirectUrl" in qs:
            return unquote(qs["redirectUrl"][0])
        return response.url
    except:
        return None

def extract_product_id(url: str):
    try:
        match = re.search(r'/item/(\d+)\.html', url)
        if match:
            return match.group(1)
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "productIds" in qs:
            return qs["productIds"][0].split(",")[0]
        return None
    except:
        return None

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.startswith("http"):
        await update.message.reply_text("🔗 أرسل رابط من نوع AliExpress فقط.")
        return

    waiting_message = await update.message.reply_text("⏳ جاري معالجة الرابط...")

    real_url = resolve_real_url(text)
    if not real_url:
        await waiting_message.edit_text("❌ ما قدرناش نجيبو رابط حقيقي.")
        return

    product_id = extract_product_id(real_url)
    if not product_id:
        await waiting_message.edit_text("❌ ما قدرناش نستخرجو ID المنتج.")
        return

    connector = aiohttp.TCPConnector(
        resolver=aiohttp.AsyncResolver(nameservers=["8.8.8.8", "1.1.1.1"]),
        family=socket.AF_INET,
        limit=6,
        enable_cleanup_closed=True
    )

    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        title, image_url = await asyncio.gather(
            get_title_from_item(product_id),
            get_image_from_item(product_id)
        )

        urls = {
            "💸 رابط العملات المباشر": f"https://vi.aliexpress.com/item/{product_id}.html?sourceType=620&channel=coin",
            "💰 رابط العملات العامة": f"https://m.aliexpress.com/p/coin-index/index.html?productIds={product_id}",
            "🌐 رابط الباندل": f"https://www.aliexpress.com/ssr/300000512/BundleDeals2?productIds={product_id}",
            "🔥 رابط Super Deals": f"https://vi.aliexpress.com/item/{product_id}.html?sourceType=562",
            "🧨 رابط Big Save": f"https://vi.aliexpress.com/item/{product_id}.html?sourceType=680",
            "⚡ رابط العرض المحدود": f"https://vi.aliexpress.com/item/{product_id}.html?sourceType=561"
        }

        tasks = [generate_affiliate_link(u, session) for u in urls.values()]
        results = await asyncio.gather(*tasks)
        links = dict(zip(urls.keys(), results))

    caption = f"🏷️ {title}\n\n"
    for label, link in links.items():
        if link and len(caption + f"{label}:\n{link}\n\n") < 1000:
            caption += f"{label}:\n{link}\n\n"

    await waiting_message.delete()
    if image_url:
        await update.message.reply_photo(image_url, caption=caption[:1024])
    else:
        await update.message.reply_text(caption.strip())

# 🚀 تشغيل البوت
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
print("✅ البوت شغال مع retry واستقرار جيد")
app.run_polling()