import asyncio
import time
from datetime import datetime, timezone, timedelta
from telegram import Bot
import aiohttp

# ==================== НАЛАШТУВАННЯ ====================
TELEGRAM_BOT_TOKEN = "8686768235:AAEphYxwBp36WM8kkhgjm4akOhtrkJNp_vw"
TELEGRAM_CHAT_ID = -1004438401967
PUMP_THRESHOLD = 2.0      # 2% зміни
MIN_PRICE = 0.001
CHECK_INTERVAL = 10        # перевірка кожні 10 секунд
# =====================================================

KYIV_TZ = timezone(timedelta(hours=3))

bot = Bot(token=TELEGRAM_BOT_TOKEN)
prices = {}          # зберігаємо {symbol: (first_price, first_time)}
alerted = set()      # запобігаємо повторним сигналам
all_symbols = []

def get_kyiv_time():
    return datetime.now(KYIV_TZ).strftime('%H:%M:%S')

async def send_alert(symbol, change, price, alert_type):
    emoji = "🟢" if alert_type == "PUMP" else "🔴"
    title = "PUMP" if alert_type == "PUMP" else "DUMP"
    # Розраховуємо час, який минув від першої фіксації
    first_time = prices.get(symbol, (None, None))[1]
    time_diff = ""
    if first_time:
        seconds = int(time.time() - first_time)
        minutes = seconds // 60
        seconds = seconds % 60
        if minutes > 0:
            time_diff = f" (за {minutes}хв {seconds}с)"
        else:
            time_diff = f" (за {seconds}с)"
    
    message = (
        f"{emoji} *{title}*\n"
        f"📊 *Монета:* `{symbol}`\n"
        f"📈 *Зміна:* {change:.2f}%{time_diff}\n"
        f"💰 *Ціна:* {price} USDT\n"
        f"🕐 *Час:* {get_kyiv_time()}"
    )
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
        print(f"[✓] СИГНАЛ: {symbol} {alert_type} {change:.2f}% {time_diff}")
    except Exception as e:
        print(f"[✗] Помилка: {e}")

async def get_all_symbols_binance():
    """Отримує ВСІ ф'ючерсні USDT-монети з Binance"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                "https://fapi.binance.com/fapi/v1/exchangeInfo",
                timeout=15
            ) as resp:
                data = await resp.json()
                symbols = []
                for item in data.get('symbols', []):
                    symbol = item.get('symbol', '')
                    if symbol.endswith('USDT') and item.get('status') == 'TRADING':
                        symbols.append(symbol)
                return symbols
        except Exception as e:
            print(f"❌ Помилка: {e}")
            return []

async def get_all_prices_binance():
    """Отримує ціни ВСІХ монет з Binance Futures"""
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

async def check_pumps():
    global prices, alerted, all_symbols
    
    current_time = time.time()
    
    # Отримуємо всі ціни
    tickers = await get_all_prices_binance()
    if not tickers:
        print("⚠️ Не вдалося отримати ціни")
        return
    
    # Оновлюємо список монет (якщо ще не отримали)
    if not all_symbols:
        all_symbols = [item['symbol'] for item in tickers if item['symbol'].endswith('USDT')]
        print(f"📊 ВСЬОГО МОНЕТ НА BINANCE: {len(all_symbols)}")
        
        try:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=f"✅ *Бот запущено на Binance!*\n📊 Моніторинг {len(all_symbols)} монет\n📈 Поріг: {PUMP_THRESHOLD}%\n🔄 Перевірка кожні {CHECK_INTERVAL}с\n🕐 Київ: {get_kyiv_time()}",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"⚠️ Помилка відправки: {e}")
    
    checked = 0
    
    for item in tickers:
        symbol = item.get('symbol', '')
        if not symbol.endswith('USDT'):
            continue
        
        price = float(item.get('lastPrice', 0))
        if price < MIN_PRICE:
            continue
        
        checked += 1
        
        # Якщо монета нова — фіксуємо початкову ціну
        if symbol not in prices:
            prices[symbol] = (price, current_time)
            continue
        
        # Отримуємо початкову ціну та час
        first_price, first_time = prices[symbol]
        
        if first_price > 0:
            change = ((price - first_price) / first_price) * 100
            
            # Якщо зміна ≥ порогу і ще не було сигналу
            if abs(change) >= PUMP_THRESHOLD:
                key = f"{symbol}_{int(first_time)}"
                if key not in alerted:
                    alerted.add(key)
                    print(f"🔥 ЗНАЙДЕНО! {symbol} зміна {change:.2f}% (ціна: {price})")
                    await send_alert(symbol, change, price, "PUMP" if change > 0 else "DUMP")
    
    print(f"✅ Перевірено {checked} монет з {len(all_symbols)} | Час: {get_kyiv_time()}")

async def main():
    global all_symbols
    
    print("=" * 50)
    print("PUMP/DUMP MONITOR - BINANCE FUTURES (ВСІ МОНЕТИ)")
    print("=" * 50)
    print(f"📊 Поріг: {PUMP_THRESHOLD}% (без обмеження за часом)")
    print(f"🔄 Перевірка кожні {CHECK_INTERVAL}с")
    print(f"🕐 Часовий пояс: Київ")
    print("=" * 50)
    
    print("📡 Отримую список всіх монет Binance Futures...")
    all_symbols = await get_all_symbols_binance()
    print(f"✅ ЗНАЙДЕНО {len(all_symbols)} ф'ючерсних USDT-монет")
    
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
