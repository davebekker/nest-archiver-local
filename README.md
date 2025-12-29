# Google Nest Camera Local Archiver

## Credits & Attribution
This project is an updated version of the [original Google Nest Archiver](https://github.com/tamirmayer/google-nest-camera-telegram-sync) created by **Tamir Mayer**. The core connection logic and Nest API wrappers remain based on their excellent research into the Google HomeGraph.

---

## 🚀 Key Improvements in this Version
This fork transforms the original script into a resilient, long-term monitoring service:

- **Individual Camera Persistence**: Uses a `state.json` file to track the last sync time for every camera independently.
- **Auto-Recovery**: If the service goes offline, it automatically calculates the gap and "catches up" on all missed events upon restart.
- **Signal Messenger Integration**: Upgraded for `signal-cli-rest-api` v2, sending high-quality video alerts via Base64.
- **Automated Storage Maintenance**: Automatically deletes clips older than 30 days or when the archive exceeds a set size (e.g., 10GB).
- **Notification Filtering**: Silently archives all motion while only sending Signal alerts for specific cameras (e.g., "Nursery" or "Backyard").

## Usage & Configuration

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
```

2. **Get a Google "Master Token"**
You will need a Master Token to authenticate. It is recommended to use a Google One-Time Password for this: 
```bash
docker run --rm -it breph/ha-google-home_get-token
```

3. **Setup Environment (.env)**

Create a .env file in the root directory: 
```dotenv 
GOOGLE_MASTER_TOKEN="aas_..." 
GOOGLE_USERNAME="youremailaddress@gmail.com" 
SIGNAL_NUMBER="+123456789" 
RECIPIENT_NUMBER="+123456789" # Can be a phone number or Signal Group ID 
DOWNLOAD_PATH="./downloads"
```

4. **Initialize State**

The script requires a state.json file. Ensure it contains at least an empty JSON object: ```bash echo "{}" > state.json ```

5. **Run the Service**

```python 
python3 main.py
```