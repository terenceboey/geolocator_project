# Image Geolocation Globe

Browser prototype for uploading an image file or image URL, sending it to a geolocation API, and pinning the returned coordinates on a Mapbox GL JS globe.

## What Mapbox Does

Mapbox renders the globe, camera movement, marker, popup, and map style. It does not infer a photo location from pixels.

Your backend must return coordinates, for example:

```json
{
  "location": {
    "latitude": 25.7617,
    "longitude": -80.1918,
    "city": "Miami",
    "country": "United States"
  },
  "confidence": 0.78,
  "reasoning": "Visual clues matched downtown Miami."
}
```

## Run

Open `index.html` directly in a browser, or serve this folder:

```powershell
python -m http.server 8080
```

Then open `http://localhost:8080`.

## Backend Clue Extraction

The first backend stage is implemented in `backend/`. It validates the image, preserves the original pixels for OCR/vision accuracy, runs an OCR provider hook, runs OpenRouter vision clue extraction when `OPENROUTER_API_KEY` is set, and returns structured clues. It does not use EXIF/GPS metadata.

Install and run:

```powershell
cd C:\Users\Terence\Desktop\geolocator_project\backend
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --port 8000
```

Set your OpenRouter key in `backend/.env`:

```env
VISION_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here
OPENROUTER_VISION_MODEL=google/gemini-2.5-pro
OCR_PROVIDER=google
GOOGLE_VISION_FEATURES=text,landmark,logo,web
GOOGLE_APPLICATION_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"...","token_uri":"https://oauth2.googleapis.com/token"}
```

Then open:

```text
http://localhost:8000/docs
```

Implemented endpoints:

```text
GET  /health
POST /extract-clues
POST /geolocate
```

For this stage, use `/extract-clues` to inspect visual/OCR clues. `/geolocate` currently returns the clue extraction result as debug output; coordinate ranking comes in the next implementation stage.

Google Cloud Vision is the primary OCR provider. Set `OCR_PROVIDER=google` in `backend/.env`, enable the Cloud Vision API in your Google Cloud project, and paste the service-account JSON as a single-line `GOOGLE_APPLICATION_CREDENTIALS_JSON` value. A file path in `GOOGLE_APPLICATION_CREDENTIALS` is also supported. `GOOGLE_VISION_FEATURES` controls the Google features requested; the current live setting is `text,landmark,logo,web`, which returns OCR structure plus landmark, logo, and web-detection clues. Leave `OCR_PROVIDER=none` only when you want OpenRouter-only clue extraction without OCR.

The `/extract-clues` response includes:

```text
agent_result_run_id   unique id for this Analyze run
agent_result_dir      folder containing per-agent JSON outputs
ocr_items            word-level OCR with bounding boxes
ocr_full_text        Google full text string
ocr_lines            grouped OCR lines
ocr_blocks           grouped OCR blocks
google_landmarks     detected landmark names, boxes, and coordinates when available
google_logos         detected brand/logo names
google_web_entities  web-detection entities
google_web_pages     matching web pages from web detection
```

Each Analyze request writes per-agent result files to:

```text
agent_result/<agent_result_run_id>/
```

Current files:

```text
google_vision.json       Google Vision OCR/landmark/logo/web response extracted by the backend
vision_clue_model.json   OpenRouter/OpenAI clue-model result or error
final_response.json      final `/extract-clues` API response
```

## Required Setup

1. Create a Mapbox public token from your Mapbox account.
2. Paste it into the app.
3. Add your geolocation API endpoint.
4. Upload an image or enter an image URL.
5. Click `Analyze`.

The `Demo Pin` button verifies the Mapbox globe and marker without needing a backend.

## UI Surfaces

The side panel remains the full control and debugging surface. A floating dark translucent quick-action panel sits over the globe and uses the same shared state and functions, so File/URL selection, previews, Analyze, Demo Pin, and Clear Pin stay synchronized.

## Image Inputs

Files must be PNG, JPG, JPEG, or WebP and 10 MB or smaller.

Image URLs must start with `http://` or `https://` and the URL path must end in `.png`, `.jpg`, `.jpeg`, or `.webp`.

## Map Style

The app uses Mapbox Streets with globe projection:

```js
style: "mapbox://styles/mapbox/streets-v12",
projection: "globe"
```
