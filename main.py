import os
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from database import get_connection
from auth import hash_password, verify_password, create_token, decode_token, generate_verify_code
from email_service import send_verify_email
import telegram_relay

app = FastAPI(title="Remote Control API")


@app.on_event("startup")
def _start_telegram_relay():
    telegram_relay.start_polling()


@app.get("/telegram/poll")
def telegram_poll(password: str):
    """Qurilma o'z paroli bilan shu yerga murojaat qilib, faqat o'ziga tegishli yangi xabarlarni oladi."""
    return {"messages": telegram_relay.pop_messages(password)}


class TelegramSendRequest(BaseModel):
    chat_id: str
    type: str = "text"  # "text" | "location"
    text: str = ""
    lat: float = 0.0
    lng: float = 0.0


@app.post("/telegram/send")
def telegram_send(req: TelegramSendRequest):
    """Qurilma javobni shu orqali yuboradi — bot token qurilmada saqlanmaydi, faqat serverda."""
    try:
        if req.type == "location":
            telegram_relay.send_location(req.chat_id, req.lat, req.lng)
        else:
            telegram_relay.send_message(req.chat_id, req.text)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email_or_username: str
    password: str

class VerifyRequest(BaseModel):
    email: str
    code: str

@app.get("/")
def root():
    return {"status": "Remote Control API ishlayapti!"}

