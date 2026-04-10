# sender_screenshot.py
import atexit
import logging
import os
import sys
import time
import tkinter as tk
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Tuple

import boto3
import pusher
import pyautogui
import pygetwindow as gw

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

Region = Tuple[int, int, int, int]  # left, top, width, height


# ══════════════════════════════════════════════════════════════════════════════
# Storage
# ══════════════════════════════════════════════════════════════════════════════

class R2Uploader:
    """Uploads files to Cloudflare R2 and returns pre-signed URLs."""

    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        presign_expiry: int = 3600,
    ) -> None:
        self.bucket_name = bucket_name
        self.presign_expiry = presign_expiry
        self._client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
        )

    def upload(self, local_path: str, object_name: Optional[str] = None) -> Optional[str]:
        """Upload *local_path* and return a presigned URL, or None on failure."""
        if object_name is None:
            object_name = os.path.basename(local_path)
        try:
            logging.info("Uploading '%s' → R2 bucket '%s'…", local_path, self.bucket_name)
            self._client.upload_file(local_path, self.bucket_name, object_name)
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": object_name},
                ExpiresIn=self.presign_expiry,
            )
            logging.info("Upload successful.")
            return url
        except Exception as exc:
            logging.error("Upload failed: %s", exc)
            return None


# ══════════════════════════════════════════════════════════════════════════════
# Messaging
# ══════════════════════════════════════════════════════════════════════════════

