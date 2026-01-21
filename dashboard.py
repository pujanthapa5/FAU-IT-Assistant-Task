import streamlit as st
import pandas as pd
import time
from datetime import datetime
import queue
import logging
from reciever import PusherSensorReceiver
import config
import altair as alt

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
def get_data_queue_v2():
    return queue.Queue()


# Get the shared queue instance
data_queue = get_data_queue_v2()


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


# --- Receiver Setup ---
@st.cache_resource
def get_receiver_v2():
    # Make sure we use INFO level logging to see connection status in console
    # Note: Streamlit captures stdout, so we should see logs in terminal
    receiver = PusherSensorReceiver(
        api_key=config.PUSHER_KEY,
        cluster=config.PUSHER_CLUSTER,
        log_level=logging.INFO
    )

    channels = [f'room-{i}' for i in range(1, 4)]

    # Start connection
    receiver.connect(channels, on_message_received)
    return receiver


# Start Receiver
receiver = get_receiver_v2()

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

# Build a simple dataframe for charts (fast enough without pyarrow at 50 rows)
# History contains 'room-1', 'room-2' etc. as it comes directly from data queue
df = pd.DataFrame(st.session_state.history, columns=["Time", "Room", "Temp", "Hum"])


def get_status(value, min_val, max_val):
    """Returns status text and icon based on range."""
    if min_val <= value <= max_val:
        return "OK", "✅"
    # Simple logic: slightly out = warning, far out = alert?
    if value < min_val - 5 or value > max_val + 5:
        return "ALERT", "🚨"
    return "WARNING", "⚠️"


def make_dual_axis_chart(data):
    """Creates a dual-axis chart for Temp and Humidity using Altair."""
    base = alt.Chart(data).encode(x=alt.X('Time:T', axis=alt.Axis(title=None, format='%H:%M:%S')))

    line_temp = base.mark_line(color='orange').encode(
        y=alt.Y('Temp:Q', axis=alt.Axis(title='Temp (°C)', titleColor='orange'))
    )

    line_hum = base.mark_line(color='#5276A7').encode(
        y=alt.Y('Hum:Q', axis=alt.Axis(title='Hum (%)', titleColor='#5276A7'))
    )

    return alt.layer(line_temp, line_hum).resolve_scale(y='independent').properties(height=250)


# Main Display Loop
cols = st.columns(3)

# We want exactly Room 1, Room 2, Room 3 in order
# Room 1 has a special title
ordered_rooms = [("Bilddynamik Room 01.103", "room-1"), ("Room 2", "room-2"), ("Room 3", "room-3")]

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
                <div style="font-size:40px;">
                    🌡️ {temp:.2f} °C <br>
                    💧 {hum:.2f} %
                </div>
                """,
                unsafe_allow_html=True
            )

            # Filter history for this room
            room_df = df[df['Room'] == room_id]

            if not room_df.empty:
                # Dual Axis Chart
                st.altair_chart(make_dual_axis_chart(room_df), use_container_width=True)

        else:
            st.warning("Connecting...")

time.sleep(5)  # Refresh rate
st.rerun()
