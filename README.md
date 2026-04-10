# Sensor & Event Dashboard

This project is a Python-based lab monitor dashboard that displays real-time laboratory environment metrics (temperature and humidity), streams screenshots, and scrapes and displays upcoming physics colloquium events.

## Project Structure

- `dashboard.py`: The entry point of the Streamlit application. It handles routing and displaying the main dashboard (sensor readings and charts), event information (from the FAU physics website), and a fullscreen mode slide (visiting the physics website directly). The pages switch effectively in a continuous loop.
- `config.py`: Configuration file holding secrets and API keys for Pusher (websocket service for real-time messaging) and Cloudflare R2 (S3-compatible object storage for uploading screenshots).
- `event_scraper.py`: A web scraper built with `requests` and `BeautifulSoup`. It automatically fetches upcoming physics colloquium events from the FAU department website to be periodically shown on the Streamlit dashboard as an "Info" slide.
- `receiver.py`: A WebSocket client built around `pysher` to receive real-time push events from Pusher channels. It listens to sensor readings for various rooms and screenshot notifications, passing received messages to the Streamlit application's state queue.
- `sender_screenshot.py`: A utility script to capture screenshots from specific windows, fullscreen, or drawn regions. It captures the screen, uploads the temporary image to Cloudflare R2 to generate a public URL, and publishes the image URL back to the main dashboard through Pusher.

## Requirements

The project uses a mix of data and UI components. Ensure you have the required libraries installed:

```bash
pip install streamlit plotly requests beautifulsoup4 pysher boto3 pyautogui pygetwindow
```

## Usage

### 1. Running the Dashboard
You can start the real-time visual dashboard by running:
```bash
streamlit run dashboard.py
```
This UI will rotate between showing live sensor charts, scraped physics events, and the fullscreen physics website.

### 2. Running the Screenshot Capture Tool
To stream live visual captures to the dashboard, run the supplementary screenshot sender utility:
```bash
python sender_screenshot.py
```
You will be prompted with an interactive menu to choose your screenshot source (e.g., Full Screen, Active Window, or Selected Region). This script will then capture, upload, and push those updates over the configured `config.py` endpoints for `dashboard.py` to pick up.
