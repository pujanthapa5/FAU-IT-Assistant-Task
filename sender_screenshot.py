import time
import json
import logging
import boto3
from botocore.exceptions import NoCredentialsError
import pyautogui
import pygetwindow as gw
import os
import sys
import tkinter as tk
from datetime import datetime
import pusher
import config
import atexit

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def capture_screenshot(filename, region=None):
    """Captures the screen or a specific region and saves it to a file."""
    try:
        logging.info("Capturing screenshot...")
        # region parameter is (left, top, width, height)
        screenshot = pyautogui.screenshot(region=region)
        
        # JPEG doesn't support alpha channel, must convert RGBA/P to RGB
        if screenshot.mode in ("RGBA", "P"):
            screenshot = screenshot.convert("RGB")
            
        screenshot.save(filename, "JPEG", quality=85)
        return True
    except Exception as e:
        logging.error(f"Failed to capture screenshot: {e}")
        return False

def upload_to_r2(file_name, bucket, object_name=None):
    """Upload a file to R2 and return a presigned URL."""
    
    if object_name is None:
        object_name = os.path.basename(file_name)

    # R2 client setup
    s3_client = boto3.client('s3',
        endpoint_url=f'https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
        region_name='auto'
    )

    try:
        logging.info(f"Uploading {file_name} to R2 bucket '{bucket}'...")
        s3_client.upload_file(file_name, bucket, object_name)
        logging.info("Upload successful.")
        
        # Generate Presigned URL (valid for 1 hour)
        url = s3_client.generate_presigned_url('get_object',
                                               Params={'Bucket': bucket,
                                                       'Key': object_name},
                                               ExpiresIn=3600)
        return url
    except Exception as e:
        logging.error(f"Failed to upload or generate URL: {e}")
        return None

class WindowSelector:
    """A dialog box for selecting an open window."""
    def __init__(self, parent):
        self.top = tk.Toplevel(parent)
        self.top.title("Select a Window")
        self.top.geometry("600x600")
        self.top.attributes("-topmost", True)
        self.top.lift()
        
        self.selected_window = None
        
        tk.Label(self.top, text="Select a window from the list and click Select (or double-click it):", pady=10, font=("Arial", 10, "bold")).pack()
        
        # Frame for listbox and scrollbar
        list_frame = tk.Frame(self.top)
        list_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.listbox = tk.Listbox(list_frame, width=70, height=25, yscrollcommand=scrollbar.set, font=("Consolas", 9))
        self.listbox.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        
        # Get and filter windows
        windows = gw.getAllWindows()
        # Only include windows with titles and that are likely visible
        self.valid_windows = sorted([w for w in windows if w.title.strip()], key=lambda w: w.title.lower())
        
        for w in self.valid_windows:
            self.listbox.insert(tk.END, f" {w.title[:80]}") # Show first 80 chars
            
        self.listbox.bind("<Double-Button-1>", lambda e: self.on_select())
        
        btn_frame = tk.Frame(self.top)
        btn_frame.pack(pady=15)
        
        tk.Button(btn_frame, text="SELECT", command=self.on_select, width=15, bg="#4CAF50", fg="white", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="CANCEL", command=self.top.destroy, width=15, font=("Arial", 9)).pack(side=tk.LEFT, padx=10)
        
        # Focus the listbox
        self.listbox.focus_set()
        if self.valid_windows:
            self.listbox.selection_set(0)
        
    def on_select(self):
        selection = self.listbox.curselection()
        if selection:
            index = selection[0]
            self.selected_window = self.valid_windows[index]
            logging.info(f"User confirmed window selection: {self.selected_window.title}")
            self.top.destroy()
        else:
            logging.warning("Select clicked but no window highlighted.")
            
    def get_selection(self):
        self.top.focus_force()
        self.top.wait_window()
        return self.selected_window

class CaptureSelector:
    """A transparent overlay for selecting a screen region."""
    def __init__(self, parent, bounding_box=None):
        self.top = tk.Toplevel(parent)
        self.top.attributes("-alpha", 0.3)
        self.top.attributes("-fullscreen", True)
        self.top.attributes("-topmost", True)
        self.top.config(cursor="cross")
        self.top.lift()
        
        self.canvas = tk.Canvas(self.top, highlightthickness=0, bg="grey")
        self.canvas.pack(fill="both", expand=True)
        
        if bounding_box:
            l, t, w, h = bounding_box
            self.canvas.create_rectangle(l, t, l+w, t+h, outline="blue", width=2, dash=(4, 4))
            self.canvas.create_text(l + w/2, t - 20, text=f"Target: {h}x{w}", fill="blue", font=("Arial", 12, "bold"))

        self.start_x = None
        self.start_y = None
        self.rect = None
        self.selection = None
        
        self.top.bind("<ButtonPress-1>", self.on_press)
        self.top.bind("<B1-Motion>", self.on_drag)
        self.top.bind("<ButtonRelease-1>", self.on_release)
        self.top.bind("<Escape>", lambda e: self.top.destroy())
        
    def on_press(self, event):
        self.start_x = self.top.winfo_pointerx()
        self.start_y = self.top.winfo_pointery()
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="red", width=2)
        
    def on_drag(self, event):
        curr_x = self.top.winfo_pointerx()
        curr_y = self.top.winfo_pointery()
        self.canvas.coords(self.rect, self.start_x, self.start_y, curr_x, curr_y)
        
    def on_release(self, event):
        end_x = self.top.winfo_pointerx()
        end_y = self.top.winfo_pointery()
        
        left = min(self.start_x, end_x)
        top = min(self.start_y, end_y)
        width = abs(self.start_x - end_x)
        height = abs(self.start_y - end_y)
        
        if width > 5 and height > 5:
            self.selection = (left, top, width, height)
            logging.info(f"Region selected: {self.selection}")
            self.top.destroy()

    def get_selection(self):
        self.top.focus_force()
        self.top.wait_window()
        return self.selection

