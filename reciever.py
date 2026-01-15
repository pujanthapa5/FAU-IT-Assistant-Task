import pysher
from pysher.connection import Connection
import sys
import time
import logging
import json
import threading

import config


# Monkey patch pysher.connection.Connection to handle new websocket-client arguments
# This needs to run once when the module is imported
def _apply_patches():
    if getattr(Connection, '_is_patched', False):
        return
    original_on_open = Connection._on_open

    def new_on_open(self, ws):
        original_on_open(self)

    Connection._on_open = new_on_open
    original_on_message = Connection._on_message

    def new_on_message(self, ws, message):
        original_on_message(self, message)

    Connection._on_message = new_on_message
    original_on_error = Connection._on_error

    def new_on_error(self, ws, error):
        original_on_error(self, error)

    Connection._on_error = new_on_error
    original_on_close = Connection._on_close

    def new_on_close(self, ws, close_status_code, close_msg):
        original_on_close(self, close_status_code, close_msg)

    Connection._on_close = new_on_close

    Connection._is_patched = True


# Apply patches immediately
_apply_patches()


class PusherSensorReceiver:
    def __init__(self, api_key, cluster, log_level=logging.INFO):
        self.api_key = api_key
        self.cluster = cluster
        self.pusher = None
        self.channels = []
        self.data_callback = None
        self._setup_logging(log_level)

    def _setup_logging(self, level):
        root = logging.getLogger()
        root.setLevel(level)
        # Avoid adding multiple handlers if instantiated multiple times
        if not root.handlers:
            ch = logging.StreamHandler(sys.stdout)
            root.addHandler(ch)

    def connect(self, channel_names, on_data_received):
        """
        Connect to Pusher and subscribe to the specified channels.

        :param channel_names: List of channel names to subscribe to (e.g., ['room-1', 'room-2'])
        :param on_data_received: Callback function that accepts a single argument (the data dict)
        """
        self.channel_names = channel_names
        self.data_callback = on_data_received

        self.pusher = pysher.Pusher(self.api_key, cluster=self.cluster)
        self.pusher.connection.bind('pusher:connection_established', self._on_connection_established)
        self.pusher.connect()

    def _on_connection_established(self, data):
        logging.info("Connection established. Subscribing to channels...")
        for name in self.channel_names:
            channel = self.pusher.subscribe(name)
            channel.bind('new-message', self._handle_message)
            self.channels.append(channel)
            logging.info(f"Subscribed to '{name}'")

        logging.info("Listening for messages...")

    def _handle_message(self, *args, **kwargs):
        # args[0] is the message data string
        try:
            raw_data = args[0]
            # logging.debug(f"Raw data received: {raw_data}")

            # Parse JSON (handling potential double encoding)
            if isinstance(raw_data, str):
                data = json.loads(raw_data)
            else:
                data = raw_data
            if isinstance(data, str):  # Double encoded check
                data = json.loads(data)

            # Invoke the user callback with the parsed data
            if self.data_callback:
                self.data_callback(data)
        except Exception as e:
            logging.error(f"Error processing message: {e}")

    def disconnect(self):
        if self.pusher:
            self.pusher.disconnect()

    def run_forever(self):
        """
        Blocking call to keep the script running.
        Useful if this is the main thread.
        """
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.disconnect()