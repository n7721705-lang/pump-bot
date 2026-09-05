import asyncio
import time
from datetime import datetime, timezone, timedelta
from telegram import Bot
import aiohttp

# ==================== НАЛАШТУВАННЯ ====================
TELEGRAM_BOT_TOKEN = "8686768235:AAEphYxwBp36WM8kkhgjm4akOhtrkJNp_vw"
TELEGRAM_CHAT_ID = -1004438401967
PUMP_THRESHOLD = 2.0
MIN_PRICE = 0.001
CHECK_INTERVAL = 5
MIN_MOVE_TIME = 10
MAX_MOVE_TIME = 60
# =====================================================

KYIV_TZ = timezone(timedelta(hours=3))

bot = Bot(token=TELEGRAM_BOT_TOKEN)
prices = {}
all_symbols = []

def get_kyiv_time():
    return datetime.now(KYIV_TZ).strftime('%H:%M:%S')

async def send_alert(symbol, change, price, alert_type, elapsed, start_price):
    # Визначаємо колір та дію
    if alert_type == "PUMP":
        emoji = "🟢"
        action = "прибавила"
        change_text = f"+{change:.2f}%"
    else:
        emoji = "🔴"
        action = "упала"
        change_text = f"{change:.2f}%"
    
    # Форматуємо час
    if elapsed < 60:
        time_str = f"{int(elapsed)} сек."
    else:
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        time_str = f"{minutes} мин. {seconds} сек."
    
    # Повідомлення як на скріншоті
    message = (
        f"{emoji} *{symbol} ({symbol.replace('USDT', '')})* {action} на *{change_text}* за последние {time_str}\n"
        f"💰 Цена: {start_price}$ → {price}$"
    )
    
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
        print(f"[✓] СИГНАЛ: {symbol} {alert_type} {change:.2f}% за {elapsed:.1f}с")
    except Exception as e:
        print(f"[✗] Помилка: {e}")

async def get_all_symbols_binance():
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
    global prices, all_symbols
    
    current_time = time.time()
    
    tickers = await get_all_prices_binance()
    if not tickers:
        print("⚠️ Не вдалося отримати ціни")
        return
    
    if not all_symbols:
        all_symbols = [item['symbol'] for item in tickers if item['symbol'].endswith('USDT')]
        print(f"📊 ВСЬОГО МОНЕТ НА BINANCE: {len(all_symbols)}")
        
        try:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=f"✅ *Бот запущено на Binance!*\n"
                     f"📊 Моніторинг {len(all_symbols)} монет\n"
                     f"📈 Поріг: {PUMP_THRESHOLD}%\n"
                     f"⏱ Час руху: {MIN_MOVE_TIME}–{MAX_MOVE_TIME}с",
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
            elif elapsed < MIN_MOVE_TIME:
                pass
            elif elapsed > MAX_MOVE_TIME:
                prices[symbol] = {
                    'first_price': price,
                    'first_time': current_time,
                    'alerted': False,
                    'last_alert_time': data['last_alert_time']
                }
                print(f"🔄 Скидання {symbol}: час {elapsed:.1f}с > {MAX_MOVE_TIME}с")
        
        if elapsed > MAX_MOVE_TIME or abs(change) < 0.3:
            if elapsed > MAX_MOVE_TIME:
                prices[symbol] = {
                    'first_price': price,
                    'first_time': current_time,
                    'alerted': False,
                    'last_alert_time': data['last_alert_time']
                }
                print(f"🔄 Скидання {symbol}: новий рух від {price}")
    
    if int(current_time / 10) % 10 == 0:
        print(f"✅ Перевірено {checked} монет з {len(all_symbols)} | Час: {get_kyiv_time()}")

async def main():
    global all_symbols
    
    print("=" * 50)
    print("PUMP/DUMP MONITOR - BINANCE FUTURES")
    print("=" * 50)
    print(f"📊 Поріг: {PUMP_THRESHOLD}%")
    print(f"⏱ Час руху: {MIN_MOVE_TIME}–{MAX_MOVE_TIME}с")
    print(f"🔄 Перевірка кожні {CHECK_INTERVAL}с")
    print("=" * 50)
    
    print("📡 Отримую список всіх монет Binance Futures...")
    all_symbols = await get_all_symbols_binance()
    print(f"✅ ЗНАЙДЕНО {len(all_symbols)} ф'ючерсних USDT-монет")
    
    while True:
        try:
            await check_pumps()
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"❌ Помилка в циклі: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
