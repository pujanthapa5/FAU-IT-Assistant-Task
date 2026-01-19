import streamlit as st
import pandas as pd
import time
from datetime import datetime
import queue
import logging
from receiver import PusherSensorReceiver
import config

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
        div.block-container {padding-top: 1rem;} /* Moves data up to use all space */
    </style>
""", unsafe_allow_html=True)


# --- Thread-Safe Data Handling ---
# We use st.cache_resource to create a global queue that persists across reruns
# and is accessible safely from the background thread.
@st.cache_resource
def get_data_queue():
    return queue.Queue()


# Get the shared queue instance
data_queue = get_data_queue()


# Callback function (Runs in Background Thread)
def on_message_received(data):
    # IMPORTANT: Do not use st.session_state or st.write here!
    # We just push to the queue.
    data['timestamp'] = datetime.now()
    data_queue.put(data)


# --- Receiver Setup ---
@st.cache_resource
def get_receiver():
    # Make sure we use INFO level logging to see connection status in console
    receiver = PusherSensorReceiver(
        api_key=config.PUSHER_KEY,
        cluster=config.PUSHER_CLUSTER,
        log_level=logging.INFO
    )

    channels = [f'room-{i}' for i in range(1, 11)]

    # Start connection
    receiver.connect(channels, on_message_received)
    return receiver


# Start Receiver
receiver = get_receiver()

if 'history' not in st.session_state: st.session_state.history = []
if 'latest' not in st.session_state: st.session_state.latest = {}

# 3. Memory Protection (Capping the data)
while not data_queue.empty():
    item = data_queue.get()
    room = item.get('room')
    if room:
        st.session_state.latest[room] = item
        st.session_state.history.append([item['timestamp'], room, item['temperature'], item['humidity']])

    # 🚨 HARD LIMIT: Only keep 50 rows. Without PyArrow, this is the safest size.
    if len(st.session_state.history) > 50:
        st.session_state.history = st.session_state.history[-50:]

# 4. Simple Kiosk Display
st.title("🧪 Lab Sensor Live Analytics")
rooms = ["Room 1", "Room 2", "Room 3"]
cols = st.columns(3)

# Build a simple dataframe for charts (fast enough without pyarrow at 50 rows)
df = pd.DataFrame(st.session_state.history, columns=["Time", "Room", "Temp", "Hum"])

for i, room in enumerate(rooms):
    with cols[i]:
        room_data = st.session_state.latest.get(room)
        if room_data:
            # Big numbers for the hall
            st.metric(label=f"📍 {room}", value=f"{room_data['temperature']}°C", delta=f"{room_data['humidity']}% Hum")

            # Simple line chart (Native Streamlit = Low CPU)
            room_df = df[df['Room'] == room]
            if not room_df.empty:
                st.line_chart(room_df.set_index('Time')['Temp'], height=200)
        else:
            st.info(f"Connecting to {room}...")

# 5. Heartbeat (Refresh every 5 seconds)
time.sleep(5)
st.rerun()
