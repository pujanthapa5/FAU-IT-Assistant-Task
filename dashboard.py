import streamlit as st
import time
from datetime import datetime, timedelta
import queue
import logging
from receiver import PusherSensorReceiver
import config
from event_scraper import EventScraper
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import textwrap

# Configure page
st.set_page_config(
    page_title="Sensor Dashboard",
    page_icon="🌡️",
    layout="wide"
)

st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        div.block-container {padding-top: 1rem;} 
    </style>
""", unsafe_allow_html=True)

if 'data_queue' not in st.session_state:
    st.session_state.data_queue = queue.Queue()

data_queue = st.session_state.data_queue


def on_message_received(data):
    try:
        data['timestamp'] = datetime.now()
        data_queue.put(data)
    except Exception:
        pass


if 'receiver' not in st.session_state:
    receiver = PusherSensorReceiver(
        api_key=config.PUSHER_KEY,
        cluster=config.PUSHER_CLUSTER,
        log_level=logging.INFO
    )
    channels = [f'room-{i}' for i in range(1, 4)] + ['screenshot-stream']
    receiver.connect(channels, on_message_received)
    st.session_state.receiver = receiver
else:
    receiver = st.session_state.receiver

if 'history' not in st.session_state: st.session_state.history = []
if 'latest' not in st.session_state: st.session_state.latest = {}
if 'page' not in st.session_state: st.session_state.page = 'dashboard'
if 'screenshot_active' not in st.session_state: st.session_state.screenshot_active = False
if 'last_screenshot_signal' not in st.session_state: st.session_state.last_screenshot_signal = 0

if 'events' not in st.session_state: st.session_state.events = []
if 'event_index' not in st.session_state: st.session_state.event_index = 0
if 'last_fetched' not in st.session_state: st.session_state.last_fetched = 0

REFRESH_INTERVAL = 86400  # Re-check website every 24 hours (1 day)

now_ts = time.time()
if now_ts - st.session_state.last_fetched > REFRESH_INTERVAL or not st.session_state.events:
    fetched = EventScraper().fetch_upcoming(n=1)
    if fetched:
        st.session_state.events = fetched
        st.session_state.last_fetched = now_ts

# Memory Protection (Capping the data)
while not data_queue.empty():
    item = data_queue.get()
    room = item.get('room')
    if room:
        st.session_state.latest[room] = item
        st.session_state.history.append({
            "Time": item['timestamp'],
            "Room": room,
            "Temp": item['temperature'],
            "Hum": item['humidity']
        })

    if len(st.session_state.history) > 10000:
        st.session_state.history = st.session_state.history[-10000:]

    if item.get('type') == 'screenshot':
        st.session_state.latest_screenshot = item.get('url')
        st.session_state.latest_screenshot_timestamp = item.get('timestamp')
        st.session_state.latest_screenshot_data = item
        st.session_state.screenshot_active = True
        st.session_state.last_screenshot_signal = time.time()
    
    if item.get('type') == 'screenshot_status':
        st.session_state.screenshot_active = item.get('active', False)
        st.session_state.last_screenshot_signal = time.time()

if st.session_state.screenshot_active:
    if time.time() - st.session_state.last_screenshot_signal > 300:
        st.session_state.screenshot_active = False


history_data = st.session_state.history


def make_split_charts(data, show_header=False):
    from collections import OrderedDict
    
    hourly_data = OrderedDict()
    for d in data:
        hour_key = d['Time'].replace(minute=0, second=0, microsecond=0)
        hourly_data[hour_key] = d
        
    sorted_hours = sorted(hourly_data.keys())
    times = sorted_hours
    temps = [hourly_data[h]['Temp'] for h in sorted_hours]
    hums = [hourly_data[h]['Hum'] for h in sorted_hours]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.15
    )

    fig.add_trace(
        go.Scatter(
            x=times, y=temps,
            mode="lines+markers",
            line=dict(color="orange", width=2),
            marker=dict(size=6),
            name="Temperature Trend",
            cliponaxis=False
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Scatter(
            x=times, y=hums,
            mode="lines+markers",
            line=dict(color="lightblue", width=2),
            marker=dict(size=6),
            name="Humidity Trend",
            cliponaxis=False
        ),
        row=2, col=1
    )

    tick_font_x = dict(size=18, color="lightgray")

    now = datetime.now()
    end_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    start_time = end_time - timedelta(hours=12)

    fig.update_xaxes(
        range=[start_time, end_time], dtick=3600000, tickformat="%H:%M",
        tickangle=-45, tickfont=tick_font_x, gridcolor="rgba(255,255,255,0.1)",
        row=1, col=1
    )
    
    fig.update_xaxes(
        range=[start_time, end_time], dtick=3600000, tickformat="%H:%M",
        tickangle=-45, tickfont=tick_font_x, gridcolor="rgba(255,255,255,0.1)",
        row=2, col=1
    )

    fig.update_yaxes(
        visible=True, range=[20, 30], dtick=2,
        tickfont=dict(size=18, color="lightgray"), gridcolor="rgba(255,255,255,0.1)",
        title=dict(text="Temp (°C)", font=dict(size=16, color="white")),
        row=1, col=1
    )
    fig.update_yaxes(
        visible=True, range=[25, 45], dtick=5,
        tickfont=dict(size=18, color="lightgray"), gridcolor="rgba(255,255,255,0.1)",
        title=dict(text="Hum (%)", font=dict(size=16, color="white")),
        row=2, col=1
    )

    fig.update_layout(
        height=1000, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=120, b=80, l=30, r=40)
    )

    if show_header:
        fig.update_layout(
            annotations=[
                dict(x=0.5, y=1.05, xref='paper', yref='paper', text='Temperature Trend', showarrow=False, font=dict(size=35, color="white"), xanchor='center'),
                dict(x=0.5, y=0.45, xref='paper', yref='paper', text='Humidity Trend', showarrow=False, font=dict(size=35, color="white"), xanchor='center')
            ]
        )

    return fig

sleep_time = 20

# Main Display Loop
if st.session_state.page == 'dashboard':
    st.markdown("<h1 style='text-align:center;'>🌡️ Lab Environment Monitor</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center;'>Last Update: {datetime.now().strftime('%H:%M:%S')}</p>", unsafe_allow_html=True)
    st.markdown("---")

    cols = st.columns(3)
    ordered_rooms = [("Bilddynamik Room 01.103", "room-1"), ("Lab 2", "room-2"), ("Lab 3", "room-3")]

    for i, (room_display_name, room_id) in enumerate(ordered_rooms):
        with cols[i]:
            st.markdown(f"## {room_display_name}")
            room_data = st.session_state.latest.get(room_id)

            if room_data:
                temp = room_data['temperature']
                hum = room_data['humidity']

                st.markdown(
                    f"""<div style="font-size: 65px;">🌡️ {temp:.2f} °C <br>💧 {hum:.2f} %</div>""",
                    unsafe_allow_html=True
                )

                room_data_list = [d for d in history_data if d['Room'] == room_id]

                if room_data_list:
                    show_header = (room_id == "room-2")
                    st.plotly_chart(make_split_charts(room_data_list, show_header=show_header), width='stretch', config={'staticPlot': True})

                if (room_id == "room-1" and 
                    st.session_state.screenshot_active and 
                    'latest_screenshot' in st.session_state and 
                    st.session_state.latest_screenshot):
                    
                    st.markdown("---")
                    st.markdown("### 📸 Live View")
                    screenshot_data = st.session_state.latest_screenshot_data
                    image_url = st.session_state.latest_screenshot
                    st.image(
                        image_url, 
                        caption=f"Captured: {screenshot_data.get('window_title', 'Unknown')} at {st.session_state.latest_screenshot_timestamp}",
                        use_container_width=True
                    )
            else:
                st.warning("Connecting...")

    # Cycle to next logic
    if st.session_state.events:
        st.session_state.page = 'info'
    else:
        st.session_state.page = 'website'

elif st.session_state.page == 'info':
    events = st.session_state.events
    if events:
        idx = st.session_state.event_index % len(events)
        ev = events[idx]
        
        st.markdown(
            textwrap.dedent(f"""
                <style>
                .info-container {{
                    position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 9999;
                    display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; box-sizing: border-box;
                    font-family: 'Inter', sans-serif; padding: 5vmin;
                    background: radial-gradient(circle at center, #1a1a2e 0%, #0f0f1a 100%);
                }}
                .header-title {{ font-size: 10vmin; font-weight: bold; color: #ffffff; margin-bottom: 5vmin; border-bottom: 2px solid #4DA8FF; padding-bottom: 2vmin; width: 100%; }}
                .event-date {{ font-size: 8vmin; font-weight: bold; color: #FF6B6B; }}
                .event-time {{ font-size: 7vmin; color: #AAD4FF; margin-bottom: 4vmin; }}
                .speaker    {{ font-size: 10vmin; font-weight: bold; color: #00D1FF; line-height: 1.1; }}
                .title      {{ font-size: 7vmin; font-style: italic; color: #4DA8FF; margin: 6vmin 0; line-height: 1.2; text-wrap: balance; }}
                .location   {{ font-size: 7vmin; color: #FFD166; }}
                </style>
                <div class="info-container">
                    <div class="header-title">📅 UPCOMING EVENTS</div>
                    <div class="event-date">📅 {ev.date_str}</div>
                    <div class="event-time">🕐 {ev.time}</div>
                    <div class="speaker">{ev.speaker}</div>
                    <div class="title">{ev.title}</div>
                    <div class="location">📍 {ev.location}</div>
                </div>
            """),
            unsafe_allow_html=True
        )
        st.session_state.event_index += 1

    st.session_state.page = 'website'

elif st.session_state.page == 'website':
    st.markdown(
        '<iframe src="https://www.fkp.physik.nat.fau.eu/" sandbox="allow-same-origin" style="position:fixed; top:0; left:0; bottom:0; right:0; width:100%; height:100%; border:none; margin:0; padding:0; overflow:hidden; z-index:999999;"></iframe>',
        unsafe_allow_html=True
    )
    sleep_time = 10
    st.session_state.page = 'dashboard'

time.sleep(sleep_time)
st.rerun()