class ScreenshotPublisher:
    """Publishes screenshot URLs and status events to a Pusher channel."""

    CHANNEL = "screenshot-stream"
    EVENT = "new-message"

    def __init__(self, app_id: str, key: str, secret: str, cluster: str) -> None:
        self._client = pusher.Pusher(
            app_id=app_id, key=key, secret=secret, cluster=cluster, ssl=True
        )

    def publish_screenshot(
        self, url: str, timestamp: str, window_title: str, mode: str
    ) -> None:
        self._trigger(
            {
                "type": "screenshot",
                "url": url,
                "timestamp": timestamp,
                "window_title": window_title,
                "mode": mode,
            }
        )

    def publish_status(self, active: bool) -> None:
        self._trigger(
            {
                "type": "screenshot_status",
                "active": active,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        logging.info("Sent status: %s", "ACTIVE" if active else "INACTIVE")

    def _trigger(self, payload: dict) -> None:
        try:
            self._client.trigger(self.CHANNEL, self.EVENT, payload)
        except Exception as exc:
            logging.error("Pusher trigger failed: %s", exc)


# ══════════════════════════════════════════════════════════════════════════════
# Capture strategies (Strategy pattern)
# ══════════════════════════════════════════════════════════════════════════════

class CaptureStrategy(ABC):
    """Abstract base for screenshot capture strategies."""

    @property
    @abstractmethod
    def label(self) -> str:
        """Human-readable name shown in logs / UI."""

    @abstractmethod
    def get_region(self) -> Optional[Region]:
        """Return the (left, top, width, height) region, or None for full screen."""


class FullScreenCapture(CaptureStrategy):
    label = "Full Screen"

    def get_region(self) -> None:
        return None


class ActiveWindowCapture(CaptureStrategy):
    """Always captures the currently focused window."""

    label = "Active Window"

    def get_region(self) -> Optional[Region]:
        try:
            win = gw.getActiveWindow()
            if win:
                return win.left, win.top, win.width, win.height
        except Exception as exc:
            logging.error("Could not get active window: %s", exc)
        return None


class FixedRegionCapture(CaptureStrategy):
    """Captures a fixed screen region chosen interactively once at startup."""

    def __init__(self, region: Region, title: str = "Selected Region") -> None:
        self._region = region
        self._label = title

    @property
    def label(self) -> str:
        return self._label

    def get_region(self) -> Region:
        return self._region


# ══════════════════════════════════════════════════════════════════════════════
# Tkinter UI helpers
# ══════════════════════════════════════════════════════════════════════════════

class _WindowSelector:
    """Popup for choosing an open window from a list."""

    def __init__(self, parent: tk.Tk) -> None:
        self._top = tk.Toplevel(parent)
        self._top.title("Select a Window")
        self._top.geometry("600x600")
        self._top.attributes("-topmost", True)
        self._selected = None

        tk.Label(
            self._top,
            text="Select a window and click SELECT (or double-click):",
            pady=10, font=("Arial", 10, "bold"),
        ).pack()

        frame = tk.Frame(self._top)
        frame.pack(padx=10, pady=10, fill="both", expand=True)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._listbox = tk.Listbox(
            frame, width=70, height=25,
            yscrollcommand=scrollbar.set, font=("Consolas", 9),
        )
        self._listbox.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar.config(command=self._listbox.yview)

        self._windows = sorted(
            [w for w in gw.getAllWindows() if w.title.strip()],
            key=lambda w: w.title.lower(),
        )
        for w in self._windows:
            self._listbox.insert(tk.END, f" {w.title[:80]}")

        self._listbox.bind("<Double-Button-1>", lambda _e: self._confirm())

        btn = tk.Frame(self._top)
        btn.pack(pady=15)
        tk.Button(btn, text="SELECT", command=self._confirm,
                  width=15, bg="#4CAF50", fg="white").pack(side=tk.LEFT, padx=10)
        tk.Button(btn, text="CANCEL", command=self._top.destroy,
                  width=15).pack(side=tk.LEFT, padx=10)

        self._listbox.focus_set()
        if self._windows:
            self._listbox.selection_set(0)

    def _confirm(self) -> None:
        sel = self._listbox.curselection()
        if sel:
            self._selected = self._windows[sel[0]]
            self._top.destroy()

    def wait(self):
        self._top.focus_force()
        self._top.wait_window()
        return self._selected


class _RegionSelector:
    """Transparent fullscreen overlay for drawing a capture rectangle."""

    def __init__(self, parent: tk.Tk, hint_box: Optional[Region] = None) -> None:
        self._top = tk.Toplevel(parent)
        self._top.attributes("-alpha", 0.3, "-fullscreen", True, "-topmost", True)
        self._top.config(cursor="cross")

        self._canvas = tk.Canvas(self._top, highlightthickness=0, bg="grey")
        self._canvas.pack(fill="both", expand=True)

        if hint_box:
            l, t, w, h = hint_box
            self._canvas.create_rectangle(
                l, t, l + w, t + h, outline="blue", width=2, dash=(4, 4)
            )

        self._sx = self._sy = None
        self._rect = None
        self._selection: Optional[Region] = None

        self._top.bind("<ButtonPress-1>", self._press)
        self._top.bind("<B1-Motion>", self._drag)
        self._top.bind("<ButtonRelease-1>", self._release)
        self._top.bind("<Escape>", lambda _e: self._top.destroy())

    def _press(self, _e) -> None:
        self._sx = self._top.winfo_pointerx()
        self._sy = self._top.winfo_pointery()
        self._rect = self._canvas.create_rectangle(
            self._sx, self._sy, self._sx, self._sy, outline="red", width=2
        )

    def _drag(self, _e) -> None:
        cx, cy = self._top.winfo_pointerx(), self._top.winfo_pointery()
        self._canvas.coords(self._rect, self._sx, self._sy, cx, cy)

    def _release(self, _e) -> None:
        ex, ey = self._top.winfo_pointerx(), self._top.winfo_pointery()
        l, t = min(self._sx, ex), min(self._sy, ey)
        w, h = abs(self._sx - ex), abs(self._sy - ey)
        if w > 5 and h > 5:
            self._selection = (l, t, w, h)
        self._top.destroy()

    def wait(self) -> Optional[Region]:
        self._top.focus_force()
        self._top.wait_window()
        return self._selection


# ══════════════════════════════════════════════════════════════════════════════
# Strategy factory / interactive menu
# ══════════════════════════════════════════════════════════════════════════════

class CaptureModeSelector:
    """Interactive CLI/Tk menu that returns a configured CaptureStrategy."""

    def choose(self) -> CaptureStrategy:
        while True:
            print("\n--- Screenshot Selection ---")
            print("[1] Full Screen")
            print("[2] Active Window (dynamic)")
            print("[3] Select Region")
            print("[4] Select Window then Region")
            print("[q] Quit")
            choice = input("\nChoose: ").strip().lower()

            strategy = self._handle(choice)
            if strategy is not None:
                return strategy
            if choice == "q":
                sys.exit(0)

    def _handle(self, choice: str) -> Optional[CaptureStrategy]:
        if choice == "1":
            return FullScreenCapture()

        if choice == "2":
            strat = ActiveWindowCapture()
            region = strat.get_region()
            if region:
                return strat
            print("Could not identify active window.")
            return None

        if choice == "3":
            return self._pick_region()

        if choice == "4":
            return self._pick_window_region()

        return None

    @staticmethod
    def _pick_region() -> Optional[CaptureStrategy]:
        root = tk.Tk()
        root.withdraw()
        sel = _RegionSelector(root).wait()
        root.destroy()
        if sel:
            return FixedRegionCapture(sel, "Selected Region")
        print("No region selected.")
        return None

    @staticmethod
    def _pick_window_region() -> Optional[CaptureStrategy]:
        root = tk.Tk()
        root.withdraw()
        win = _WindowSelector(root).wait()
        if not win:
            root.destroy()
            return None

        try:
            if win.isMinimized:
                win.restore()
            win.activate()
            time.sleep(1.5)
            hint = (win.left, win.top, win.width, win.height)
            sel = _RegionSelector(root, hint_box=hint).wait()
            root.destroy()
            if sel:
                return FixedRegionCapture(sel, f"Region of {win.title}")
            print("No region selected.")
        except Exception as exc:
            logging.error("Window selection error: %s", exc)
            root.destroy()
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator
# ══════════════════════════════════════════════════════════════════════════════

class ScreenshotCapturePipeline:
    """
    Ties together capture → upload → publish into one reusable pipeline.

    Parameters
    ----------
    strategy   : CaptureStrategy   – how to grab the screen
    uploader   : R2Uploader        – where to store the image
    publisher  : ScreenshotPublisher – how to announce the URL
    interval   : int               – seconds between captures (default 120)
    """

    def __init__(
        self,
        strategy: CaptureStrategy,
        uploader: R2Uploader,
        publisher: ScreenshotPublisher,
        interval: int = 120,
    ) -> None:
        self._strategy = strategy
        self._uploader = uploader
        self._publisher = publisher
        self._interval = interval

    # ----------------------------------------------------------------- public
    def run(self) -> None:
        self._publisher.publish_status(active=True)
        atexit.register(self._publisher.publish_status, False)

        logging.info(
            "Pipeline started. Strategy: '%s'. Interval: %ds.",
            self._strategy.label,
            self._interval,
        )

        while True:
            self._capture_and_send()
            logging.info("Sleeping for %d seconds…", self._interval)
            time.sleep(self._interval)

    # --------------------------------------------------------------- internal
    def _capture_and_send(self) -> None:
        region = self._strategy.get_region()
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"screenshot_{ts}.jpg"

        try:
            shot = pyautogui.screenshot(region=region)
            if shot.mode in ("RGBA", "P"):
                shot = shot.convert("RGB")
            shot.save(filename, "JPEG", quality=85)
        except Exception as exc:
            logging.error("Capture failed: %s", exc)
            return

        url = self._uploader.upload(filename)
        if url:
            self._publisher.publish_screenshot(
                url=url,
                timestamp=ts,
                window_title=self._strategy.label,
                mode=type(self._strategy).__name__,
            )

        if os.path.exists(filename):
            os.remove(filename)


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    strategy = CaptureModeSelector().choose()

    uploader = R2Uploader(
        account_id=config.R2_ACCOUNT_ID,
        access_key_id=config.R2_ACCESS_KEY_ID,
        secret_access_key=config.R2_SECRET_ACCESS_KEY,
        bucket_name=config.R2_BUCKET_NAME,
    )

    publisher = ScreenshotPublisher(
        app_id=config.PUSHER_APP_ID,
        key=config.PUSHER_KEY,
        secret=config.PUSHER_SECRET,
        cluster=config.PUSHER_CLUSTER,
    )

    ScreenshotCapturePipeline(strategy, uploader, publisher).run()


if __name__ == "__main__":
    main()
