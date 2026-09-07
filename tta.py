import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
import math
import threading
from datetime import datetime, time as dtime, timedelta
import pytz
import plotly.graph_objects as go

if "screener_running" not in st.session_state:
    st.session_state["screener_running"] = False

st.set_page_config(
    page_title="W1zarD TTA // Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Премиальный минималистичный темный стиль с белыми и голубыми акцентами
st.markdown("""
<style>
    .stApp { background-color: #0b0e14; color: #f0f6fc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    h1, h2, h3, h4 { color: #ffffff !important; font-weight: 700 !important; letter-spacing: -0.5px; }
    .stButton>button { background-color: #161b22; color: #38bdf8; border-radius: 6px; border: 1px solid #30363d; font-weight: 600; width: 100%; transition: 0.2s; }
    .stButton>button:hover { background-color: #38bdf8; border-color: #38bdf8; color: #0b0e14; }
    .metric-card { background-color: #161b22; border: 1px solid #30363d; padding: 18px; border-radius: 8px; margin-bottom: 12px; }
    .status-box { background-color: #161b22; border-left: 3px solid #38bdf8; padding: 12px 16px; border-radius: 6px; margin-bottom: 15px; }
    hr { border-color: #21262d; }
</style>
""", unsafe_allow_html=True)

SETTINGS_FILE = "tta_settings.json"
JOURNAL_FILE = "my_journal.csv"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"token": "", "chat_id": ""}

def save_settings(token, chat_id):
    with open(SETTINGS_FILE, "w") as f:
        json.dump({"token": token, "chat_id": chat_id}, f)

settings = load_settings()

def send_telegram(token, chat_id, message):
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def load_journal():
    if os.path.exists(JOURNAL_FILE):
        try:
            return pd.read_csv(JOURNAL_FILE)
        except Exception:
            pass
    return pd.DataFrame(columns=["date", "instrument", "risk_choice", "result_r", "profit_usd"])

def save_to_journal(inst, risk, result_r, balance):
    df = load_journal()
    risk_usd = balance * (risk / 100.0)
    profit_usd = risk_usd * result_r
    new_row = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "instrument": inst,
        "risk_choice": risk,
        "result_r": result_r,
        "profit_usd": profit_usd
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(JOURNAL_FILE, index=False)

def run_screener_loop(token, chat_id):
    st.session_state["screener_running"] = True
    instruments = {
        "XAUUSD": {"ticker": "GC=F", "session_start": dtime(3, 0), "session_end": dtime(10, 0)},
        "SPX500": {"ticker": "^GSPC", "session_start": dtime(11, 0), "session_end": dtime(16, 30)}
    }
    tz_msk = pytz.timezone("Europe/Moscow")

    while st.session_state.get("screener_running", False):
        now_msk = datetime.now(tz_msk)
        for name, cfg in instruments.items():
            try:
                df = yf.download(cfg["ticker"], period="3d", interval="5m", progress=False)
                if df.empty or len(df) < 50:
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [c[0] for c in df.columns]
                df.columns = [c.lower() for c in df.columns]
                df = df.reset_index()
                
                time_col = 'datetime' if 'datetime' in df.columns else df.columns[0]
                df['time_msk'] = pd.to_datetime(df[time_col], utc=True).dt.tz_convert(tz_msk)

                today = now_msk.date()
                session_df = df[(df['time_msk'].dt.date == today) & 
                                (df['time_msk'].dt.time >= cfg['session_start']) & 
                                (df['time_msk'].dt.time <= cfg['session_end'])]
                
                if session_df.empty:
                    continue
                
                s_high = session_df['high'].max()
                s_low = session_df['low'].min()

                last = df.iloc[-2]
                prev = df.iloc[-3]
                prev2 = df.iloc[-4]

                last_bull = last['close'] > last['open']
                last_bear = last['close'] < last['open']
                prev_bull = prev['close'] > prev['open']
                prev_bear = prev['close'] < prev['open']

                # Покупки (Свип Low)
                if last['low'] < s_low and last['close'] > s_low:
                    if last_bull and prev_bear and last['close'] > prev['open']:
                        msg = f"⚡ *[W1zarD TTA] СИГНАЛ!*\n\n🔹 *Актив:* `{name}`\n🔹 *Модель:* `Свип Low + Поглощение`\n🔹 *Вход:* 🟢 `BUY`"
                        send_telegram(token, chat_id, msg)
                        time.sleep(300)
                    elif prev2['high'] < prev['low'] and last['close'] > prev['low']:
                        msg = f"⚡ *[W1zarD TTA] СИГНАЛ!*\n\n🔹 *Актив:* `{name}`\n🔹 *Модель:* `Свип Low + IFVG`\n🔹 *Вход:* 🟢 `BUY`"
                        send_telegram(token, chat_id, msg)
                        time.sleep(300)

                # Продажи (Свип High)
                elif last['high'] > s_high and last['close'] < s_high:
                    if last_bear and prev_bull and last['close'] < prev['open']:
                        msg = f"⚡ *[W1zarD TTA] СИГНАЛ!*\n\n🔹 *Актив:* `{name}`\n🔹 *Модель:* `Свип High + Поглощение`\n🔹 *Вход:* 🔴 `SELL`"
                        send_telegram(token, chat_id, msg)
                        time.sleep(300)
                    elif prev2['low'] > prev['high'] and last['close'] < prev['high']:
                        msg = f"⚡ *[W1zarD TTA] СИГНАЛ!*\n\n🔹 *Актив:* `{name}`\n🔹 *Модель:* `Свип High + IFVG`\n🔹 *Вход:* 🔴 `SELL`"
                        send_telegram(token, chat_id, msg)
                        time.sleep(300)

            except Exception:
                pass
        time.sleep(60)