def get_active_window_region():
    """Returns the region (left, top, width, height) of the active window."""
    try:
        window = gw.getActiveWindow()
        if window:
            return (window.left, window.top, window.width, window.height), window.title
    except Exception as e:
        logging.error(f"Failed to get active window: {e}")
    return None, None

def select_capture_mode():
    """Prompts the user to select what to capture."""
    while True:
        root = tk.Tk()
        root.withdraw()
        
        print("\n--- Screenshot Selection ---")
        print("[1] Full Screen")
        print("[2] Active Window (Dynamic Tracking)")
        print("[3] Select Region (Anywhere)")
        print("[4] Select Window + Region")
        print("[q] Quit")
        
        choice = input("\nChoose an option: ").strip().lower()
        
        if choice == '1':
            root.destroy()
            return "full", None, "Full Screen"
            
        elif choice == '2':
            region, title = get_active_window_region()
            if region:
                root.destroy()
                return "active", region, title
            else:
                print("Could not identify active window. Try again.")
                root.destroy()
                continue
                
        elif choice == '3':
            print("Drag your mouse to select a region. Press Esc to cancel.")
            selector = CaptureSelector(root)
            selection = selector.get_selection()
            root.destroy()
            if selection:
                return "region", selection, "Selected Region"
            else:
                print("No region selected. Returning to menu...")
                continue
                
        elif choice == '4':
            logging.info("Opening window selection dialog...")
            win_selector = WindowSelector(root)
            target_win = win_selector.get_selection()
            
            if target_win:
                try:
                    logging.info(f"Activating window: {target_win.title}")
                    # Try to bring window to front
                    if target_win.isMinimized:
                        target_win.restore()
                    target_win.activate()
                    time.sleep(1.5) # Wait for window to settle/activate
                    
                    # Highlight the window and let user select region
                    win_box = (target_win.left, target_win.top, target_win.width, target_win.height)
                    print(f"\nTargeting: {target_win.title}")
                    print("--> Drag your mouse across the area YOU WANT TO CAPTURE within this window.")
                    
                    cap_selector = CaptureSelector(root, bounding_box=win_box)
                    selection = cap_selector.get_selection()
                    
                    root.destroy()
                    if selection:
                        return "window_region", selection, f"Region of {target_win.title}"
                    else:
                        print("No region selected. Returning to menu...")
                        continue
                except Exception as e:
                    logging.error(f"Error during window selection flow: {e}")
                    print(f"Failed to handle window: {e}")
                    root.destroy()
                    continue
            else:
                logging.info("Window selection cancelled.")
                root.destroy()
                continue
                
        elif choice == 'q':
            root.destroy()
            sys.exit(0)
        else:
            print("Invalid choice. Please enter 1, 2, 3, 4, or q.")
            root.destroy()

def main():
    # Initialize Pusher Client
    pusher_client = pusher.Pusher(
        app_id=config.PUSHER_APP_ID,
        key=config.PUSHER_KEY,
        secret=config.PUSHER_SECRET,
        cluster=config.PUSHER_CLUSTER,
        ssl=True
    )
    
    def send_status(active):
        """Sends a status message to Pusher to indicate if capture is active."""
        status_data = {
            "type": "screenshot_status",
            "active": active,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        try:
            pusher_client.trigger('screenshot-stream', 'new-message', status_data)
            logging.info(f"Sent screenshot status: {'ACTIVE' if active else 'INACTIVE'}")
        except Exception as e:
            logging.error(f"Failed to send status to Pusher: {e}")

    # Register exit handler to send inactive status
    atexit.register(send_status, False)

    print("Welcome to the upgraded Screen Capture tool.")
    mode, region, window_title = select_capture_mode()
    
    # Notify that we are starting
    send_status(True)
    
    logging.info(f"Sender script started. Mode: '{mode}' ({window_title}) Capturing every 2 minutes...")

    while True:
        # If mode is 'active', we need to refresh the region and title
        if mode == "active":
            current_region, current_title = get_active_window_region()
            if current_region:
                region = current_region
                window_title = current_title
                logging.info(f"Targeting active window: '{window_title}' at {region}")

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"screenshot_{timestamp}.jpg"
        
        if capture_screenshot(filename, region=region):
            public_url = upload_to_r2(filename, config.R2_BUCKET_NAME, filename)
            
            if public_url:
                data = {
                    "type": "screenshot",
                    "url": public_url,
                    "timestamp": timestamp,
                    "window_title": window_title,
                    "mode": mode
                }
                
                try:
                    pusher_client.trigger('screenshot-stream', 'new-message', data)
                    logging.info(f"Sent screenshot URL to Pusher for '{window_title}'.")
                except Exception as e:
                    logging.error(f"Failed to trigger Pusher event: {e}")
            
            # Clean up local file
            if os.path.exists(filename):
                os.remove(filename)
        
        logging.info("Sleeping for 2 minutes...")
        time.sleep(120) # Send every 2 minutes

if __name__ == "__main__":
    main()
