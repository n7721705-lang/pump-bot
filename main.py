import asyncio
import time
import io
import aiohttp
from datetime import datetime, timezone, timedelta
from telegram import Bot

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

async def get_binance_chart(symbol):
    """
    Отримує зображення графіка з Binance
    Використовує публічний API Binance для генерації графіка
    """
    try:
        # Binance публічний ендпоінт для графіків (klines)
        # Отримуємо дані за останні 5 хвилин (15 свічок по 20 секунд)
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1m&limit=15"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                data = await resp.json()
                if not data:
                    return None
                
                # Формуємо дані для графіка
                import matplotlib.pyplot as plt
                import matplotlib.dates as mdates
                import numpy as np
                
                # Використовуємо Agg бекенд (без GUI)
                import matplotlib
                matplotlib.use('Agg')
                
                # Парсимо дані
                times = [datetime.fromtimestamp(int(k[0])/1000) for k in data]
                opens = [float(k[1]) for k in data]
                highs = [float(k[2]) for k in data]
                lows = [float(k[3]) for k in data]
                closes = [float(k[4]) for k in data]
                
                # Створюємо графік
                fig, ax = plt.subplots(figsize=(10, 5))
                fig.patch.set_facecolor('#1a1a2e')
                ax.set_facecolor('#16213e')
                
                # Малюємо свічки
                width = 0.6
                for i, (t, o, h, l, c) in enumerate(zip(times, opens, highs, lows, closes)):
                    color = '#00ff88' if c >= o else '#ff6b6b'
                    # Тінь (high-low)
                    ax.plot([t, t], [l, h], color=color, linewidth=1)
                    # Тіло свічки
                    ax.bar(t, abs(c-o), bottom=min(o,c), width=width, color=color, alpha=0.7)
                
                # Заголовок
                current_price = closes[-1]
                change = ((current_price - opens[0]) / opens[0]) * 100
                ax.set_title(f'{symbol}  {change:+.2f}%  останні 15 хв',
                             color='white', fontsize=14, fontweight='bold')
                
                # Осі
                ax.tick_params(colors='white')
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                ax.xaxis.set_major_locator(mdates.AutoDateLocator())
                ax.set_ylabel('Ціна (USDT)', color='white', fontsize=10)
                ax.grid(True, alpha=0.2, color='white')
                
                plt.tight_layout()
                
                # Зберігаємо в буфер
                buf = io.BytesIO()
                plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='#1a1a2e')
                buf.seek(0)
                plt.close()
                
                return buf
                
    except Exception as e:
        print(f"❌ Помилка створення графіка: {e}")
        return None

async def send_alert_with_chart(symbol, change, price, alert_type, elapsed, start_price):
    emoji = "🟢" if alert_type == "PUMP" else "🔴"
    title = "PUMP" if alert_type == "PUMP" else "DUMP"
    
    if elapsed < 60:
        time_str = f"{int(elapsed)}с"
    else:
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        time_str = f"{minutes}хв {seconds}с"
    
    caption = (
        f"{emoji} *{title}*\n"
        f"📊 *Монета:* `{symbol}`\n"
        f"📈 *Зміна:* {change:+.2f}% за {time_str}\n"
        f"💰 *Ціна:* {start_price} → {price} USDT\n"
        f"🕐 *Час:* {get_kyiv_time()}"
    )
    
    try:
        # Отримуємо графік з Binance
        chart_buffer = await get_binance_chart(symbol)
        
        if chart_buffer:
            await bot.send_photo(
                chat_id=TELEGRAM_CHAT_ID,
                photo=chart_buffer,
                caption=caption,
                parse_mode="Markdown"
            )
            print(f"[✓] СИГНАЛ З ГРАФІКОМ: {symbol} {alert_type} {change:.2f}% за {time_str}")
        else:
            # Якщо графік не створився — надсилаємо текст
            await send_alert_text(symbol, change, price, alert_type, elapsed, start_price)
            
    except Exception as e:
        print(f"[✗] ПОМИЛКА: {e}")
        await send_alert_text(symbol, change, price, alert_type, elapsed, start_price)

async def send_alert_text(symbol, change, price, alert_type, elapsed, start_price):
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
        f"📈 *Зміна:* {change:+.2f}% за {time_str}\n"
        f"💰 *Ціна:* {start_price} → {price} USDT\n"
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
                     f"📊 Графік: свічковий (Binance API)\n"
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
                    await send_alert_with_chart(
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
    print(f"📊 Графік: свічковий (Binance API + matplotlib)")
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
