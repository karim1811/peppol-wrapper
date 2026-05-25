import os
import httpx
from dotenv import load_dotenv

load_dotenv()

AUTH_URL = os.getenv("SUPERPDP_AUTH_URL")

async def get_token():
    return await get_company_token("seller")

async def get_company_token(role: str):
    if role == "seller":
        client_id = os.getenv("SELLER_CLIENT_ID")
        client_secret = os.getenv("SELLER_CLIENT_SECRET")
    elif role == "buyer":
        client_id = os.getenv("BUYER_CLIENT_ID")
        client_secret = os.getenv("BUYER_CLIENT_SECRET")
    else:
        raise ValueError("role must be 'seller' or 'buyer'")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]