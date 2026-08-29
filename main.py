import asyncio
import json
import time
from datetime import datetime
import websockets
from telegram import Bot

# ==================== НАЛАШТУВАННЯ ====================
TELEGRAM_BOT_TOKEN = "8686768235:AAEphYxwBp36WM8kkhgjm4akOhtrkJNp_vw"
TELEGRAM_CHAT_ID = -1004438401967
PUMP_THRESHOLD = 2.0      # ЗМІНЕНО: 2% замість 3%
TIME_WINDOW = 30          # ЗМІНЕНО: 30 секунд замість 60
MIN_PRICE = 0.01
# =====================================================

bot = Bot(token=TELEGRAM_BOT_TOKEN)
prices = {}
alerted = set()

async def send_alert(symbol, change, price, alert_type):
    emoji = "🚀" if alert_type == "PUMP" else "💀"
    message = (
        f"{emoji} *{alert_type} DETECTED!*\n"
        f"📊 *Монета:* `{symbol}`\n"
        f"📈 *Зміна:* {change:.2f}%\n"
        f"💰 *Ціна:* {price} USDT\n"
        f"🕐 *Час:* {datetime.now().strftime('%H:%M:%S')}\n"
        f"⚡ *Вікно:* {TIME_WINDOW}с"
    )
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
        print(f"[✓] СИГНАЛ: {symbol} {alert_type} {change:.2f}%")
    except Exception as e:
        print(f"[✗] Помилка відправки: {e}")

async def process_price(data):
    global prices, alerted
    symbol = data.get('s')
    price = float(data.get('c', 0))
    
    if not symbol or price < MIN_PRICE:
        return
    
    # Логуємо кожну 100-ту монету, щоб бачити, що бот працює
    if len(prices) % 100 == 0 and len(prices) > 0:
        print(f"📊 Оброблено монет: {len(prices)}, поточна: {symbol} {price}")
    
    if symbol not in prices:
        prices[symbol] = []
    
    prices[symbol].append((time.time(), price))
    
    # Видаляємо старі дані
    cutoff = time.time() - TIME_WINDOW
    prices[symbol] = [(t, p) for t, p in prices[symbol] if t >= cutoff]
    
    if len(prices[symbol]) >= 2:
        first_time, first_price = prices[symbol][0]
        last_time, last_price = prices[symbol][-1]
        
        if first_price > 0:
            change = ((last_price - first_price) / first_price) * 100
            
            if abs(change) >= PUMP_THRESHOLD:
                key = f"{symbol}_{int(first_time)}"
                if key not in alerted:
                    alerted.add(key)
                    print(f"🔥 ЗНАЙДЕНО! {symbol} зміна {change:.2f}%")
                    await send_alert(symbol, change, last_price, "PUMP" if change > 0 else "DUMP")

async def main():
    print("=" * 50)
    print("PUMP/DUMP MONITOR - BINANCE FUTURES")
    print("=" * 50)
    print(f"📊 Поріг: {PUMP_THRESHOLD}% за {TIME_WINDOW}с")
    print(f"📨 Чат ID: {TELEGRAM_CHAT_ID}")
    print("=" * 50)
    print("🔄 Очікування сигналів...")

    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ *Бот запущено!*\n📊 Поріг: {PUMP_THRESHOLD}% за {TIME_WINDOW}с", parse_mode="Markdown")
        print("✅ Тестове повідомлення надіслано!")
    except Exception as e:
        print(f"⚠️ Помилка відправки: {e}")

    uri = "wss://fstream.binance.com/ws/!miniTicker@arr"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                print("✅ Підключено до Binance WebSocket")
                print("⏳ Очікую на зміни цін...")
                while True:
                    try:
                        data = json.loads(await ws.recv())
                        if isinstance(data, list):
                            for item in data:
                                await process_price(item)
                        else:
                            await process_price(data)
                    except websockets.exceptions.ConnectionClosed:
                        print("⚠️ З'єднання втрачено, перепідключення...")
                        break
        except Exception as e:
            print(f"❌ Помилка: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
