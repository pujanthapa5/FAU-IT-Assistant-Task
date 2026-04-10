# receiver.py
import pysher
from pysher.connection import Connection
import sys
import time
import logging
import json
from typing import Callable, List, Optional


def _apply_pysher_patches() -> None:
    """Monkey-patch pysher to handle new websocket-client callback signatures."""
    if getattr(Connection, "_is_patched", False):
        return

    original_on_open = Connection._on_open
    Connection._on_open = lambda self, ws: original_on_open(self)

    original_on_message = Connection._on_message
    Connection._on_message = lambda self, ws, msg: original_on_message(self, msg)

    original_on_error = Connection._on_error
    Connection._on_error = lambda self, ws, err: original_on_error(self, err)

    original_on_close = Connection._on_close
    Connection._on_close = lambda self, ws, code, msg: original_on_close(self, code, msg)

    Connection._is_patched = True


_apply_pysher_patches()


class PusherSensorReceiver:
    """
    Connects to one or more Pusher channels and forwards parsed messages
    to a caller-supplied callback.

    Usage
    -----
    receiver = PusherSensorReceiver(api_key=..., cluster=...)
    receiver.connect(['room-1', 'room-2', 'screenshot-stream'], my_callback)
    """

    def __init__(
        self,
        api_key: str,
        cluster: str,
        log_level: int = logging.INFO,
    ) -> None:
        self.api_key = api_key
        self.cluster = cluster
        self._pusher: Optional[pysher.Pusher] = None
        self._subscribed_channels: list = []
        self._channel_names: List[str] = []
        self._data_callback: Optional[Callable] = None
        self._configure_logging(log_level)

    # ------------------------------------------------------------------ setup
    def _configure_logging(self, level: int) -> None:
        root = logging.getLogger()
        root.setLevel(level)
        if not root.handlers:
            root.addHandler(logging.StreamHandler(sys.stdout))

    # ----------------------------------------------------------------- public
    def connect(self, channel_names: List[str], callback: Callable) -> None:
        """Subscribe to *channel_names* and call *callback* for every message."""
        self._channel_names = channel_names
        self._data_callback = callback

        self._pusher = pysher.Pusher(self.api_key, cluster=self.cluster)
        self._pusher.connection.bind(
            "pusher:connection_established", self._on_connected
        )
        self._pusher.connect()

    def disconnect(self) -> None:
        if self._pusher:
            self._pusher.disconnect()

    def run_forever(self) -> None:
        """Block the calling thread (useful in stand-alone scripts)."""
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.disconnect()

    # --------------------------------------------------------------- internal
    def _on_connected(self, _data) -> None:
        logging.info("Pusher connected – subscribing to channels…")
        for name in self._channel_names:
            ch = self._pusher.subscribe(name)
            ch.bind("new-message", self._handle_message)
            self._subscribed_channels.append(ch)
            logging.info("Subscribed to '%s'", name)

    def _handle_message(self, *args, **_kwargs) -> None:
        try:
            raw = args[0]
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, str):          # double-encoded guard
                data = json.loads(data)
            if self._data_callback:
                self._data_callback(data)
        except Exception as exc:
            logging.error("Error processing message: %s", exc)
