import asyncio
import json
import time
from datetime import datetime
import websockets
from telegram import Bot

# ==================== НАЛАШТУВАННЯ ====================
TELEGRAM_BOT_TOKEN = "8686768235:AAEphYxwBp36WM8kkhgjm4akOhtrkJNp_vw"
TELEGRAM_CHAT_ID = -1004438401967
PUMP_THRESHOLD = 1.0      # ЗМІНЕНО: 1% замість 2%
TIME_WINDOW = 30           # секунд для аналізу
MIN_PRICE = 0.001
# =====================================================

bot = Bot(token=TELEGRAM_BOT_TOKEN)
prices = {}
alerted = set()
all_symbols = []

async def send_alert(symbol, change, price, alert_type):
    emoji = "🚀" if alert_type == "PUMP" else "💀"
    message = (
        f"{emoji} *{alert_type} DETECTED!*\n"
        f"📊 *Монета:* `{symbol}`\n"
        f"📈 *Зміна:* {change:.2f}%\n"
        f"💰 *Ціна:* {price} USDT\n"
        f"🕐 *Час:* {datetime.now().strftime('%H:%M:%S')}"
    )
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
        print(f"[✓] СИГНАЛ: {symbol} {alert_type} {change:.2f}%")
    except Exception as e:
        print(f"[✗] Помилка відправки: {e}")

async def process_price(symbol, price):
    global prices, alerted
    
    if not symbol or price < MIN_PRICE:
        return
    
    if symbol not in prices:
        prices[symbol] = []
    
    prices[symbol].append((time.time(), price))
    
    cutoff = time.time() - TIME_WINDOW
    prices[symbol] = [(t, p) for t, p in prices[symbol] if t >= cutoff]
    
    if len(prices[symbol]) >= 2:
        first_price = prices[symbol][0][1]
        last_price = prices[symbol][-1][1]
        
        if first_price > 0:
            change = ((last_price - first_price) / first_price) * 100
            
            if abs(change) >= PUMP_THRESHOLD:
                key = f"{symbol}_{int(prices[symbol][0][0])}"
                if key not in alerted:
                    alerted.add(key)
                    print(f"🔥 ЗНАЙДЕНО! {symbol} зміна {change:.2f}%")
                    await send_alert(symbol, change, last_price, "PUMP" if change > 0 else "DUMP")

async def main():
    global all_symbols
    
    print("=" * 50)
    print("PUMP/DUMP MONITOR - BYBIT FUTURES")
    print("=" * 50)
    print(f"📊 Поріг: {PUMP_THRESHOLD}% за {TIME_WINDOW}с")
    print("=" * 50)
    
    # Тестове повідомлення
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"✅ *Бот запущено!*\n📈 Поріг: {PUMP_THRESHOLD}% за {TIME_WINDOW}с",
            parse_mode="Markdown"
        )
        print("✅ Тестове повідомлення надіслано!")
    except Exception as e:
        print(f"⚠️ Помилка відправки: {e}")
    
    # Отримуємо початкові ціни
    print("📡 Отримую початкові ціни...")
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.bybit.com/v5/market/tickers?category=linear") as resp:
            data = await resp.json()
            if data['retCode'] == 0:
                for item in data['result']['list']:
                    symbol = item['symbol']
                    price = float(item['lastPrice'])
                    if symbol.endswith('USDT') and price > MIN_PRICE:
                        prices[symbol] = [(time.time(), price)]
                print(f"✅ Завантажено {len(prices)} монет")
    
    # Bybit WebSocket
    uri = "wss://stream.bybit.com/v5/public/linear"
    subscription_msg = {"op": "subscribe", "args": ["tickers"]}
    
    print("🔄 Підключення до Bybit WebSocket...")
    
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                await ws.send(json.dumps(subscription_msg))
                print("✅ Підключено до Bybit! Очікую сигнали...")
                
                while True:
                    try:
                        response = json.loads(await ws.recv())
                        if 'topic' in response and response['topic'] == 'tickers':
                            for data in response['data']:
                                symbol = data['symbol']
                                price = float(data['lastPrice'])
                                await process_price(symbol, price)
                    except websockets.exceptions.ConnectionClosed:
                        print("⚠️ Перепідключення...")
                        break
        except Exception as e:
            print(f"❌ Помилка: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
