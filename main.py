import asyncio
import time
from datetime import datetime, timezone, timedelta
from telegram import Bot
import aiohttp

# ==================== НАЛАШТУВАННЯ ====================
TELEGRAM_BOT_TOKEN = "8818473462:AAG02pUpdJn0FsBzJabEVdOW7-UrFmMbx4w"
TELEGRAM_CHAT_ID = -1003933274705

PUMP_THRESHOLD = 2.0             # Мінімальний рух (%)
MIN_MOVE_TIME = 1                # Мінімальний час руху (сек)
MAX_MOVE_TIME = 20               # Максимальний час руху (сек)
CHECK_INTERVAL = 5               # Перевірка кожні 5 секунд
MIN_PRICE = 0.001
# =====================================================

KYIV_TZ = timezone(timedelta(hours=3))

bot = Bot(token=TELEGRAM_BOT_TOKEN)
prices = {}
alerted = set()

def get_kyiv_time():
    return datetime.now(KYIV_TZ).strftime('%H:%M:%S')

def format_price(price):
    if price >= 1:
        return f"{price:.4f}"
    elif price >= 0.01:
        return f"{price:.6f}"
    else:
        return f"{price:.8f}"

async def get_all_prices_binance():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                "https://fapi.binance.com/fapi/v1/ticker/24hr",
                timeout=15
            ) as resp:
                data = await resp.json()
                return data
        except Exception as e:
            print(f"❌ Помилка: {e}")
            return []

async def send_alert(symbol, change, price, alert_type, elapsed, start_price):
    emoji = "🟢" if alert_type == "PUMP" else "🔴"
    action = "прибавила" if alert_type == "PUMP" else "упала"
    change_text = f"+{change:.2f}%" if change > 0 else f"{change:.2f}%"
    coin_name = symbol.replace('USDT', '')
    
    if elapsed < 60:
        time_str = f"{int(elapsed)} сек."
    else:
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        time_str = f"{minutes} мин. {seconds} сек."
    
    message = (
        f"{emoji} *{symbol}* ({coin_name}) {action} на *{change_text}%* за последние {time_str}\n"
        f"💰 Цена: {format_price(start_price)} → {format_price(price)} USDT\n"
        f"🕐 *Час:* {get_kyiv_time()}"
    )
    
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
        print(f"[✓] СИГНАЛ: {symbol} {alert_type} {change:.2f}% за {time_str}")
    except Exception as e:
        print(f"[✗] Помилка: {e}")

async def check_pumps():
    global prices, alerted
    
    current_time = time.time()
    
    tickers = await get_all_prices_binance()
    if not tickers:
        print("⚠️ Не вдалося отримати ціни")
        return
    
    for item in tickers:
        symbol = item.get('symbol', '')
        if not symbol.endswith('USDT'):
            continue
        
        price = float(item.get('lastPrice', 0))
        if price < MIN_PRICE:
            continue
        
        if symbol not in prices:
            prices[symbol] = {
                'first_price': price,
                'first_time': current_time,
                'alerted': False,
                'last_alert_time': 0
            }
            continue
        
        data = prices[symbol]
        first_price = data['first_price']
        first_time = data['first_time']
        elapsed = current_time - first_time
        change = ((price - first_price) / first_price) * 100
        
        time_since_last_alert = current_time - data['last_alert_time']
        
        # Перевіряємо умови для сигналу
        # 1. Зміна ≥ порогу
        # 2. Час руху від 1 до 20 секунд
        # 3. Ще не було сигналу для цього руху
        if abs(change) >= PUMP_THRESHOLD and not data['alerted']:
            if MIN_MOVE_TIME <= elapsed <= MAX_MOVE_TIME:
                if time_since_last_alert >= 5:
                    data['alerted'] = True
                    data['last_alert_time'] = current_time
                    print(f"🔥 ЗНАЙДЕНО! {symbol} зміна {change:.2f}% за {elapsed:.1f}с")
                    await send_alert(
                        symbol, change, price,
                        "PUMP" if change > 0 else "DUMP",
                        elapsed,
                        first_price
                    )
        
        # Скидаємо якщо минуло більше MAX_MOVE_TIME або зміна стала маленькою
        if elapsed > MAX_MOVE_TIME or abs(change) < 0.3:
            if elapsed > MAX_MOVE_TIME:
                prices[symbol] = {
                    'first_price': price,
                    'first_time': current_time,
                    'alerted': False,
                    'last_alert_time': data['last_alert_time']
                }
                print(f"🔄 Скидання {symbol}: новий рух від {price}")

async def main():
    print("=" * 50)
    print("🚀 PUMP/DAMP BOT")
    print("=" * 50)
    print(f"📊 Поріг: {PUMP_THRESHOLD}%")
    print(f"⏱ Час руху: {MIN_MOVE_TIME}–{MAX_MOVE_TIME}с")
    print(f"🔄 Перевірка кожні {CHECK_INTERVAL}с")
    print("=" * 50)
    
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"✅ *PUMP/DAMP BOT запущено!*\n"
                 f"📊 Поріг: {PUMP_THRESHOLD}%\n"
                 f"⏱ Час руху: {MIN_MOVE_TIME}–{MAX_MOVE_TIME}с\n"
                 f"🕐 Київ: {get_kyiv_time()}",
            parse_mode="Markdown"
        )
        print("✅ Бот запущено!")
    except Exception as e:
        print(f"⚠️ Помилка: {e}")
    
    while True:
        try:
            await check_pumps()
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"❌ Помилка в циклі: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
