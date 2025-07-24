import os
from dotenv import load_dotenv

load_dotenv()

Backend_URL = os.getenv("Backend_URL")
print("Backend URL:", Backend_URL)