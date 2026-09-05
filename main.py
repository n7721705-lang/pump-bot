import asyncio
import time
import io
from datetime import datetime, timezone, timedelta
from telegram import Bot
import aiohttp
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import FancyBboxPatch
import numpy as np

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

async def create_chart(symbol, prices_list, start_price, current_price, change, elapsed, high_price, low_price):
    """Створює графік з підписами"""
    
    # Налаштування графіка
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#16213e')
    
    # Розпаковуємо дані
    times = [p[0] for p in prices_list]
    values = [p[1] for p in prices_list]
    
    # Перетворюємо час у datetime
    dt_times = [datetime.fromtimestamp(t, tz=timezone.utc).astimezone(KYIV_TZ) for t in times]
    
    # Малюємо лінію ціни
    ax.plot(dt_times, values, color='#00d2ff', linewidth=2.5, label='Ціна')
    
    # Додаємо точки максимуму/мінімуму
    ax.scatter(dt_times[0], values[0], color='#00ff88', s=100, zorder=5, label='Старт')
    ax.scatter(dt_times[-1], values[-1], color='#ff6b6b' if change < 0 else '#00ff88', s=100, zorder=5, label='Поточна')
    
    # Додаємо горизонтальні лінії для старту та поточної ціни
    ax.axhline(y=start_price, color='#00ff88', linestyle='--', linewidth=1.5, alpha=0.7)
    ax.axhline(y=current_price, color='#ff6b6b' if change < 0 else '#00ff88', linestyle='--', linewidth=1.5, alpha=0.7)
    
    # Заповнюємо область між цінами
    ax.fill_between(dt_times, start_price, values[-1], 
                     color='#00ff88' if change > 0 else '#ff6b6b', 
                     alpha=0.2)
    
    # Налаштовуємо графік
    ax.set_title(f'{symbol} — {change:+.2f}% за {int(elapsed)}с', 
                 color='white', fontsize=14, fontweight='bold')
    ax.set_xlabel('Час (Київ)', color='white', fontsize=10)
    ax.set_ylabel('Ціна (USDT)', color='white', fontsize=10)
    
    # Налаштовуємо кольори осей
    ax.tick_params(colors='white')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    
    # Додаємо анотації на графік
    # Старт
    ax.annotate(f'Старт: {start_price:.4f} USDT', 
                xy=(dt_times[0], values[0]),
                xytext=(dt_times[0], values[0] - (max(values)-min(values))*0.1),
                color='#00ff88', fontsize=9,
                ha='center', va='top')
    
    # Поточна
    ax.annotate(f'Поточна: {current_price:.4f} USDT', 
                xy=(dt_times[-1], values[-1]),
                xytext=(dt_times[-1], values[-1] + (max(values)-min(values))*0.1),
                color='#ff6b6b' if change < 0 else '#00ff88', fontsize=9,
                ha='center', va='bottom')
    
    # Зміна
    mid_idx = len(dt_times) // 2
    mid_y = (start_price + current_price) / 2
    ax.annotate(f'Зміна: {change:+.2f}%', 
                xy=(dt_times[mid_idx], mid_y),
                xytext=(dt_times[mid_idx], mid_y + (max(values)-min(values))*0.05),
                color='white', fontsize=11, fontweight='bold',
                ha='center', va='bottom',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#1a1a2e', alpha=0.8))
    
    # Додаємо легенду
    ax.legend(loc='upper left', facecolor='#1a1a2e', labelcolor='white', framealpha=0.8)
    
    # Сітка
    ax.grid(True, alpha=0.2, color='white')
    
    plt.tight_layout()
    
    # Зберігаємо в буфер
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='#1a1a2e')
    buf.seek(0)
    plt.close()
    
    return buf

async def send_alert_with_chart(symbol, change, price, alert_type, elapsed, start_price, high_price, low_price, prices_history):
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
        f"📈 *Максимум:* {high_price} USDT\n"
        f"📉 *Мінімум:* {low_price} USDT\n"
        f"🕐 *Час:* {get_kyiv_time()}"
    )
    
    try:
        # Створюємо графік
        chart_buffer = await create_chart(
            symbol, prices_history, start_price, price, change, elapsed, high_price, low_price
        )
        
        # Надсилаємо фото з підписом
        await bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID,
            photo=chart_buffer,
            caption=caption,
            parse_mode="Markdown"
        )
        print(f"[✓] СИГНАЛ З ГРАФІКОМ: {symbol} {alert_type} {change:.2f}% за {time_str}")
    except Exception as e:
        print(f"[✗] Помилка відправки: {e}")

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
                     f"📊 Графік: так\n"
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
                'high_price': price,
                'low_price': price,
                'history': [(current_time, price)],
                'volume': float(item.get('quoteVolume', 0))
            }
            continue
        
        data = prices[symbol]
        first_price = data['first_price']
        first_time = data['first_time']
        elapsed = current_time - first_time
        change = ((price - first_price) / first_price) * 100
        
        # Додаємо в історію
        data['history'].append((current_time, price))
        if len(data['history']) > 100:
            data['history'] = data['history'][-100:]
        
        # Оновлюємо максимум/мінімум
        if price > data['high_price']:
            data['high_price'] = price
        if price < data['low_price']:
            data['low_price'] = price
        
        time_since_last_alert = current_time - data['last_alert_time']
        
        if abs(change) >= PUMP_THRESHOLD and not data['alerted']:
            if MIN_MOVE_TIME <= elapsed <= MAX_MOVE_TIME:
                if time_since_last_alert >= 5:
                    data['alerted'] = True
                    data['last_alert_time'] = current_time
                    print(f"🔥 ЗНАЙДЕНО! {symbol} зміна {change:.2f}% за {elapsed:.1f}с")
                    
                    # Відправляємо з графіком
                    await send_alert_with_chart(
                        symbol, change, price,
                        "PUMP" if change > 0 else "DUMP",
                        elapsed,
                        first_price,
                        data['high_price'],
                        data['low_price'],
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
                    'high_price': price,
                    'low_price': price,
                    'history': [(current_time, price)],
                    'volume': float(item.get('quoteVolume', 0))
                }
                print(f"🔄 Скидання {symbol}: час {elapsed:.1f}с > {MAX_MOVE_TIME}с")
        
        if elapsed > MAX_MOVE_TIME or abs(change) < 0.3:
            if elapsed > MAX_MOVE_TIME:
                prices[symbol] = {
                    'first_price': price,
                    'first_time': current_time,
                    'alerted': False,
                    'last_alert_time': data['last_alert_time'],
                    'high_price': price,
                    'low_price': price,
                    'history': [(current_time, price)],
                    'volume': float(item.get('quoteVolume', 0))
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
