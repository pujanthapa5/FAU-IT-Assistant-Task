# Lab Environment Monitor Dashboard

A Python-based Streamlit dashboard that provides real-time monitoring of laboratory environment metrics (temperature and humidity). The system integrates with live sensor feeds, dynamic web scrapers, and external display streams to automatically rotate through vital laboratory information, designed efficiently for large-screen formats.

## Core Features

1. **Live Sensor Dashboard**: Real-time graphing and visualization of laboratory environments (Temp & Humidity trends) managed through Pusher websockets.
2. **Event Board**: Scrapes and prominently displays the latest upcoming Physics Colloquium events sourced directly from the FAU Physics Department.
3. **Web Rotation**: Operates on an automatic timer to loop into full-screen interactive web views of internal department portals.
4. **Screenshot Streaming**: Allows laboratory PCs to broadcast "Live View" active window / specified region screenshots directly onto the Streamlit UI dashboard seamlessly.

## File Architecture

- `dashboard.py`: The primary Streamlit frontend application. Handles the looped routing between the sensor data visualizer, event views, and external iframes dynamically without caching bottlenecks.
- `receiver.py`: A multithreaded listener utilizing `pysher` to ingest WebSocket real-time messages and funnel them into the dashboard's `queue.Queue`.
- `event_scraper.py`: A `BeautifulSoup` integration that parses live academic colloquium directories to generate the event info slides automatically. 
- `sender_screenshot.py`: A standalone utility that can be run on active laboratory workstations. It captures active screen sections, uploads them onto Cloudflare R2 bucket storage via `boto3`, and alerts the central dashboard.
- `config.py`: Local configuration holding needed API keys.

## Getting Started

### 1. Install Dependencies

Install all core web and processing packages:
```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Ensure `config.py` is present in the root directory equipped with your required secrets:
- Pusher App IDs, Cluster, & Secrets.
- Cloudflare R2 Bucket configuration strings.

### 3. Launch the Dashboard

Run the main dashboard app in your environment:
```bash
streamlit run dashboard.py
```
> Wait a few moments for the dashboard to automatically initialize websocket connections. It rotates slides indefinitely.

### 4. (Optional) Run the Screenshot Tool
To start casting visual captures of specific monitors or windows into the main dashboard:
```bash
python sender_screenshot.py
```
You will be prompted to select Region or Window capture profiles via an interactive terminal/GUI mix.
