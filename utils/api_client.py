import requests
from config.settings import MONGO_API_BASE

def fetch_summary(clerk_id, project_id, chat_type):
    url = f"{MONGO_API_BASE}/{clerk_id}/{project_id}/{chat_type}"
    try:
        res = requests.get(url)
        if res.status_code == 200:
            return res.json().get("content","")
    except:
        return ""


def save_summary(clerk_id, project_id, chat_type, summary):
    url = f"{MONGO_API_BASE}/save-type-summary/{clerk_id}/{project_id}/{chat_type}"

    try:
        requests.put(url, json={"content":summary})
    except:
        pass    