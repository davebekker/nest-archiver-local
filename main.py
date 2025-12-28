import os
import datetime
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

# Project imports
from tools import logger
from google_auth_wrapper import GoogleConnection

load_dotenv()

GOOGLE_MASTER_TOKEN = os.getenv("GOOGLE_MASTER_TOKEN")
GOOGLE_USERNAME = os.getenv("GOOGLE_USERNAME")
DOWNLOAD_PATH = "./downloads"
REFRESH_EVERY_X_MINUTES = 30

if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

import datetime
import time

class LocalEventsSync:
    def __init__(self, nest_camera_devices):
        self.nest_camera_devices = nest_camera_devices

    async def sync(self):
        logger.info("Checking for new camera events...")
        now = datetime.datetime.now()
        lookback_duration = 15 # Catching those backyard events

        for device in self.nest_camera_devices:
            try:
                d_name = device.device_name.replace(' ', '_')
                events = device.get_events(end_time=now, duration_minutes=lookback_duration)
                
                if not events:
                    continue

                for event in events:
                    # Create a simple unique filename based on the start time of the event
                    # This avoids the messy pipe symbols in the ID
                    start_time = event.start_time.strftime("%Y%m%d_%H%M%S")
                    filename = f"{d_name}_{start_time}.mp4"
                    filepath = os.path.join(DOWNLOAD_PATH, filename)

                    if not os.path.exists(filepath):
                        logger.info(f"Downloading new event for {d_name}...")
                        
                        # CATCH THE BYTES: The function returns the video data
                        video_bytes = device.download_camera_event(event)
                        
                        if video_bytes and len(video_bytes) > 0:
                            with open(filepath, "wb") as f:
                                f.write(video_bytes)
                            logger.info(f"Successfully saved to: {filepath}")
                        else:
                            logger.warning(f"Download triggered but no data returned for {filename}")
                                
            except Exception as e:
                logger.error(f"Error syncing {getattr(device, 'device_name', 'Unknown')}: {e}")

async def run_scheduler():
    logger.info("Welcome to the Google Nest Local Archiver")

    if not GOOGLE_MASTER_TOKEN or not GOOGLE_USERNAME:
        logger.error("Missing credentials in .env")
        return

    google_connection = GoogleConnection(GOOGLE_MASTER_TOKEN, GOOGLE_USERNAME)
    nest_camera_devices = google_connection.get_nest_camera_devices()
    logger.info(f"Found {len(nest_camera_devices)} cameras.")

    local_sync = LocalEventsSync(nest_camera_devices)

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