# ШЛЮЗ ДИСЦИПЛИНЫ
st.markdown('<div class="status-box">', unsafe_allow_html=True)
st.subheader("Шлюз готовности трейдера")
col_c1, col_c2, col_c3, col_c4 = st.columns(4)
with col_c1:
    check_sleep = st.checkbox("Сон от 7+ часов")
with col_c2:
    check_mind = st.checkbox("Хладнокровие / Нет стресса")
with col_c3:
    check_news = st.checkbox("Календарь проверен")
with col_c4:
    check_rules = st.checkbox("Риск 0.5% / 1.0% подтвержден")

gate_passed = check_sleep and check_mind and check_news and check_rules
st.markdown('</div>', unsafe_allow_html=True)

tz_msk = pytz.timezone("Europe/Moscow")
now_msk = datetime.now(tz_msk)

news_hour = 15 if now_msk.hour < 15 else 21
target_news_time = tz_msk.localize(datetime.combine(now_msk.date(), dtime(news_hour, 30)))
time_diff = target_news_time - now_msk
minutes_left = int(time_diff.total_seconds() / 60)

if 0 < minutes_left <= 30:
    st.warning(f"⚠️ КРАСНАЯ ЗОНА: До выхода новостей США осталось {minutes_left} мин. Входы заблокированы.")
else:
    st.info(f"🟢 Зеленое окно ликвидности. До макро-новостей: {minutes_left if minutes_left > 0 else minutes_left + 1440} мин.")

col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.subheader("Калькулятор лота")
    inst = st.selectbox("Инструмент", ["XAUUSD (Золото)", "SPX500 (S&P 500)"], disabled=not gate_passed)
    balance = st.number_input("Баланс ($)", min_value=100.0, value=10000.0, step=1000.0, disabled=not gate_passed)
    risk_choice = st.radio("Риск на сделку", [0.5, 1.0], horizontal=True, disabled=not gate_passed)
    sl_points = st.number_input("Стоп-Лосс (Points)", min_value=0.1, value=10.0, step=1.0, disabled=not gate_passed)

    contract_size = 100 if "XAUUSD" in inst else 50
    risk_usd = balance * (risk_choice / 100.0)
    
    if sl_points > 0:
        raw_lot = risk_usd / (sl_points * contract_size)
        calculated_lot = math.floor(raw_lot * 100) / 100.0
    else:
        calculated_lot = 0.0

    st.markdown(f"""
    <div class="metric-card">
        <div style="font-size: 13px; color: #8b949e; text-transform: uppercase;">Риск в деньгах: <b style="color:#ffffff;">${risk_usd:.2f}</b> | Контракт: <b style="color:#ffffff;">{contract_size}</b></div>
        <div style="margin-top: 10px; font-size: 14px; color: #38bdf8;">РАСЧЕТНЫЙ ОБЪЕМ (ЛОТ):</div>
        <div style="font-size: 38px; font-weight: 800; color: #ffffff;">{calculated_lot:.2f}</div>
    </div>
    """, unsafe_allow_html=True)
    st.code(f"{calculated_lot:.2f}", language="text")

    st.write("---")
    st.subheader("Фиксация сделки")
    r_result = st.selectbox("Результат R", [1.0, 2.0, 3.0, 4.0, -1.0, 0.0], format_func=lambda x: f"+{x}R" if x > 0 else f"{x}R")
    if st.button("Записать в Журнал", disabled=not gate_passed):
        save_to_journal(inst, risk_choice, r_result, balance)
        st.success("Сохранено в my_journal.csv")

