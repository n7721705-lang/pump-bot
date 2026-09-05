import asyncio
import time
import json
from datetime import datetime, timezone, timedelta
from telegram import Bot
import aiohttp
import websockets

# ==================== НАЛАШТУВАННЯ ====================
TELEGRAM_BOT_TOKEN = "8686768235:AAEphYxwBp36WM8kkhgjm4akOhtrkJNp_vw"
TELEGRAM_CHAT_ID = -1004438401967
PUMP_THRESHOLD = 2.0      # 2% зміни
TIME_WINDOW = 30           # за 30 секунд
MIN_PRICE = 0.001
# =====================================================

KYIV_TZ = timezone(timedelta(hours=3))

bot = Bot(token=TELEGRAM_BOT_TOKEN)
prices = {}
alerted = set()
all_symbols = []

def get_kyiv_time():
    return datetime.now(KYIV_TZ).strftime('%H:%M:%S')

async def send_alert(symbol, change, price, alert_type):
    emoji = "🟢" if alert_type == "PUMP" else "🔴"
    title = "PUMP" if alert_type == "PUMP" else "DUMP"
    message = (
        f"{emoji} *{title}*\n"
        f"📊 *Монета:* `{symbol}`\n"
        f"📈 *Зміна:* {change:.2f}%\n"
        f"💰 *Ціна:* {price} USDT\n"
        f"🕐 *Час:* {get_kyiv_time()}"
    )
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
        print(f"[✓] СИГНАЛ: {symbol} {alert_type} {change:.2f}%")
    except Exception as e:
        print(f"[✗] Помилка: {e}")

async def get_all_symbols_mexc():
    """Отримує ВСІ ф'ючерсні USDT-монети з MEXC через правильний API"""
    async with aiohttp.ClientSession() as session:
        try:
            # ВИПРАВЛЕНО: правильна URL для MEXC Futures
            url = "https://futures.mexc.com/api/v1/contract/detail?type=all"
            print(f"📡 Запит до: {url}")
            
            async with session.get(url, timeout=15) as resp:
                data = await resp.json()
                print(f"📨 Код відповіді: {data.get('code')}")
                
                if data.get('code') == 200:
                    symbols = []
                    for item in data.get('data', []):
                        symbol = item.get('symbol', '')
                        if symbol.endswith('USDT'):
                            symbols.append(symbol)
                    return symbols
                else:
                    print(f"❌ Помилка: {data}")
                    return []
        except Exception as e:
            print(f"❌ Помилка запиту: {e}")
            return []

async def process_price(symbol, price):
    global prices, alerted
    if not symbol or price < MIN_PRICE:
        return
    current_time = time.time()
    if symbol not in prices:
        prices[symbol] = []
    prices[symbol].append((current_time, price))
    cutoff = current_time - TIME_WINDOW
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
    print("PUMP/DUMP MONITOR - MEXC FUTURES (ВСІ МОНЕТИ)")
    print("=" * 50)
    print(f"📊 Поріг: {PUMP_THRESHOLD}% за {TIME_WINDOW}с")
    print("🔄 WebSocket + REST API")
    print(f"🕐 Часовий пояс: Київ")
    print("=" * 50)
    
    print("📡 Отримую список всіх монет MEXC...")
    all_symbols = await get_all_symbols_mexc()
    
    if not all_symbols:
        print("❌ НЕ ВДАЛОСЯ ОТРИМАТИ СПИСОК МОНЕТ!")
        print("🔄 Перевіряємо альтернативний ендпоінт...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://contract.mexc.com/api/v1/contract/detail",
                    timeout=15
                ) as resp:
                    data = await resp.json()
                    if data.get('code') == 200:
                        all_symbols = [item['symbol'] for item in data.get('data', []) 
                                      if item['symbol'].endswith('USDT')]
        except Exception as e:
            print(f"❌ Альтернатива не спрацювала: {e}")
    
    print(f"✅ ЗНАЙДЕНО {len(all_symbols)} ф'ючерсних USDT-монет")
    
    if not all_symbols:
        print("❌ Немає монет для моніторингу.")
        return
    
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"✅ *Бот запущено!*\n📊 Моніторинг {len(all_symbols)} монет (MEXC)\n📈 Поріг: {PUMP_THRESHOLD}% за {TIME_WINDOW}с\n🕐 Київ: {get_kyiv_time()}",
            parse_mode="Markdown"
        )
        print("✅ Тестове повідомлення надіслано!")
    except Exception as e:
        print(f"⚠️ Помилка відправки: {e}")
    
    # MEXC WebSocket
    uri = "wss://contract.mexc.com/edge"
    subscription_msg = {"method": "SUBSCRIPTION", "params": ["tickers"], "id": 1}
    
    print("🔄 Підключення до WebSocket MEXC...")
    
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                await ws.send(json.dumps(subscription_msg))
                response = await ws.recv()
                print(f"📨 Відповідь WebSocket: {response[:200]}...")
                print(f"✅ Підключено! Отримую дані з {len(all_symbols)} монет...")
                
                while True:
                    try:
                        response = await ws.recv()
                        data = json.loads(response)
                        if data.get('channel') == 'tickers':
                            tickers = data.get('data', [])
                            if not isinstance(tickers, list):
                                tickers = [tickers]
                            for ticker in tickers:
                                symbol = ticker.get('symbol')
                                price = float(ticker.get('lastPrice', 0))
                                if symbol and price > 0:
                                    await process_price(symbol, price)
                    except websockets.exceptions.ConnectionClosed:
                        print("⚠️ З'єднання втрачено, перепідключення...")
                        break
        except Exception as e:
            print(f"❌ Помилка WebSocket: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
