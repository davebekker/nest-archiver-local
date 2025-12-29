import os
import datetime as dt 
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
import time
import httpx
import base64
import json

# Project imports
from tools import logger
from google_auth_wrapper import GoogleConnection
# logger.setLevel("DEBUG")
load_dotenv()

GOOGLE_MASTER_TOKEN = os.getenv("GOOGLE_MASTER_TOKEN")
GOOGLE_USERNAME = os.getenv("GOOGLE_USERNAME")
REFRESH_EVERY_X_MINUTES = 30

# --- CONFIGURATION ---
STATE_FILE = "state.json"
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", "./downloads")
MAX_FOLDER_GB = 10  # Max storage limit
MAX_AGE_DAYS = 30   # Delete older than a month
MONITORED_CAMERAS = ["Backyard", "Nest Doorbell (battery)"] # Only alert for these

if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

# Signal Config
SIGNAL_URL = "http://localhost:8080/v2/send"
SIGNAL_NUMBER = os.getenv("SIGNAL_NUMBER")
RECIPIENT_NUMBER = os.getenv("RECIPIENT_NUMBER") # Group ID or Phone Number

class LocalEventsSync:
    def __init__(self, nest_devices):
        self.devices = nest_devices
        self.state = self.load_state()

    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    content = f.read().strip()
                    if not content:  # Handle empty file
                        return {}
                    return json.loads(content)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading state file: {e}. Resetting state.")
                return {}
        return {}

    def save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f)

    async def send_to_signal(self, filepath=None, message=""):
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "message": message,
                    "number": SIGNAL_NUMBER,
                    "recipients": [RECIPIENT_NUMBER],
                    "base64_attachments": []
                }
                if filepath:
                    with open(filepath, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode('utf-8')
                        payload["base64_attachments"].append(
                            f"data:video/mp4;filename={os.path.basename(filepath)};base64,{b64}"
                        )
                await client.post(SIGNAL_URL, json=payload, timeout=120.0)
        except Exception as e:
            logger.error(f"Signal error: {e}")

    async def sync(self):
        # now = dt.datetime.now()
        now = dt.datetime.now(dt.timezone.utc)
        for device in self.devices:
            d_id = getattr(device, 'device_id', device.device_name)
            
            # 1. Determine Lookback (Persistence)
            last_ts_str = self.state.get(d_id)
            if last_ts_str:
                last_ts = dt.datetime.fromisoformat(last_ts_str)
                # Calculate minutes since last successful sync
                delta = int((now - last_ts).total_seconds() / 60) + 2 
            else:
                delta = 180 # Default fallback

            logger.info(f"Syncing {device.device_name} (Lookback: {delta}m)")
            events = device.get_events(end_time=now, duration_minutes=delta)
            
            latest_event_time = last_ts if last_ts_str else None

            for event in (events or []):
                # Avoid duplicates
                if latest_event_time and event.start_time <= latest_event_time:
                    continue

                filename = f"{device.device_name}_{event.start_time.strftime('%Y%m%d_%H%M%S')}.mp4"
                filepath = os.path.join(DOWNLOAD_PATH, filename)

                if not os.path.exists(filepath):
                    video_bytes = device.download_camera_event(event)
                    if video_bytes:
                        with open(filepath, "wb") as f:
                            f.write(video_bytes)
                        
                        # 2. Filter Alerts by Camera Name
                        if device.device_name in MONITORED_CAMERAS:
                            await self.send_to_signal(filepath, f"Alert: {device.device_name}")

                if not latest_event_time or event.start_time > latest_event_time:
                    latest_event_time = event.start_time

            # 3. Update State
            if latest_event_time:
                self.state[d_id] = latest_event_time.isoformat()
                self.save_state()

    def cleanup_storage(self):
        """Deletes files older than N days or if folder exceeds GB limit"""
        files = [os.path.join(DOWNLOAD_PATH, f) for f in os.listdir(DOWNLOAD_PATH)]
        files.sort(key=os.path.getmtime) # Oldest first

        # Delete by age
        now = time.time()
        for f in files[:]:
            if os.path.getmtime(f) < now - (MAX_AGE_DAYS * 86400):
                os.remove(f)
                files.remove(f)

        # Delete by size
        total_size = sum(os.path.getsize(f) for f in files)
        while total_size > (MAX_FOLDER_GB * 1024**3) and files:
            oldest = files.pop(0)
            total_size -= os.path.getsize(oldest)
            os.remove(oldest)

async def run_scheduler():
    logger.info("Welcome to the Google Nest Local Archiver")

    if not GOOGLE_MASTER_TOKEN or not GOOGLE_USERNAME:
        logger.error("Missing credentials in .env")
        return

    google_connection = GoogleConnection(GOOGLE_MASTER_TOKEN, GOOGLE_USERNAME)
    nest_camera_devices = google_connection.get_nest_camera_devices()
    for idx, device in enumerate(nest_camera_devices):
        print(f"{idx} - Camera {device.device_name} found")
    logger.info(f"Found {len(nest_camera_devices)} cameras.")

    local_sync = LocalEventsSync(nest_camera_devices)
    # await local_sync.send_to_signal(message="🚀 Nest Archiver has started. Monitoring every 30 minutes.")
    # Build a status report for the startup message
    status_report = f"🚀 Nest Archiver Started\nInterval: {REFRESH_EVERY_X_MINUTES}m\n\nCamera Status:"
    
    await local_sync.send_to_signal(message=status_report)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        local_sync.sync, 
        'interval', 
        minutes=REFRESH_EVERY_X_MINUTES, 
        next_run_time=dt.datetime.now()
    )
    scheduler.add_job(local_sync.cleanup_storage, 'interval', hours=24)
    scheduler.start()
    while True:
        await asyncio.sleep(1000)

if __name__ == "__main__":
    try:
        asyncio.run(run_scheduler())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
