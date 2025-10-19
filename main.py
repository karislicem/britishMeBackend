import os
import uuid
import base64
import asyncio
import requests
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Load environment variables (for local dev)
load_dotenv()

app = FastAPI(
    title="BritishMe - AI British Portrait Generator",
    description="Upload a photo and see yourself as a classy British portrait — London vibe guaranteed.",
    version="2.1.0"
)

# ---- CONFIG ----
GOOGLE_IMAGE_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    raise RuntimeError("❌ GOOGLE_API_KEY environment variable not set. Please configure it.")

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
                {"error": "Google API Error", "detail": response.text},
                status_code=response.status_code,
            )

        data = response.json()

        try:
            image_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            output_bytes = base64.b64decode(image_b64)
        except Exception:
            return JSONResponse({"error": "inline_data", "response_example": data}, status_code=500)

        file_id = f"{uuid.uuid4()}.jpg"
        output_path = os.path.join(OUTPUT_DIR, file_id)
        with open(output_path, "wb") as f:
            f.write(output_bytes)

        asyncio.create_task(delete_file_later(output_path))

        return {"status": "success", "download_url": f"/download/{file_id}"}

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---- DOWNLOAD ENDPOINT ----
@app.get("/download/{file_id}")
async def download_file(file_id: str):
    path = os.path.join(OUTPUT_DIR, file_id)
    if not os.path.exists(path):
        return JSONResponse({"error": "File expired or not found."}, status_code=404)
    return FileResponse(path, filename="britishme_result.jpg")


# ---- SERVE STATIC (optional) ----
app.mount("/", StaticFiles(directory=".", html=True), name="static")
