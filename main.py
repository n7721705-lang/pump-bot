import asyncio
import time
import json
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

async def create_chart_quickchart(symbol, prices_history, start_price, current_price, change, elapsed):
    """Створює графік через QuickChart API (простий варіант)"""
    
    # Формуємо дані для графіка
    times = [datetime.fromtimestamp(t, tz=timezone.utc).astimezone(KYIV_TZ).strftime('%H:%M:%S') 
             for t, _ in prices_history]
    values = [p for _, p in prices_history]
    
    # Кольори для PUMP/DUMP
    color = '00ff88' if change > 0 else 'ff6b6b'
    fill_color = '00ff88' if change > 0 else 'ff6b6b'
    
    # Формуємо простий URL для QuickChart
    # Беремо першу та останню ціну для відображення
    first_price = prices_history[0][1]
    last_price = prices_history[-1][1]
    
    # Формуємо JSON для графіка
    chart_config = {
        "type": "line",
        "data": {
            "labels": times,
            "datasets": [{
                "label": f"{symbol}",
                "data": values,
                "borderColor": color,
                "backgroundColor": f"{color}33",
                "fill": True,
                "pointRadius": 3,
                "tension": 0.2
            }]
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": f"{symbol}  {change:+.2f}%  за {int(elapsed)}с",
                    "color": "white",
                    "font": {"size": 14}
                },
                "legend": {
                    "labels": {"color": "white"}
                }
            },
            "scales": {
                "x": {
                    "ticks": {"color": "white", "font": {"size": 8}},
                    "grid": {"color": "rgba(255,255,255,0.1)"}
                },
                "y": {
                    "ticks": {"color": "white", "font": {"size": 8}},
                    "grid": {"color": "rgba(255,255,255,0.1)"}
                }
            }
        }
    }
    
    # Кодуємо JSON
    chart_json = json.dumps(chart_config)
    
    # URL для QuickChart (спрощений варіант)
    chart_url = f"https://quickchart.io/chart?c={chart_json}&bkg=1a1a2e&width=500&height=350"
    
    return chart_url

async def send_alert_with_chart(symbol, change, price, alert_type, elapsed, start_price, prices_history):
    emoji = "🟢" if alert_type == "PUMP" else "🔴"
    title = "PUMP" if alert_type == "PUMP" else "DUMP"
    
    if elapsed < 60:
        time_str = f"{int(elapsed)}с"
    else:
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        time_str = f"{minutes}хв {seconds}с"
    
    # Текст повідомлення
    caption = (
        f"{emoji} *{title}*\n"
        f"📊 *Монета:* `{symbol}`\n"
        f"📈 *Зміна:* {change:+.2f}% (за {time_str})\n"
        f"💰 *Поточна ціна:* {price} USDT\n"
        f"📌 *Старт руху:* {start_price} USDT\n"
        f"🕐 *Час:* {get_kyiv_time()}"
    )
    
    try:
        # Створюємо графік
        chart_url = await create_chart_quickchart(
            symbol, prices_history, start_price, price, change, elapsed
        )
        
        # Надсилаємо фото через URL
        await bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID,
            photo=chart_url,
            caption=caption,
            parse_mode="Markdown"
        )
        print(f"[✓] СИГНАЛ З ГРАФІКОМ: {symbol} {alert_type} {change:.2f}% за {time_str}")
    except Exception as e:
        print(f"[✗] ПОМИЛКА ГРАФІКА: {e}")
        # Якщо не вийшло з графіком, надсилаємо текст
        await send_alert_text(symbol, change, price, alert_type, elapsed, start_price)

async def send_alert_text(symbol, change, price, alert_type, elapsed, start_price):
    """Надсилає тільки текст (резервний варіант)"""
    emoji = "🟢" if alert_type == "PUMP" else "🔴"
    title = "PUMP" if alert_type == "PUMP" else "DUMP"
    
    if elapsed < 60:
        time_str = f"{int(elapsed)}с"
    else:
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        time_str = f"{minutes}хв {seconds}с"
    
    message = (
        f"{emoji} *{title}*\n"
        f"📊 *Монета:* `{symbol}`\n"
        f"📈 *Зміна:* {change:+.2f}% (за {time_str})\n"
        f"💰 *Поточна ціна:* {price} USDT\n"
        f"📌 *Старт руху:* {start_price} USDT\n"
        f"🕐 *Час:* {get_kyiv_time()}"
    )
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
        print(f"[✓] ТЕКСТОВИЙ СИГНАЛ: {symbol} {alert_type} {change:.2f}% за {time_str}")
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
                     f"⏱ Час руху: {MIN_MOVE_TIME}–{MAX_MOVE_TIME}с\n"
                     f"📊 Графік: QuickChart\n"
                     f"🕐 Київ: {get_kyiv_time()}",
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
                'last_alert_time': 0,
                'history': [(current_time, price)]
            }
            continue
        
        data = prices[symbol]
        first_price = data['first_price']
        first_time = data['first_time']
        elapsed = current_time - first_time
        change = ((price - first_price) / first_price) * 100
        
        # Додаємо в історію
        data['history'].append((current_time, price))
        if len(data['history']) > 20:
            data['history'] = data['history'][-20:]
        
        time_since_last_alert = current_time - data['last_alert_time']
        
        if abs(change) >= PUMP_THRESHOLD and not data['alerted']:
            if MIN_MOVE_TIME <= elapsed <= MAX_MOVE_TIME:
                if time_since_last_alert >= 5:
                    data['alerted'] = True
                    data['last_alert_time'] = current_time
                    print(f"🔥 ЗНАЙДЕНО! {symbol} зміна {change:.2f}% за {elapsed:.1f}с")
                    await send_alert_with_chart(
                        symbol, change, price,
                        "PUMP" if change > 0 else "DUMP",
                        elapsed,
                        first_price,
                        data['history']
                    )
            elif elapsed < MIN_MOVE_TIME:
                pass
            elif elapsed > MAX_MOVE_TIME:
                prices[symbol] = {
                    'first_price': price,
                    'first_time': current_time,
                    'alerted': False,
                    'last_alert_time': data['last_alert_time'],
                    'history': [(current_time, price)]
                }
                print(f"🔄 Скидання {symbol}: час {elapsed:.1f}с > {MAX_MOVE_TIME}с")
        
        if elapsed > MAX_MOVE_TIME or abs(change) < 0.3:
            if elapsed > MAX_MOVE_TIME:
                prices[symbol] = {
                    'first_price': price,
                    'first_time': current_time,
                    'alerted': False,
                    'last_alert_time': data['last_alert_time'],
                    'history': [(current_time, price)]
                }
                print(f"🔄 Скидання {symbol}: новий рух від {price}")
    
    print(f"✅ Перевірено {checked} монет з {len(all_symbols)} | Час: {get_kyiv_time()}")

async def main():
    global all_symbols
    
    print("=" * 50)
    print("PUMP/DUMP MONITOR - BINANCE FUTURES (З ГРАФІКОМ)")
    print("=" * 50)
    print(f"📊 Поріг: {PUMP_THRESHOLD}%")
    print(f"⏱ Час руху: {MIN_MOVE_TIME}–{MAX_MOVE_TIME}с")
    print(f"🔄 Перевірка кожні {CHECK_INTERVAL}с")
    print(f"📊 Графік: QuickChart API")
    print(f"🕐 Часовий пояс: Київ")
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
