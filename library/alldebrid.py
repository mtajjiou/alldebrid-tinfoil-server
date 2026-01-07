import os
from dotenv import load_dotenv

load_dotenv()

ALLDEBRID_API_KEY = os.getenv("ALLDEBRID_API_KEY")
ALLDEBRID_API_URL = "https://api.alldebrid.com/v4"
