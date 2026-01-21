import time
import logging
from reciever import PusherSensorReceiver
import config

# Setup basic logging
logging.basicConfig(level=logging.INFO)

def on_message(data):
    print(f"DEBUG DATA RECEIVED: {data}")

def main():
    receiver = PusherSensorReceiver(
        api_key=config.PUSHER_KEY,
        cluster=config.PUSHER_CLUSTER,
        log_level=logging.INFO
    )
    
    # Matching dashboard.py channels
    channels = [f'room-{i}' for i in range(1, 11)]
    
    print("Connecting...")
    receiver.connect(channels, on_message)
    
    print("Waiting for messages (15s)...")
    time.sleep(15)
    print("Done.")

if __name__ == "__main__":
    main()
