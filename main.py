import os
import uuid
import base64
import asyncio
import requests
from fastapi import FastAPI, File, UploadFile, Form, Request 
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# SlowAPI için gerekli importlar
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# .env dosyasındaki değişkenleri yükle
load_dotenv()

# IP adresine göre istekleri takip edecek olan Limiter'ı oluştur
limiter = Limiter(key_func=get_remote_address)

# FastAPI uygulamasını başlat
app = FastAPI(
    title="BritishMe - AI British Portrait Generator",
    description="Upload a photo and see yourself as a classy British portrait — London vibe guaranteed.",
    version="2.1.0"
)

# Limiter'ı FastAPI uygulamasına state ve middleware olarak ekle
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS (Cross-Origin Resource Sharing) ayarları
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://cemkarisli.com", "http://127.0.0.1:5500"], # Kendi domainini ve yerel test adresini ekle
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- API ve Dosya Yapılandırması ----
GOOGLE_IMAGE_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    raise RuntimeError("❌ GOOGLE_API_KEY environment variable not set. Please configure it.")

OUTPUT_DIR = "/tmp/britishme/"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---- Geçici Dosya Temizleyici ----
async def delete_file_later(path: str, delay: int = 120):
    """Geçici dosyaları 2 dakika sonra siler."""
    await asyncio.sleep(delay)
    if os.path.exists(path):
        os.remove(path)
        print(f"Deleted temporary file: {path}")


# ---- Ana Üretim Endpoint'i ----
@app.post("/generate")
@limiter.limit("2/day")  # <-- IP başına günde 2 istek limiti burada uygulanıyor
async def generate_british_style(request: Request, file: UploadFile = File(...), style: str = Form("classic")):
    """Fotoğrafı Google Gemini API kullanarak British-style portréye dönüştürür."""
    try:
        image_bytes = await file.read()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        headers = {"Content-Type": "application/json"}
        params = {"key": API_KEY}

        prompts = {
            "classic": (
                "Keep the person's face, identity, and expression exactly the same. "
                "Do not alter facial features or proportions. "
                "Transform only clothing and background into a classy British portrait — "
                "a stylish outfit, London atmosphere, soft cinematic lighting."
            ),
            "modern": (
                "Keep the face unchanged. Reimagine the person in a modern British style — "
                "smart-casual outfit, London street background, daylight lighting."
            ),
            "royal": (
                "Preserve the same face and expression. Transform the clothing and background "
                "into a royal British portrait — luxurious outfit, palace interior, warm lighting."
            )
        }

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"inline_data": {"mime_type": "image/jpeg", "data": image_base64}},
                        {"text": prompts.get(style, prompts["classic"])},
                    ],
                }
            ]
        }

        response = requests.post(GOOGLE_IMAGE_API_URL, headers=headers, params=params, json=payload)
        
        if response.status_code != 200:
            return JSONResponse(
                {"detail": "Google API returned an error. Please try again later."},
                status_code=502,
            )

        data = response.json()
        
        try:
            # Gemini'nin safetyRatings kontrolü
            if data.get("candidates") and data["candidates"][0].get("finishReason") == "SAFETY":
                 return JSONResponse({"detail": "The request was blocked by the AI's safety filter."}, status_code=400)

            image_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            output_bytes = base64.b64decode(image_b64)
        except (KeyError, IndexError):
            return JSONResponse({"detail": "Could not parse the image from the AI response."}, status_code=500)

        file_id = f"{uuid.uuid4()}.jpg"
        output_path = os.path.join(OUTPUT_DIR, file_id)
        
        with open(output_path, "wb") as f:
            f.write(output_bytes)
            
        asyncio.create_task(delete_file_later(output_path))
        
        return {"status": "success", "download_url": f"/download/{file_id}"}

    except RateLimitExceeded:
        # Bu bloğa normalde girmez, middleware halleder ama güvenlik için eklenebilir.
        return JSONResponse({"detail": "Rate limit exceeded. Please try again later."}, status_code=429)
    except Exception as e:
        return JSONResponse({"detail": f"An unexpected error occurred: {str(e)}"}, status_code=500)


# ---- Dosya İndirme Endpoint'i ----
@app.get("/download/{file_id}")
async def download_file(file_id: str):
    """Oluşturulan dosyayı sunar."""
    path = os.path.join(OUTPUT_DIR, file_id)
    if not os.path.exists(path):
        return JSONResponse({"error": "File expired or not found."}, status_code=404)
    return FileResponse(path, filename="britishme_result.jpg")
