import asyncio
import time
from datetime import datetime
from telegram import Bot
import aiohttp

# ==================== НАЛАШТУВАННЯ ====================
TELEGRAM_BOT_TOKEN = "8686768235:AAEphYxwBp36WM8kkhgjm4akOhtrkJNp_vw"
TELEGRAM_CHAT_ID = -1004438401967
PUMP_THRESHOLD = 2.0      # 2% зміни
TIME_WINDOW = 30           # за 30 секунд
CHECK_INTERVAL = 10        # перевірка кожні 10 секунд
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
        print(f"[✗] Помилка: {e}")

async def get_all_symbols():
    """Отримує ВСІ ф'ючерсні USDT-монети з Bybit"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                "https://api.bybit.com/v5/market/tickers?category=linear",
                timeout=15
            ) as resp:
                data = await resp.json()
                if data.get('retCode') == 0:
                    symbols = [item['symbol'] for item in data['result']['list'] 
                              if item['symbol'].endswith('USDT')]
                    return symbols
                else:
                    print(f"❌ Помилка API: {data}")
                    return []
        except Exception as e:
            print(f"❌ Помилка запиту: {e}")
            return []

async def get_all_prices():
    """Отримує ціни ВСІХ монет з Bybit"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                "https://api.bybit.com/v5/market/tickers?category=linear",
                timeout=15
            ) as resp:
                data = await resp.json()
                if data.get('retCode') == 0:
                    return data['result']['list']
                else:
                    print(f"❌ Помилка API: {data}")
                    return []
        except Exception as e:
            print(f"❌ Помилка запиту: {e}")
            return []

async def check_pumps():
    global prices, alerted, all_symbols
    
    current_time = time.time()
    
    # Отримуємо всі ціни
    tickers = await get_all_prices()
    if not tickers:
        print("⚠️ Не вдалося отримати ціни")
        return
    
    # Оновлюємо список символів (якщо змінився)
    if not all_symbols:
        all_symbols = [item['symbol'] for item in tickers if item['symbol'].endswith('USDT')]
        print(f"📊 ВСЬОГО МОНЕТ: {len(all_symbols)}")
    
    new_prices = {}
    checked = 0
    
    for item in tickers:
        symbol = item['symbol']
        if not symbol.endswith('USDT'):
            continue
            
        price = float(item['lastPrice'])
        if price < MIN_PRICE:
            continue
            
        checked += 1
        new_prices[symbol] = price
        
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
    
    print(f"✅ Перевірено {checked} монет з {len(all_symbols)}")

async def main():
    global all_symbols
    
    print("=" * 50)
    print("PUMP/DUMP MONITOR - BYBIT (ВСІ МОНЕТИ)")
    print("=" * 50)
    print(f"📊 Поріг: {PUMP_THRESHOLD}% за {TIME_WINDOW}с")
    print(f"🔄 Перевірка кожні {CHECK_INTERVAL}с")
    print("=" * 50)
    
    # Отримуємо список всіх монет
    print("📡 Отримую список всіх монет...")
    all_symbols = await get_all_symbols()
    print(f"✅ ЗНАЙДЕНО {len(all_symbols)} ф'ючерсних USDT-монет")
    
    # Тестове повідомлення
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"✅ *Бот запущено!*\n📊 Моніторинг {len(all_symbols)} монет\n📈 Поріг: {PUMP_THRESHOLD}% за {TIME_WINDOW}с",
            parse_mode="Markdown"
        )
        print("✅ Тестове повідомлення надіслано!")
    except Exception as e:
        print(f"⚠️ Помилка відправки: {e}")
    
    # Основний цикл
    while True:
        try:
            await check_pumps()
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"❌ Помилка в циклі: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
