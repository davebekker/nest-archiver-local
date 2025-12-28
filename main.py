import os
import datetime
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

# Project imports
from tools import logger
from google_auth_wrapper import GoogleConnection
# logger.setLevel("DEBUG")
load_dotenv()

GOOGLE_MASTER_TOKEN = os.getenv("GOOGLE_MASTER_TOKEN")
GOOGLE_USERNAME = os.getenv("GOOGLE_USERNAME")
SIGNAL_NUMBER = os.getenv("SIGNAL_NUMBER")
RECIPIENT_NUMBER = os.getenv("RECIPIENT_NUMBER")
DOWNLOAD_PATH = "./downloads"
REFRESH_EVERY_X_MINUTES = 30

if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

import datetime
import time
import httpx
import base64

class LocalEventsSync:
    def __init__(self, nest_camera_devices):
        self.nest_camera_devices = nest_camera_devices
        self.signal_url = "http://localhost:8080/v2/send"
        self.signal_number = SIGNAL_NUMBER  # YOUR registered Signal number
        self.recipient_number = RECIPIENT_NUMBER # WHO you want to send it to


    async def send_to_signal(self, filepath=None, message=""):
        """Unified sender using Base64 for the v2 JSON API"""
        try:
            async with httpx.AsyncClient() as client:
                # Base payload structure as defined in your API spec
                payload = {
                    "message": message,
                    "number": self.signal_number,
                    "recipients": [self.recipient_number],
                    "base64_attachments": []
                }
                
                if filepath and os.path.exists(filepath):
                    # Read file and encode to Base64
                    with open(filepath, "rb") as f:
                        file_data = f.read()
                        base64_data = base64.b64encode(file_data).decode('utf-8')
                        filename = os.path.basename(filepath)
                        
                        # Format string: data:<MIME-TYPE>;filename=<FILENAME>;base64,<DATA>
                        attachment_string = f"data:video/mp4;filename={filename};base64,{base64_data}"
                        payload["base64_attachments"].append(attachment_string)

                # Send as pure JSON
                response = await client.post(
                    self.signal_url, 
                    json=payload, 
                    timeout=120.0 # Increased timeout for large video uploads
                )

                if response.status_code in [200, 201]:
                    logger.info(f"Signal notification sent successfully.")
                else:
                    logger.error(f"Signal failed ({response.status_code}): {response.text}")
                    
        except Exception as e:
            logger.error(f"Signal helper error: {e}")

    async def sync(self):
        logger.info("Checking for new camera events...")
        now = datetime.datetime.now()
        # Look back for the full duration of our sleep plus 5 minutes buffer
        lookback = REFRESH_EVERY_X_MINUTES + 5
        for device in self.nest_camera_devices:
            try:
                d_name = device.device_name.replace(' ', '_')
                events = device.get_events(end_time=now, duration_minutes=lookback)
                
                for event in events:
                    start_time = event.start_time.strftime("%Y%m%d_%H%M%S")
                    filename = f"{d_name}_{start_time}.mp4"
                    filepath = os.path.join(DOWNLOAD_PATH, filename)

                    if not os.path.exists(filepath):
                        logger.info(f"Downloading new event for {d_name}...")
                        video_bytes = device.download_camera_event(event)
                        
                        if video_bytes:
                            with open(filepath, "wb") as f:
                                f.write(video_bytes)
                            
                            # NEW: Send to Signal after saving
                            await self.send_to_signal(filepath, f"Nest Alert: {d_name} detected motion at {start_time}")
                                
            except Exception as e:
                logger.error(f"Error syncing {getattr(device, 'device_name', 'Unknown')}: {e}")

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
    # Build a status report for the startup message
    status_report = f"🚀 Nest Archiver Started\nInterval: {REFRESH_EVERY_X_MINUTES}m\n\nCamera Status:"
    
    await local_sync.send_to_signal(message=status_report)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        local_sync.sync, 
        'interval', 
        minutes=REFRESH_EVERY_X_MINUTES, 
        next_run_time=datetime.datetime.now()
    )
    
    scheduler.start()
    while True:
        await asyncio.sleep(1000)

if __name__ == "__main__":
    try:
        asyncio.run(run_scheduler())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
