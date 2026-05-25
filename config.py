from dotenv import load_dotenv
import os

load_dotenv()

CLIENT_ID = os.getenv("SUPERPDP_CLIENT_ID")
CLIENT_SECRET = os.getenv("SUPERPDP_CLIENT_SECRET")
BASE_URL = os.getenv("SUPERPDP_BASE_URL")
AUTH_URL = os.getenv("SUPERPDP_AUTH_URL")