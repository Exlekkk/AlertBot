from fastapi import FastAPI, Request
import os
import requests
from dotenv import load_dotenv

load_dotenv('/opt/smct-alert/config/.env')

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }
    r = requests.post(url, json=payload, timeout=20)
    return r.text


@app.get("/")
def root():
    return {"status": "ok", "message": "SMCT Alert Bot is running"}


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    message = f"📡 收到 TradingView 预警:\n{data}"
    result = send_telegram_message(message)
    return {"ok": True, "telegram_result": result}

