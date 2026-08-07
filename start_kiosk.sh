#!/bin/bash
# Launches Chromium in kiosk mode pointed at the local Streamlit dashboard,
# with flags tuned to avoid the "Aw, Snap!" (error code 5 / OOM) crash on
# Raspberry Pi.

DASHBOARD_URL="http://localhost:8501"   # change if your Streamlit app runs elsewhere

# Wait for the Streamlit server to be ready before launching the browser
until curl -s "$DASHBOARD_URL" > /dev/null; do
  sleep 1
done

chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-dev-shm-usage \
  --disable-gpu-sandbox \
  --disable-software-rasterizer \
  --disable-background-timer-throttling \
  --disable-backgrounding-occluded-windows \
  --disable-renderer-backgrounding \
  --memory-pressure-off \
  --overscroll-history-navigation=0 \
  "$DASHBOARD_URL"
