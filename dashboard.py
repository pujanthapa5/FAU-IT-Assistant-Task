# dashboard.py
import logging
import queue
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import config
from event_scraper import Event, EventScraper
from receiver import PusherSensorReceiver

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(page_title="Sensor Dashboard", page_icon="🌡️", layout="wide")
st.markdown(
    """
    <style>
        #MainMenu {visibility: hidden;}
        footer     {visibility: hidden;}
        header     {visibility: hidden;}
        div.block-container {padding-top: 1rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

TEMP_RANGE = (18, 30)
HUM_RANGE = (30, 60)
MAX_HISTORY = 10_000
REFRESH_INTERVAL_S = 20
EVENT_CACHE_TTL_S = 86_400  # 24 h
SCREENSHOT_TIMEOUT_S = 300   # 5 min


# ══════════════════════════════════════════════════════════════════════════════
# Data models
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SensorReading:
    room: str
    temperature: float
    humidity: float
    timestamp: datetime


@dataclass
class ScreenshotState:
    active: bool = False
    url: str = ""
    window_title: str = ""
    timestamp: Optional[datetime] = None
    last_signal: float = 0.0


# ══════════════════════════════════════════════════════════════════════════════
# State manager (single source of truth for st.session_state)
# ══════════════════════════════════════════════════════════════════════════════

class DashboardState:
    """
    Thin wrapper around st.session_state that centralises all read/write access.
    Keeps business logic out of the rendering layer.
    """

    # ------------------------------------------------------------------ init
    def _ensure(self, key: str, default):
        if key not in st.session_state:
            st.session_state[key] = default

    def initialise(self) -> None:
        self._ensure("data_queue", queue.Queue())
        self._ensure("history", [])
        self._ensure("latest", {})
        self._ensure("page", "dashboard")
        self._ensure("screenshot", ScreenshotState())
        self._ensure("events", [])
        self._ensure("event_index", 0)
        self._ensure("last_fetched", 0.0)

    # ---------------------------------------------------------------- getters
    @property
    def data_queue(self) -> queue.Queue:
        return st.session_state.data_queue

    @property
    def history(self) -> List[dict]:
        return st.session_state.history

    @property
    def latest(self) -> Dict[str, dict]:
        return st.session_state.latest

    @property
    def page(self) -> str:
        return st.session_state.page

    @page.setter
    def page(self, value: str) -> None:
        st.session_state.page = value

    @property
    def screenshot(self) -> ScreenshotState:
        return st.session_state.screenshot

    @property
    def events(self) -> List[Event]:
        return st.session_state.events

    @property
    def event_index(self) -> int:
        return st.session_state.event_index

    # --------------------------------------------------------------- mutators
    def push_message(self, data: dict) -> None:
        data["timestamp"] = datetime.now()
        self.data_queue.put(data)

    def drain_queue(self) -> None:
        while not self.data_queue.empty():
            item = self.data_queue.get()
            self._process_item(item)
        if len(self.history) > MAX_HISTORY:
            st.session_state.history = self.history[-MAX_HISTORY:]

    def _process_item(self, item: dict) -> None:
        room = item.get("room")
        if room:
            self.latest[room] = item
            self.history.append(
                {
                    "Time": item["timestamp"],
                    "Room": room,
                    "Temp": item["temperature"],
                    "Hum": item["humidity"],
                }
            )

        msg_type = item.get("type")
        if msg_type == "screenshot":
            ss = self.screenshot
            ss.active = True
            ss.url = item.get("url", "")
            ss.window_title = item.get("window_title", "Unknown")
            ss.timestamp = item.get("timestamp")
            ss.last_signal = time.time()

        elif msg_type == "screenshot_status":
            ss = self.screenshot
            ss.active = item.get("active", False)
            ss.last_signal = time.time()

    def maybe_expire_screenshot(self) -> None:
        ss = self.screenshot
        if ss.active and time.time() - ss.last_signal > SCREENSHOT_TIMEOUT_S:
            ss.active = False

    def maybe_refresh_events(self) -> None:
        now = time.time()
        if now - st.session_state.last_fetched > EVENT_CACHE_TTL_S or not self.events:
            fetched = EventScraper().fetch_upcoming(n=1)
            if fetched:
                st.session_state.events = fetched
                st.session_state.last_fetched = now

    def advance_event_index(self) -> None:
        st.session_state.event_index += 1

    def toggle_page(self) -> None:
        if self.page == "dashboard":
            if self.events:
                self.page = "info"
            else:
                self.page = "website"
        elif self.page == "info":
            self.page = "website"
        else:
            self.page = "dashboard"

    def history_for_room(self, room_id: str) -> List[dict]:
        return [d for d in self.history if d["Room"] == room_id]


# ══════════════════════════════════════════════════════════════════════════════
# Chart builder
# ══════════════════════════════════════════════════════════════════════════════

class SensorChartBuilder:
    """Creates the dual-subplot temperature/humidity chart for one room."""

    _TICK_FONT_AXIS = dict(size=18, color="lightgray")

    def build(self, data: List[dict], show_header: bool = False) -> go.Figure:
        times, temps, hums = self._aggregate_hourly(data)

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.15)
        fig.add_trace(
            go.Scatter(
                x=times, y=temps, mode="lines+markers",
                line=dict(color="orange", width=2), marker=dict(size=6),
                name="Temperature", cliponaxis=False,
            ),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=times, y=hums, mode="lines+markers",
                line=dict(color="lightblue", width=2), marker=dict(size=6),
                name="Humidity", cliponaxis=False,
            ),
            row=2, col=1,
        )

        start, end = self._x_window()
        x_axis_cfg = dict(
            range=[start, end], dtick=3_600_000, tickformat="%H:%M",
            tickangle=-45, tickfont=self._TICK_FONT_AXIS,
            gridcolor="rgba(255,255,255,0.1)",
        )
        fig.update_xaxes(**x_axis_cfg, row=1, col=1)
        fig.update_xaxes(**x_axis_cfg, row=2, col=1)
        fig.update_yaxes(
            range=[20, 30], dtick=2,
            tickfont=dict(size=18, color="lightgray"),
            gridcolor="rgba(255,255,255,0.1)",
            title=dict(text="Temp (°C)", font=dict(size=16, color="white")),
            row=1, col=1,
        )
        fig.update_yaxes(
            range=[25, 45], dtick=5,
            tickfont=dict(size=18, color="lightgray"),
            gridcolor="rgba(255,255,255,0.1)",
            title=dict(text="Hum (%)", font=dict(size=16, color="white")),
            row=2, col=1,
        )
        fig.update_layout(
            height=1000, showlegend=False,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=120, b=80, l=30, r=40),
        )

        if show_header:
            fig.update_layout(
                annotations=[
                    dict(x=0.5, y=1.05, xref="paper", yref="paper",
                         text="Temperature Trend", showarrow=False,
                         font=dict(size=35, color="white"), xanchor="center"),
                    dict(x=0.5, y=0.45, xref="paper", yref="paper",
                         text="Humidity Trend", showarrow=False,
                         font=dict(size=35, color="white"), xanchor="center"),
                ]
            )

        return fig

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _aggregate_hourly(data: List[dict]):
        from collections import OrderedDict
        hourly: dict = OrderedDict()
        for d in data:
            key = d["Time"].replace(minute=0, second=0, microsecond=0)
            hourly[key] = d
        sorted_keys = sorted(hourly)
        return (
            sorted_keys,
            [hourly[h]["Temp"] for h in sorted_keys],
            [hourly[h]["Hum"] for h in sorted_keys],
        )

    @staticmethod
    def _x_window():
        now = datetime.now()
        end = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return end - timedelta(hours=12), end


# ══════════════════════════════════════════════════════════════════════════════
# Page renderers
# ══════════════════════════════════════════════════════════════════════════════

ROOMS = [
    ("Bilddynamik Room 01.103", "room-1"),
    ("Lab 2",                   "room-2"),
    ("Lab 3",                   "room-3"),
]


class DashboardPage:
    """Renders the live sensor data page."""

    def __init__(self, state: DashboardState) -> None:
        self._state = state
        self._chart = SensorChartBuilder()

    def render(self) -> None:
        st.markdown(
            "<h1 style='text-align:center;'>🌡️ Lab Environment Monitor</h1>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<p style='text-align:center;'>Last Update: {datetime.now():%H:%M:%S}</p>",
            unsafe_allow_html=True,
        )
        st.markdown("---")

        cols = st.columns(3)
        for i, (display_name, room_id) in enumerate(ROOMS):
            with cols[i]:
                self._render_room(display_name, room_id)

    # --------------------------------------------------------------- helpers
    def _render_room(self, name: str, room_id: str) -> None:
        st.markdown(f"## {name}")
        data = self._state.latest.get(room_id)
        if not data:
            st.warning("Connecting…")
            return

        temp, hum = data["temperature"], data["humidity"]
        st.markdown(
            f'<div style="font-size:65px;">🌡️ {temp:.2f} °C<br>💧 {hum:.2f} %</div>',
            unsafe_allow_html=True,
        )

        room_hist = self._state.history_for_room(room_id)
        if room_hist:
            st.plotly_chart(
                self._chart.build(room_hist, show_header=(room_id == "room-2")),
                width="stretch",
                config={"staticPlot": True},
            )

        if room_id == "room-1":
            self._render_screenshot_if_active()

    def _render_screenshot_if_active(self) -> None:
        ss = self._state.screenshot
        if not (ss.active and ss.url):
            return
        st.markdown("---")
        st.markdown("### 📸 Live View")
        st.image(
            ss.url,
            caption=f"Captured: {ss.window_title} at {ss.timestamp}",
            use_container_width=True,
        )


class InfoPage:
    """Renders the upcoming events page."""

    def __init__(self, state: DashboardState) -> None:
        self._state = state

    def render(self) -> None:
        events = self._state.events
        if not events:
            self._state.page = "dashboard"
            st.rerun()
            return

        ev = events[self._state.event_index % len(events)]
        self._state.advance_event_index()

        st.markdown(
            textwrap.dedent(f"""
                <style>
                .info-container {{ display:flex; flex-direction:column; justify-content:center;
                    align-items:center; min-height:90vh; text-align:center;
                    font-family:'Inter',sans-serif; padding:5vmin;
                    background:radial-gradient(circle at center,#1a1a2e 0%,#0f0f1a 100%);
                    border-radius:20px; margin-top:20px; }}
                .header-title {{ font-size:8vmin; font-weight:bold; color:#ffffff;
                    margin-bottom:5vmin; border-bottom:2px solid #4DA8FF; padding-bottom:2vmin; width:100%; }}
                .event-date  {{ font-size:5vmin; font-weight:bold; color:#FF6B6B; }}
                .event-time  {{ font-size:4vmin; color:#AAD4FF; margin-bottom:4vmin; }}
                .speaker     {{ font-size:8vmin; font-weight:bold; color:#00D1FF; line-height:1.1; }}
                .title       {{ font-size:6vmin; font-style:italic; color:#4DA8FF;
                    margin:6vmin 0; line-height:1.2; text-wrap:balance; }}
                .location    {{ font-size:5vmin; color:#FFD166; }}
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
            unsafe_allow_html=True,
        )


class WebsitePage:
    """Renders a fullscreen website via iframe."""

    def __init__(self, state: DashboardState) -> None:
        self._state = state

    def render(self) -> None:
        st.markdown(
            '<iframe src="https://www.fkp.physik.nat.fau.eu/" style="position:fixed; top:0; left:0; bottom:0; right:0; width:100%; height:100%; border:none; margin:0; padding:0; overflow:hidden; z-index:999999;"></iframe>',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# App bootstrap
# ══════════════════════════════════════════════════════════════════════════════

class SensorDashboardApp:
    """
    Top-level application class.  Wires together the receiver, state manager,
    and page renderers, then drives the Streamlit run-loop.
    """

    def __init__(self) -> None:
        self._state = DashboardState()
        self._state.initialise()
        self._ensure_receiver()

    # ----------------------------------------------------------------- public
    def run(self) -> None:
        self._state.drain_queue()
        self._state.maybe_expire_screenshot()
        self._state.maybe_refresh_events()

        current_page = self._state.page

        if current_page == "dashboard":
            DashboardPage(self._state).render()
        elif current_page == "info":
            InfoPage(self._state).render()
        elif current_page == "website":
            WebsitePage(self._state).render()

        self._state.toggle_page()
        
        if current_page == "website":
            time.sleep(10)
        else:
            time.sleep(REFRESH_INTERVAL_S)
        st.rerun()

    # --------------------------------------------------------------- internal
    def _ensure_receiver(self) -> None:
        if "receiver" not in st.session_state:
            receiver = PusherSensorReceiver(
                api_key=config.PUSHER_KEY,
                cluster=config.PUSHER_CLUSTER,
                log_level=logging.INFO,
            )
            channels = [f"room-{i}" for i in range(1, 4)] + ["screenshot-stream"]
            receiver.connect(channels, self._state.push_message)
            st.session_state.receiver = receiver


# ── Entry point ───────────────────────────────────────────────────────────────
SensorDashboardApp().run()