@app.post("/auth/register")
def register(data: RegisterRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Username yoki email mavjudmi?
        cur.execute("SELECT id FROM users WHERE email=%s OR username=%s", (data.email, data.username))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Email yoki username allaqachon mavjud")

        # Verify code
        code = generate_verify_code()
        expires = datetime.utcnow() + timedelta(minutes=10)

        # Userni saqlash
        password_hash = hash_password(data.password)
        cur.execute(
            "INSERT INTO users (username, email, password_hash, verify_code, verify_code_expires) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (data.username, data.email, password_hash, code, expires)
        )
        user_id = cur.fetchone()["id"]

        # Profile yaratish
        cur.execute("INSERT INTO user_profiles (user_id) VALUES (%s)", (user_id,))
        conn.commit()

        # Email yuborish
        send_verify_email(data.email, code)

        return {"message": "Ro'yxatdan o'tish muvaffaqiyatli! Emailni tasdiqlang.", "user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@app.post("/auth/verify")
def verify_email(data: VerifyRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, verify_code, verify_code_expires FROM users WHERE email=%s", (data.email,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User topilmadi")
        if user["verify_code"] != data.code:
            raise HTTPException(status_code=400, detail="Noto'g'ri kod")
        if datetime.utcnow().replace(tzinfo=None) > user["verify_code_expires"].replace(tzinfo=None):
            raise HTTPException(status_code=400, detail="Kod muddati tugagan")

        cur.execute("UPDATE users SET is_verified=TRUE, verify_code=NULL WHERE id=%s", (user["id"],))
        conn.commit()

        token = create_token(user["id"])
        return {"message": "Email tasdiqlandi!", "token": token}
    finally:
        cur.close()
        conn.close()

@app.post("/auth/login")
def login(data: LoginRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, password_hash, is_verified FROM users WHERE email=%s OR username=%s",
            (data.email_or_username, data.email_or_username)
        )
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User topilmadi")
        if not verify_password(data.password, user["password_hash"]):
            raise HTTPException(status_code=400, detail="Noto'g'ri parol")
        if not user["is_verified"]:
            raise HTTPException(status_code=400, detail="Email tasdiqlanmagan")

        token = create_token(user["id"])
        return {"message": "Kirish muvaffaqiyatli!", "token": token}
    finally:
        cur.close()
        conn.close()

@app.post("/auth/forgot-password")
def forgot_password(data: dict):
    email = data.get("email", "")
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Bu email topilmadi")
        
        code = generate_verify_code()
        expires = datetime.utcnow() + timedelta(minutes=10)
        cur.execute("UPDATE users SET verify_code=%s, verify_code_expires=%s WHERE email=%s",
                   (code, expires, email))
        conn.commit()
        send_verify_email(email, code)
        return {"message": "Kod emailga yuborildi"}
    finally:
        cur.close()
        conn.close()

@app.post("/auth/reset-password")
def reset_password(data: dict):
    email = data.get("email", "")
    code = data.get("code", "")
    new_password = data.get("new_password", "")
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, verify_code, verify_code_expires FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User topilmadi")
        if user["verify_code"] != code:
            raise HTTPException(status_code=400, detail="Noto'g'ri kod")
        if datetime.utcnow().replace(tzinfo=None) > user["verify_code_expires"].replace(tzinfo=None):
            raise HTTPException(status_code=400, detail="Kod muddati tugagan")
        
        from auth import hash_password
        new_hash = hash_password(new_password)
        cur.execute("UPDATE users SET password_hash=%s, verify_code=NULL WHERE id=%s",
                   (new_hash, user["id"]))
        conn.commit()
        return {"message": "Parol muvaffaqiyatli o'zgartirildi"}
    finally:
        cur.close()
        conn.close()

@app.get("/auth/me")
def get_me(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    try:
        user_id = decode_token(token)
    except:
        raise HTTPException(status_code=401, detail="Token noto'g'ri")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT u.id, u.username, u.email, u.created_at, p.full_name, p.profile_picture, p.age, p.phone FROM users u LEFT JOIN user_profiles p ON u.id=p.user_id WHERE u.id=%s",
            (user_id,)
        )
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User topilmadi")
        return dict(user)
    finally:
        cur.close()
        conn.close()


# Cache
audio_cache = {}

@app.get("/audio/stream")
async def get_audio_url(query: str):
    """YouTube dan audio URL olish"""
    import subprocess
    import json
    import time
    
    # Cache tekshirish
    cache_key = query.lower().strip()
    if cache_key in audio_cache:
        cached = audio_cache[cache_key]
        if time.time() - cached["time"] < 3600:  # 1 soat
            return cached["data"]
    
    # Agar cookies.txt mavjud bo'lsa, yt-dlp chaqiruviga qo'shamiz —
    # bu YouTube'ning server (datacenter) IP'larini "bot" deb bloklashining oldini oladi.
    cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
    cookies_args = ["--cookies", cookies_path] if os.path.exists(cookies_path) else []

    youtube_api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not youtube_api_key:
        raise HTTPException(status_code=500, detail="YOUTUBE_API_KEY sozlanmagan")

    # venv ichidagi yt-dlp'ni aniq ko'rsatamiz — unda bgutil-ytdlp-pot-provider plagini bor.
    # systemd xizmati ichida oddiy "yt-dlp" buyrug'i PATH orqali plaginsiz global
    # nusxani topib qolishi mumkin, shuning uchun to'liq yo'lni ishlatamiz.
    yt_dlp_bin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "bin", "yt-dlp")
    if not os.path.exists(yt_dlp_bin):
        yt_dlp_bin = "yt-dlp"

    try:
        # Qidiruvni yt-dlp o'rniga rasmiy YouTube Data API orqali qilamiz — bu
        # yt-dlp'ning o'z qidiruvi (ytsearch) ko'pincha YouTube'ning bot-aniqlash
        # tizimiga tushib qolgani uchun, brauzerdagi kabi ishonchli natija beradi.
        import urllib.request
        import urllib.parse

        search_params = urllib.parse.urlencode({
            "part": "snippet",
            "q": query,
            "type": "video",
            "videoCategoryId": "10",  # Music
            "maxResults": 1,
            "key": youtube_api_key
        })
        search_url = f"https://www.googleapis.com/youtube/v3/search?{search_params}"
        with urllib.request.urlopen(search_url, timeout=10) as resp:
            search_data = json.loads(resp.read().decode())

        items = search_data.get("items", [])
        if not items:
            raise HTTPException(status_code=404, detail="Video topilmadi")

        video_id = items[0]["id"]["videoId"]
        title = items[0]["snippet"]["title"]

        # Faqat audio URL uchun yt-dlp'ni ishlatamiz (videoId allaqachon ma'lum,
        # qidiruv qilinmaydi — shuning uchun bot-aniqlashga tushish ehtimoli kamroq).
        # Ba'zi videolar ma'lum klient kombinatsiyasida bot-tekshiruviga tushib qolishi
        # mumkin — shuning uchun bir nechta kombinatsiyani ketma-ket sinaymiz.
        client_combos = [
            "android_vr,mweb",
            "tv,web_safari",
            "mweb",
            "default",
        ]
        audio_url = ""
        last_stderr = ""
        for combo in client_combos:
            url_result = subprocess.run([
                yt_dlp_bin,
                f"https://www.youtube.com/watch?v={video_id}",
                "-f", "bestaudio[ext=m4a]/bestaudio/best",
                "--get-url",
                "--no-playlist",
                "--quiet",
                "--extractor-args", f"youtube:player_client={combo}",
                *cookies_args
            ], capture_output=True, text=True, timeout=20)
            audio_url = url_result.stdout.strip()
            last_stderr = url_result.stderr.strip()
            if audio_url:
                break

        if not audio_url:
            # yt-dlp'ning xato matnini ham qo'shamiz — shunda sabab darhol ko'rinadi
            raise HTTPException(
                status_code=404,
                detail=f"Audio URL topilmadi: {last_stderr[-500:]}"
            )

        result = {
            "video_id": video_id,
            "title": title,
            "audio_url": audio_url
        }
        # Cache ga saqlaymiz
        audio_cache[cache_key] = {"data": result, "time": time.time()}
        return result
    except HTTPException:
        raise  # ataylab chiqargan xatoliklarni (404 va h.k.) o'zgartirmasdan uzatamiz
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
