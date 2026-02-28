import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
import re

BASE_URL = 'https://www.physics.nat.fau.eu/allevents/'

def parse_event_date(date_str):
    date_str = date_str.strip()
    for fmt in ('%d.%m.%Y', '%B %d, %Y', '%b %d, %Y'):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass
    return None

def extract_speaker_from_text(text):
    patterns = [
        r'(?:von|by):\s*((?:Herrn|Frau|Prof\.?|Dr\.?)\s+[A-Z][a-z\w\.]+(?:\s+[A-Z][a-z\w\.]+)*)',
        r'Speaker[:\s]+([A-Z][a-zA-Z\s\.\-]+)',
        r'(Prof\.?\s*Dr\.?\s+[\w\s\.\-]+?)(?:\s*[û\-]|\s*,|\s*\n)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            speaker = match.group(1).strip()
            speaker = re.sub(r'\bHerrn\b', 'Herr', speaker, flags=re.IGNORECASE)
            return speaker
    return 'N/A'

def fetch_event_details(event_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(event_url, timeout=10, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # 1. Title from span
        title_span = soup.find('span', {'aria-current': 'page', 'class': 'active', 'itemprop': 'name'})
        title = title_span.get_text(strip=True) if title_span else 'N/A'

        # 2. Location from span
        loc_span = soup.find('span', itemprop='location')
        location_val = loc_span.get_text(strip=True).replace('Location:', '').strip() if loc_span else 'N/A'

        # 3. Start date and end date from meta
        start_meta = soup.find('meta', itemprop='startDate')
        end_meta = soup.find('meta', itemprop='endDate')
        
        start_date_str = start_meta.get('content', 'N/A') if start_meta else 'N/A'
        end_date_str = end_meta.get('content', 'N/A') if end_meta else 'N/A'

        date_val, time_val = 'N/A', 'N/A'
        parsed_date = None

        if start_date_str != 'N/A':
            try:
                dt_start = datetime.fromisoformat(start_date_str)
                parsed_date = dt_start.date()
                date_val = dt_start.strftime('%d.%m.%Y')
                time_val = dt_start.strftime('%H:%M')
                
                if end_date_str != 'N/A':
                    dt_end = datetime.fromisoformat(end_date_str)
                    time_val += f" - {dt_end.strftime('%H:%M')}"
            except Exception:
                date_val = start_date_str

        categories_val = 'N/A'
        body = soup.get_text()
        speaker = extract_speaker_from_text(body)

        title = title.replace('\n', ' ').strip()
        # Use regex to get only the detail after the hyphen/dash
        # Matches any of: - (hyphen), – (en-dash), — (em-dash) followed by spaces
        parts = re.split(r'\s*[\-\–\—]\s*', title)
        if len(parts) > 1:
            title = parts[-1]
        
        speaker = speaker.replace('\n', ' ').strip()

        return {
            'title': title,
            'speaker': speaker,
            'location': location_val,
            'time': time_val,
            'date_str': date_val,
            'date': parsed_date,
            'url': event_url,
            'categories': categories_val,
            'start_date': start_date_str,
            'end_date': end_date_str
        }
    except Exception as e:
        print(f"Error fetching {event_url}: {e}")
        return None

def fetch_upcoming_events(n=1):
    today = date.today()
    all_events = []
    
    months_to_check = []
    now = datetime.now()
    # Check current month and next 2 months
    for delta in range(3):
        m = now.month + delta
        y = now.year
        while m > 12:
            m -= 12
            y += 1
        months_to_check.append((y, m))

    seen_urls = set()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    for year, month in months_to_check:
        url = f'https://www.physics.nat.fau.eu/allevents/?cal-year={year}&cal-month={month:02d}'
        try:
            resp = requests.get(url, timeout=10, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')

            # Broaden search to ensure we catch colloquiums even if the URL structure changes slightly
            links = soup.select('a[href*="/events/"]')
            for link in links:
                href = link.get('href')
                if not href or href in seen_urls:
                    continue
                
                # Filter for Physics Colloquium in the URL or Text
                text = link.get_text().lower()
                is_kolloquium = "physikalisches" in text and "kolloquium" in text
                is_kolloquium_url = "physikalisches-kolloquium-" in href.lower()
                
                if not (is_kolloquium or is_kolloquium_url):
                    continue

                clean_href = href.split('#')[0].rstrip('/')
                if clean_href in seen_urls:
                    continue
                seen_urls.add(clean_href)

                details = fetch_event_details(clean_href)
                if details and details.get('date') and details['date'] >= today:
                    all_events.append(details)

        except Exception as e:
            print(f"Error fetching directory for {year}-{month}: {e}")

    # Sort by date
    all_events.sort(key=lambda x: x['date'] if x['date'] else date.max)

    # Deduced unique and limit to n
    unique_events = []
    final_seen = set()
    for ev in all_events:
        if ev['url'] not in final_seen:
            unique_events.append(ev)
            final_seen.add(ev['url'])
            if len(unique_events) >= n:
                break

    return unique_events


if __name__ == "__main__":
    print(f"Fetching events starting from {date.today()} (including current month past events)...")
    events = fetch_upcoming_events(n=2)
    if not events:
        print("No matches found.")
    for i, ev in enumerate(events, 1):
        print(f"\nEvent {i}:")
        print(f"  Title:    {ev.get('title')}")
        print(f"  Speaker:  {ev.get('speaker')}")
        print(f"  Date:     {ev.get('date_str')} ({ev.get('date')})")
        print(f"  Time:     {ev.get('time')}")
        print(f"  Location: {ev.get('location')}")
        print(f"  URL:      {ev.get('url')}")
