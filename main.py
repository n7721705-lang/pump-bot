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
CHECK_INTERVAL = 5         # перевірка через WebSocket (реальний час)
MIN_PRICE = 0.001
# =====================================================

# Часовий пояс Київ (UTC+3)
KYIV_TZ = timezone(timedelta(hours=3))

bot = Bot(token=TELEGRAM_BOT_TOKEN)
prices = {}
alerted = set()
all_symbols = []

def get_kyiv_time():
    """Повертає поточний час у Києві"""
    return datetime.now(KYIV_TZ).strftime('%H:%M:%S')

async def send_alert(symbol, change, price, alert_type):
    if alert_type == "PUMP":
        emoji = "🟢"
        title = "PUMP"
    else:
        emoji = "🔴"
        title = "DUMP"
    
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
    """Отримує ВСІ ф'ючерсні USDT-монети з MEXC"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                "https://api.mexc.com/api/v1/contract/detail",
                timeout=15
            ) as resp:
                data = await resp.json()
                if data.get('code') == 200:
                    symbols = [item['symbol'] for item in data['data'] 
                              if item['symbol'].endswith('USDT')]
                    return symbols
                else:
                    print(f"❌ Помилка API MEXC: {data}")
                    return []
        except Exception as e:
            print(f"❌ Помилка запиту: {e}")
            return []

async def process_price(symbol, price):
    """Обробляє ціну монети та перевіряє на памп/дамп"""
    global prices, alerted
    
    if not symbol or price < MIN_PRICE:
        return
    
    current_time = time.time()
    
    # Ініціалізуємо історію для нових монет
    if symbol not in prices:
        prices[symbol] = []
    
    # Додаємо поточну ціну
    prices[symbol].append((current_time, price))
    
    # Видаляємо старі записи (старше TIME_WINDOW)
    cutoff = current_time - TIME_WINDOW
    prices[symbol] = [(t, p) for t, p in prices[symbol] if t >= cutoff]
    
    # Перевіряємо зміну
    if len(prices[symbol]) >= 2:
        first_price = prices[symbol][0][1]
        last_price = prices[symbol][-1][1]
        
        if first_price > 0:
            change = ((last_price - first_price) / first_price) * 100
            
            if abs(change) >= PUMP_THRESHOLD:
                key = f"{symbol}_{int(prices[symbol][0][0])}"
                if key not in alerted:
                    alerted.add(key)
                    print(f"🔥 ЗНАЙДЕНО! {symbol} зміна {change:.2f}% (ціна: {last_price})")
                    await send_alert(symbol, change, last_price, "PUMP" if change > 0 else "DUMP")

async def main():
    global all_symbols
    
    print("=" * 50)
    print("PUMP/DUMP MONITOR - MEXC FUTURES (ВСІ МОНЕТИ)")
    print("=" * 50)
    print(f"📊 Поріг: {PUMP_THRESHOLD}% за {TIME_WINDOW}с")
    print(f"🔄 WebSocket (реальний час)")
    print(f"🕐 Часовий пояс: Київ")
    print("=" * 50)
    
    # Отримуємо список всіх монет
    print("📡 Отримую список всіх монет MEXC...")
    all_symbols = await get_all_symbols_mexc()
    print(f"✅ ЗНАЙДЕНО {len(all_symbols)} ф'ючерсних USDT-монет")
    
    # Тестове повідомлення
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
    
    # Формуємо список символів для підписки (всі монети)
    # MEXC вимагає підписку на кожну монету окремо через метод SUBSCRIPTION
    # Але простіше використовувати канал tickers:всі символи
    subscription_msg = {
        "method": "SUBSCRIPTION",
        "params": [
            f"tickers"  # Підписка на всі тікери
        ],
        "id": 1
    }
    
    print("🔄 Підключення до WebSocket MEXC...")
    
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                # Відправляємо підписку
                await ws.send(json.dumps(subscription_msg))
                print(f"✅ Підключено до MEXC! Отримую дані з {len(all_symbols)} монет...")
                
                # Отримуємо підтвердження підписки
                response = await ws.recv()
                print(f"📨 Відповідь MEXC: {response}")
                
                print("⏳ Очікую сигнали...")
                
                while True:
                    try:
                        response = await ws.recv()
                        data = json.loads(response)
                        
                        # Перевіряємо, чи це дані про ціни
                        if 'channel' in data and data['channel'] == 'tickers':
                            if 'data' in data and data['data']:
                                # MEXC повертає або один об'єкт, або масив
                                tickers = data['data']
                                if not isinstance(tickers, list):
                                    tickers = [tickers]
                                
                                for ticker in tickers:
                                    symbol = ticker.get('symbol')
                                    price = float(ticker.get('lastPrice', 0))
                                    await process_price(symbol, price)
                        
                        # Періодично виводимо кількість монет у пам'яті
                        if len(prices) > 0 and int(time.time()) % 30 == 0:
                            print(f"📊 Відстежується {len(prices)} монет")
                            
                    except websockets.exceptions.ConnectionClosed:
                        print("⚠️ З'єднання втрачено, перепідключення...")
                        break
                    except json.JSONDecodeError as e:
                        print(f"⚠️ Помилка JSON: {e}")
                        continue
        except Exception as e:
            print(f"❌ Помилка WebSocket: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
