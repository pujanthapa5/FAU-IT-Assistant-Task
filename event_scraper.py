# event_scraper.py
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Event:
    title: str
    speaker: str
    location: str
    time: str
    date_str: str
    date: Optional[date]
    url: str
    categories: str = "N/A"
    start_date: str = "N/A"
    end_date: str = "N/A"


class EventScraper:
    """
    Scrapes upcoming physics colloquium events from the FAU physics website.

    Usage
    -----
    scraper = EventScraper()
    events  = scraper.fetch_upcoming(n=2)
    """

    BASE_URL = "https://www.physics.nat.fau.eu/allevents/"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36"
        )
    }
    _DATE_FORMATS = ("%d.%m.%Y", "%B %d, %Y", "%b %d, %Y")
    _SPEAKER_PATTERNS = [
    r"(?:von|by):\s*((?:Herrn|Frau|Prof\.?|Dr\.?)\s+[A-Z][\wäöüÄÖÜß\-\.]+(?:\s+[A-Z][\wäöüÄÖÜß\-\.]+)*)",
    r"Speaker[:\s]+([A-Z][\wäöüÄÖÜß\s\.\-]+)",
    r"(Prof\.?\s*Dr\.?\s+[A-Z][\wäöüÄÖÜß\.\-]+(?:\s+[A-Z][\wäöüÄÖÜß\.\-]+)*)(?:\s*[-–]|\s*,|\s*\n)",
]

    # ----------------------------------------------------------------- public
    def fetch_upcoming(self, n: int = 1) -> List[Event]:
        """Return the next *n* colloquium events starting from today."""
        today = date.today()
        seen_urls: set = set()
        all_events: List[Event] = []

        for year, month in self._months_to_check():
            url = f"{self.BASE_URL}?cal-year={year}&cal-month={month:02d}"
            all_events.extend(
                self._scrape_month(url, today, seen_urls)
            )

        all_events.sort(key=lambda e: e.date or date.max)

        unique: List[Event] = []
        final_seen: set = set()
        for ev in all_events:
            if ev.url not in final_seen:
                unique.append(ev)
                final_seen.add(ev.url)
                if len(unique) >= n:
                    break
        return unique

    # --------------------------------------------------------------- internal
    @staticmethod
    def _months_to_check(lookahead: int = 3):
        now = datetime.now()
        for delta in range(lookahead):
            m = now.month + delta
            y = now.year
            while m > 12:
                m -= 12
                y += 1
            yield y, m

    def _scrape_month(
        self, url: str, today: date, seen_urls: set
    ) -> List[Event]:
        events: List[Event] = []
        try:
            resp = requests.get(url, timeout=10, headers=self._HEADERS)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for link in soup.select('a[href*="/events/"]'):
                href = link.get("href", "")
                text = link.get_text().lower()

                is_kolloquium = (
                    "physikalisches" in text and "kolloquium" in text
                ) or "physikalisches-kolloquium-" in href.lower()

                if not is_kolloquium:
                    continue

                clean_href = href.split("#")[0].rstrip("/")
                if clean_href in seen_urls:
                    continue
                seen_urls.add(clean_href)

                ev = self._fetch_event_details(clean_href)
                if ev and ev.date and ev.date >= today:
                    events.append(ev)

        except Exception as exc:
            print(f"Error fetching {url}: {exc}")
        return events

    def _fetch_event_details(self, event_url: str) -> Optional[Event]:
        try:
            resp = requests.get(event_url, timeout=10, headers=self._HEADERS)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            title = self._extract_title(soup)
            location = self._extract_location(soup)
            date_val, time_val, parsed_date = self._extract_datetime(soup)
            speaker = self._extract_speaker(soup.get_text())

            start_meta = soup.find("meta", itemprop="startDate")
            end_meta = soup.find("meta", itemprop="endDate")

            return Event(
                title=title,
                speaker=speaker,
                location=location,
                time=time_val,
                date_str=date_val,
                date=parsed_date,
                url=event_url,
                start_date=start_meta.get("content", "N/A") if start_meta else "N/A",
                end_date=end_meta.get("content", "N/A") if end_meta else "N/A",
            )
        except Exception as exc:
            print(f"Error fetching {event_url}: {exc}")
            return None

    # -------------------------------------------------------- extraction helpers
    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        span = soup.find(
            "span",
            {"aria-current": "page", "class": "active", "itemprop": "name"},
        )
        raw = span.get_text(strip=True) if span else "N/A"
        raw = raw.replace("\n", " ").strip()
        parts = re.split(r"\s*[\-\–\—]\s*", raw)
        if len(parts) > 2:
            parts = [parts[0], '-'.join(parts[1:])]
        return parts[-1] if len(parts) > 1 else raw

    @staticmethod
    def _extract_location(soup: BeautifulSoup) -> str:
        span = soup.find("span", itemprop="location")
        if span:
            return span.get_text(strip=True).replace("Location:", "").strip()
        return "N/A"

    @staticmethod
    def _extract_datetime(soup: BeautifulSoup):
        start_meta = soup.find("meta", itemprop="startDate")
        end_meta = soup.find("meta", itemprop="endDate")
        start_str = start_meta.get("content", "N/A") if start_meta else "N/A"
        end_str = end_meta.get("content", "N/A") if end_meta else "N/A"

        if start_str == "N/A":
            return "N/A", "N/A", None

        try:
            dt_start = datetime.fromisoformat(start_str)
            parsed_date = dt_start.date()
            date_val = dt_start.strftime("%d.%m.%Y")
            time_val = dt_start.strftime("%H:%M")

            if end_str != "N/A":
                dt_end = datetime.fromisoformat(end_str)
                time_val += f" - {dt_end.strftime('%H:%M')}"

            return date_val, time_val, parsed_date
        except Exception:
            return start_str, "N/A", None

    def _extract_speaker(self, body_text: str) -> str:
        for pattern in self._SPEAKER_PATTERNS:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                speaker = match.group(1).strip()
                print(speaker)
                speaker = re.sub(r"\bHerrn\b", "Herr", speaker, flags=re.IGNORECASE)
                return speaker.replace("\n", " ").strip()
        return "N/A"


# ── CLI helper ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    scraper = EventScraper()
    print(f"Fetching events from {date.today()} …")
    events = scraper.fetch_upcoming(n=2)
    if not events:
        print("No matches found.")
    for i, ev in enumerate(events, 1):
        print(f"\nEvent {i}:")
        print(f"  Title:    {ev.title}")
        print(f"  Speaker:  {ev.speaker}")
        print(f"  Date:     {ev.date_str} ({ev.date})")
        print(f"  Time:     {ev.time}")
        print(f"  Location: {ev.location}")
        print(f"  URL:      {ev.url}")