with col2:
    st.subheader("Управление алертом")
    tg_token = st.text_input("Bot Token", value=settings.get("token", ""), type="password", disabled=not gate_passed)
    tg_chat = st.text_input("Chat ID", value=settings.get("chat_id", ""), disabled=not gate_passed)
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Сохранить ключи", disabled=not gate_passed):
            save_settings(tg_token, tg_chat)
            st.success("Сохранено")
    with c2:
        if st.button("Тест связи", disabled=not gate_passed):
            if tg_token and tg_chat:
                ok = send_telegram(tg_token, tg_chat, "⚡ *[W1zarD TTA] Связь с терминалом установлена.*")
                if ok:
                    st.success("Уведомление отправлено!")
                else:
                    st.error("Ошибка! Проверьте данные.")

    st.write("---")
    st.subheader("Скринер M5")
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if st.button("СТАРТ СКРИНЕРА", disabled=not gate_passed):
            if not tg_token or not tg_chat:
                st.error("Укажите ключи Telegram!")
            else:
                if not st.session_state.get("screener_running", False):
                    t = threading.Thread(target=run_screener_loop, args=(tg_token, tg_chat), daemon=True)
                    t.start()
                    st.success("Скринер запущен!")
                    send_telegram(tg_token, tg_chat, "📡 *[W1zarD TTA] Скринер M5 активен.*")
    with c_btn2:
        if st.button("ОСТАНОВИТЬ", disabled=not gate_passed):
            st.session_state["screener_running"] = False
            st.warning("Скринер остановлен.")

# ПРОФЕССИОНАЛЬНЫЙ ГРАФИК M5
st.write("---")
st.subheader("График структуры M5 (Plotly)")

with st.spinner("Загрузка рыночной структуры..."):
    ticker_symbol = "GC=F" if "XAUUSD" in inst else "^GSPC"
    chart_df = yf.download(ticker_symbol, period="2d", interval="5m", progress=False)
    
    if not chart_df.empty:
        if isinstance(chart_df.columns, pd.MultiIndex):
            chart_df.columns = [c[0] for c in chart_df.columns]
        
        chart_df = chart_df.reset_index()
        time_col = 'Datetime' if 'Datetime' in chart_df.columns else chart_df.columns[0]
        chart_df['time_msk'] = pd.to_datetime(chart_df[time_col], utc=True).dt.tz_convert(tz_msk)
        
        fig = go.Figure(data=[go.Candlestick(
            x=chart_df['time_msk'],
            open=chart_df['Open'],
            high=chart_df['High'],
            low=chart_df['Low'],
            close=chart_df['Close'],
            increasing_line_color='#38bdf8',
            decreasing_line_color='#f43f5e',
            name="M5"
        )])
        
        today_date = datetime.now(tz_msk).date()
        asia_start = tz_msk.localize(datetime.combine(today_date, dtime(3, 0)))
        asia_end = tz_msk.localize(datetime.combine(today_date, dtime(10, 0)))
        
        fig.add_vrect(x0=asia_start, x1=asia_end, fillcolor="rgba(56, 189, 248, 0.07)", line_width=0)
        
        asia_df = chart_df[(chart_df['time_msk'] >= asia_start) & (chart_df['time_msk'] <= asia_end)]
        if not asia_df.empty:
            a_high = asia_df['High'].max()
            a_low = asia_df['Low'].min()
            fig.add_hline(y=a_high, line_dash="dash", line_color="#38bdf8", annotation_text="Asian High (BSL)", annotation_position="top left")
            fig.add_hline(y=a_low, line_dash="dash", line_color="#f43f5e", annotation_text="Asian Low (SSL)", annotation_position="bottom left")

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0b0e14",
            plot_bgcolor="#0b0e14",
            xaxis_rangeslider_visible=False,
            margin=dict(l=10, r=10, t=10, b=10),
            height=420,
            yaxis=dict(gridcolor="#161b22", side="right"),
            xaxis=dict(gridcolor="#161b22")
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Нет данных котировок.")

# КРИВАЯ ЭКВИТИ
st.write("---")
st.subheader("Кривая эквити депозита ($)")
journal_df = load_journal()
if not journal_df.empty:
    journal_df["cum_profit"] = journal_df["profit_usd"].cumsum()
    journal_df["equity"] = 10000.0 + journal_df["cum_profit"]
    
    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(
        x=journal_df["date"],
        y=journal_df["equity"],
        mode="lines+markers",
        line=dict(color="#38bdf8", width=2),
        marker=dict(size=6, color="#ffffff"),
        name="Equity"
    ))
    fig_eq.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b0e14",
        plot_bgcolor="#0b0e14",
        margin=dict(l=10, r=10, t=10, b=10),
        height=260,
        yaxis=dict(gridcolor="#161b22"),
        xaxis=dict(gridcolor="#161b22")
    )
    st.plotly_chart(fig_eq, use_container_width=True)
else:
    st.caption("Журнал пуст. Запишите сделку, чтобы построить график.")