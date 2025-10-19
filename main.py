from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import requests, os, uuid, asyncio, base64

app = FastAPI(
    title="BritishMe - AI British Portrait Generator",
    description="Upload a photo and see yourself as a classy British portrait — London vibe guaranteed.",
    version="2.0.0"
)

# ---- CONFIG ----
GOOGLE_IMAGE_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
API_KEY = "AIzaSyBDRaFvTU1PLxIcfvvN8xjT7NjDvF5sDKo"  # Google AI Studio'dan alınan API key

OUTPUT_DIR = "/tmp/britishme/"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---- TEMP FILE CLEANER ----
async def delete_file_later(path: str, delay: int = 120):
    """Geçici dosyaları belirli süre sonra siler."""
    await asyncio.sleep(delay)
    if os.path.exists(path):
        os.remove(path)


# ---- MAIN ENDPOINT ----
@app.post("/generate")
async def generate_british_style(file: UploadFile, style: str = Form("classic")):
    """
    Kullanıcının yüklediği fotoğrafı Google Gemini 2.5 Flash Image API ile işleyerek
    'British-style portrait' oluşturur. Yüz sabit kalır, kıyafet ve ortam değişir.
    """
    try:
        image_bytes = await file.read()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        headers = {"Content-Type": "application/json"}
        params = {"key": API_KEY}

        # --- Style-specific prompts ---
        prompts = {
            "classic": (
                "Keep the person's face, identity, and expression exactly the same. "
                "Do not alter facial features, proportions, or hair. "
                "Transform only the clothing and background into a stylish British portrait — "
                "a classy outfit, London atmosphere, soft cinematic lighting, realistic color tones."
            ),
            "modern": (
                "Keep the face unchanged. Reimagine the person in a modern British look — "
                "smart-casual outfit, London street background, daylight lighting, "
                "natural and realistic aesthetic."
            ),
            "royal": (
                "Preserve the same face and expression. Transform the clothing and background "
                "into a royal British portrait — luxurious outfit, palace or Victorian-style interior, "
                "warm lighting, elegant and photorealistic result."
            )
        }

        prompt_text = prompts.get(style, prompts["classic"])

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"inline_data": {"mime_type": "image/jpeg", "data": image_base64}},
                        {"text": prompt_text},
                    ],
                }
            ]
        }

        response = requests.post(GOOGLE_IMAGE_API_URL, headers=headers, params=params, json=payload)
        if response.status_code != 200:
            return JSONResponse({"error": "Google API Error", "detail": response.text}, status_code=response.status_code)

        data = response.json()

        # --- Extract image ---
        try:
            image_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            output_bytes = base64.b64decode(image_b64)
        except Exception:
            return JSONResponse({"error": "inline_data", "response_example": data}, status_code=500)

        # --- Save file ---
        file_id = f"{uuid.uuid4()}.jpg"
        output_path = os.path.join(OUTPUT_DIR, file_id)
        with open(output_path, "wb") as f:
            f.write(output_bytes)

        asyncio.create_task(delete_file_later(output_path))

        return JSONResponse(
            {"status": "success", "download_url": f"/download/{file_id}"}, status_code=200
        )

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---- DOWNLOAD ENDPOINT ----
@app.get("/download/{file_id}")
async def download_file(file_id: str):
    """Üretilen resmi indirir. Dosya 2 dakika sonra otomatik silinecektir."""
    path = os.path.join(OUTPUT_DIR, file_id)
    if not os.path.exists(path):
        return JSONResponse({"error": "File expired or not found."}, status_code=404)
    return FileResponse(path, filename="britishme_result.jpg")

from fastapi.staticfiles import StaticFiles

app.mount("/", StaticFiles(directory=".", html=True), name="static")
