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
.stApp { background-color: #0e1117; }
.metric-card { background-color: #262730; padding: 20px; border-radius: 10px; border: 1px solid #41444e; }
.metric-value { font-size: 2.5rem; font-weight: bold; color: #ffffff; }
.metric-label { font-size: 1rem; color: #a0a0a0; }
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
# --- Main Streamlit Logic ---
st.title("⚡ Real-Time Sensor Dashboard")
# Check Config
if config.PUSHER_KEY == "YOUR_PUSHER_KEY_HERE":
    st.error("⚠️ Please update `config.py` with your actual Pusher Credentials!")
    st.stop()
# Initialize Session State for Dataframe (View State)
if 'sensor_df' not in st.session_state:
    st.session_state.sensor_df = pd.DataFrame(columns=['timestamp', 'room', 'temperature', 'humidity'])
# Process new data from queue
new_data_list = []
while not data_queue.empty():
    new_data_list.append(data_queue.get())
if new_data_list:
    new_df = pd.DataFrame(new_data_list)
    new_df = new_df[['timestamp', 'room', 'temperature', 'humidity']]
    st.session_state.sensor_df = pd.concat([st.session_state.sensor_df, new_df], ignore_index=True)
    # Limit history
    if len(st.session_state.sensor_df) > 1000:
        st.session_state.sensor_df = st.session_state.sensor_df.iloc[-1000:]
# Sidebar
with st.sidebar:
    st.header("Configuration")
    selected_room = st.selectbox("Select Room Filter", ["All Rooms"] + [f"Room {i}" for i in range(1, 11)])
    if st.button("Clear History"):
        st.session_state.sensor_df = pd.DataFrame(columns=['timestamp', 'room', 'temperature', 'humidity'])
        st.rerun()
    st.markdown("---")
    st.text("Logs are printed to terminal.")
# Filtering
df = st.session_state.sensor_df.copy()
if selected_room != "All Rooms":
    df = df[df['room'].astype(str) == selected_room]
# Layout
if not df.empty:
    latest = df.iloc[-1]
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">Latest Update</div><div class="metric-value" style="font-size: 1.5rem">{latest["timestamp"].strftime("%H:%M:%S")}</div><div class="metric-label">{latest["room"]}</div></div>',
            unsafe_allow_html=True)
    with col2:
        color = "#ff4b4b" if float(latest['temperature']) > 25 else "#00c0f2"
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">Temperature</div><div class="metric-value" style="color: {color}">{latest["temperature"]}°C</div></div>',
            unsafe_allow_html=True)
    with col3:
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">Humidity</div><div class="metric-value" style="color: #00c0f2">{latest["humidity"]}%</div></div>',
            unsafe_allow_html=True)
    st.subheader("📈 Live Trends")
    tab1, tab2 = st.tabs(["Temperature", "Humidity"])
    with tab1:
        st.line_chart(df, x='timestamp', y='temperature', color='room', height=400)
    with tab2:
        st.line_chart(df, x='timestamp', y='humidity', color='room', height=400)

    with st.expander("View Raw Data"):
        st.dataframe(df.sort_values(by='timestamp', ascending=False), use_container_width=True)
else:
    st.info("Waiting for data... (Check terminal for connection logs)")
    st.markdown("""
    **Troubleshooting:**
    1. Ensure `config.py` has valid keys.
    2. Ensure the Sender script is running.
    3. Check if the Sender writes to **exact** channels: `room-1`, `room-2`, etc.
    4. Check if the Sender uses event name: `new-message`.
    """)
time.sleep(1)
st.rerun()