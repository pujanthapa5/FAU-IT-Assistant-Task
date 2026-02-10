import streamlit as st
import time
from datetime import datetime
import queue
import logging
from reciever import PusherSensorReceiver
import config

import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Configure page
st.set_page_config(
    page_title="Sensor Dashboard",
    page_icon="🌡️",
    layout="wide"
)

# 5. Heartbeat (Refresh every 5 seconds)
# Using standard st.rerun() loop as requested

st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        div.block-container {padding-top: 1rem;} /* Moves data up to use all space */
    </style>
""", unsafe_allow_html=True)

# Use session_state or a normal global variable instead of caching
if 'data_queue' not in st.session_state:
    st.session_state.data_queue = queue.Queue()

data_queue = st.session_state.data_queue


# Callback function (Runs in Background Thread)
def on_message_received(data):
    # IMPORTANT: Do not use st.session_state or st.write here!
    # We just push to the queue.
    try:
        # Debug logging to file to verify callback execution
        with open("dashboard_debug.log", "a") as f:
            f.write(f"{datetime.now()}: Received {data}\n")
    except Exception as e:
        pass

    data['timestamp'] = datetime.now()
    data_queue.put(data)


if 'receiver' not in st.session_state:
    receiver = PusherSensorReceiver(
        api_key=config.PUSHER_KEY,
        cluster=config.PUSHER_CLUSTER,
        log_level=logging.INFO
    )
    channels = [f'room-{i}' for i in range(1, 4)]
    receiver.connect(channels, on_message_received)
    st.session_state.receiver = receiver
else:
    receiver = st.session_state.receiver

if 'history' not in st.session_state: st.session_state.history = []
if 'latest' not in st.session_state: st.session_state.latest = {}
if 'page' not in st.session_state: st.session_state.page = 'dashboard'

# 3. Memory Protection (Capping the data)
while not data_queue.empty():
    item = data_queue.get()
    room = item.get('room')
    if room:
        st.session_state.latest[room] = item
        # Store as dict directly for Altair
        st.session_state.history.append({
            "Time": item['timestamp'],
            "Room": room,
            "Temp": item['temperature'],
            "Hum": item['humidity']
        })

    # 🚨 HARD LIMIT: Only keep 50 rows. Without PyArrow, this is the safest size.
    if len(st.session_state.history) > 50:
        st.session_state.history = st.session_state.history[-50:]

# 5. Heartbeat (Refresh every 5 seconds)

# --- Configuration ---
TEMP_RANGE = (18, 30)
HUM_RANGE = (30, 60)

# --- Custom Header ---
st.markdown(
    "<h1 style='text-align:center;'>🌡️ Lab Environment Monitor</h1>",
    unsafe_allow_html=True
)
st.markdown(
    f"<p style='text-align:center;'>Last Update: {datetime.now().strftime('%H:%M:%S')}</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# Build a simple list of dicts (fast enough without pyarrow at 50 rows)
# History contains 'room-1', 'room-2' etc. as it comes directly from data queue
# We just use the list directly
history_data = st.session_state.history


def get_status(value, min_val, max_val):
    """Returns status text and icon based on range."""
    if min_val <= value <= max_val:
        return "OK", "✅"
    # Simple logic: slightly out = warning, far out = alert?
    if value < min_val - 5 or value > max_val + 5:
        return "ALERT", "🚨"
    return "WARNING", "⚠️"


def make_split_charts(data):
    times = [d['Time'].strftime("%H:%M:%S") for d in data]
    temps = [d['Temp'] for d in data]
    hums = [d['Hum'] for d in data]

    # Two rows, shared x-axis
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.20
    )

    # Temperature Trend (Top)
    fig.add_trace(
        go.Scatter(
            x=times, y=temps,
            mode="lines+markers",
            line=dict(color="orange", width=5),
            marker=dict(size=8),
            name="Temperature Trend"
        ),
        row=1, col=1
    )

    # Humidity Trend (Bottom)
    fig.add_trace(
        go.Scatter(
            x=times, y=hums,
            mode="lines+markers",
            line=dict(color="blue", width=5),
            marker=dict(size=8),
            name="Humidity Trend"
        ),
        row=2, col=1
    )

    # Minimal layout (safe for older Plotly)
    fig.update_layout(
        height=900,
        showlegend=False
    )

    # Titles for each subplot (safe method)
    fig['layout']['annotations'] = [
        dict(
            x=0.5, y=1.05,
            xref='paper', yref='paper',
            text='Temperature Trend',
            showarrow=False,
            font=dict(size=20)
        ),
        dict(
            x=0.5, y=0.45,
            xref='paper', yref='paper',
            text='Humidity Trend',
            showarrow=False,
            font=dict(size=20)
        )
    ]

    return fig


# Main Display Loop
if st.session_state.page == 'dashboard':
    cols = st.columns(3)

    # We want exactly Room 1, Room 2, Room 3 in order
    # Room 1 has a special title
    ordered_rooms = [("Bilddynamik Room 01.103", "room-1"), ("Lab 2", "room-2"), ("Lab 3", "room-3")]

    for i, (room_display_name, room_id) in enumerate(ordered_rooms):
        with cols[i]:
            st.markdown(f"## {room_display_name}")

            room_data = st.session_state.latest.get(room_id)

            if room_data:
                temp = room_data['temperature']
                hum = room_data['humidity']

                # Big Numbers using User's HTML (2 decimal places)
                st.markdown(
                    f"""
                    <div style="font-size: 55px;">
                        🌡️ {temp:.2f} °C <br>
                        💧 {hum:.2f} %
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # Filter history for this room (list comprehension instead of pandas)
                room_data_list = [d for d in history_data if d['Room'] == room_id]

                if room_data_list:
                    # Split Charts - Plotly, static
                    # staticPlot: True disables all interactions (zoom, pan, hover)
                    st.plotly_chart(make_split_charts(room_data_list), use_container_width=True, config={'staticPlot': True})

            else:
                st.warning("Connecting...")

elif st.session_state.page == 'info':
    # Info Screen
    st.markdown(
        """
        <style>
        .info-container {
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            height: 120vh;
            text-align: center;
            font-family: 'Inter', sans-serif;
        }
        .info-text {
            margin-bottom: 20px;
        }
        .speaker {
            font-size: 85px;
            font-weight: bold;
            color: #00D1FF;
        }
        .title {
            font-size: 65px;
            font-style: italic;
            color: #4DA8FF;
            margin: 55px;
        }
        .location {
            font-size: 50px;
            color: #FFD166;
        }
        </style>
        <div class="info-container">
            <div class="info-text speaker">Sprecher/Speaker: Prof. Dr. Christophe Szwaj, Université de Lille</div>
            <div class="info-text title">Titel/Title: Shot Electro-Optic Detection of THz Pulses</div>
            <div class="info-text location">Ort/Location: Hörsaal A (Biologie)/lecture hall A (Biology)</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# Toggle page logic for next run
if st.session_state.page == 'dashboard':
    st.session_state.page = 'info'
else:
    st.session_state.page = 'dashboard'

time.sleep(10)  # Refresh rate
st.rerun()
