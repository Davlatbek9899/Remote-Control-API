import os
import json
import threading
import time
import urllib.request
import urllib.parse

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# parol -> [{"text":..., "chat_id":...}, ...] — har bir qurilma shu yerdan o'ziga tegishlisini oladi
_queues = {}
_lock = threading.Lock()
# chat_id -> parol — shu chat hozir qaysi parolning AI (Jarvis) sessiyasiga tegishli ekanini bilish uchun
# (parolsiz kelgan davomiy xabarlarni to'g'ri qurilmaga yo'naltirish uchun kerak)
_active_password_by_chat = {}

_offset = 0


def _parse_password(text: str):
    """"#ping_1234" -> ("#ping", "1234"). Parol topilmasa (text, None) qaytaradi."""
    text = text.strip()
    idx = text.rfind("_")
    if idx == -1:
        return text, None
    candidate = text[idx + 1:]
    if len(candidate) == 4 and candidate.isdigit():
        return text[:idx], candidate
    return text, None


def _enqueue(password: str, chat_id: str, text: str):
    with _lock:
        _queues.setdefault(password, []).append({"text": text, "chat_id": chat_id})


def _route_update(update: dict):
    message = update.get("message")
    if not message:
        return
    chat_id = str(message.get("chat", {}).get("id"))
    text = message.get("text", "")
    if not text:
        return

    command, password = _parse_password(text)

    if password:
        _enqueue(password, chat_id, text)
        if command.lower().startswith("#ai"):
            with _lock:
                _active_password_by_chat[chat_id] = password
        return

    # Parolsiz xabar — faqat shu chat uchun faol (AI rejimidagi) parol bo'lsa, o'shanga yo'naltiramiz
    with _lock:
        active_password = _active_password_by_chat.get(chat_id)
    if active_password:
        _enqueue(active_password, chat_id, text)
        if text.strip().lower() == "#stop_ai":
            with _lock:
                _active_password_by_chat.pop(chat_id, None)


def _poll_loop():
    global _offset
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN sozlanmagan — Telegram relay ishga tushmadi")
        return
    while True:
        try:
            params = urllib.parse.urlencode({"timeout": 25, "offset": _offset})
            url = f"{API_BASE}/getUpdates?{params}"
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            for update in data.get("result", []):
                _offset = update["update_id"] + 1
                _route_update(update)
        except Exception as e:
            print(f"Telegram poll xato: {e}")
            time.sleep(3)


def start_polling():
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN sozlanmagan — Telegram relay ishga tushmadi")
        return
    thread = threading.Thread(target=_poll_loop, daemon=True)
    thread.start()


def pop_messages(password: str):
    with _lock:
        msgs = _queues.get(password, [])
        _queues[password] = []
    return msgs


def send_message(chat_id: str, text: str):
    params = urllib.parse.urlencode({"chat_id": chat_id, "text": text})
    url = f"{API_BASE}/sendMessage?{params}"
    urllib.request.urlopen(url, timeout=10).read()


def send_location(chat_id: str, lat: float, lng: float):
    params = urllib.parse.urlencode({"chat_id": chat_id, "latitude": lat, "longitude": lng})
    url = f"{API_BASE}/sendLocation?{params}"
    urllib.request.urlopen(url, timeout=10).read()
