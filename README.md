# StepInsight Interview Challenge

Image geolocation prototype built for the StepInsight interview challenge.

The challenge is to identify where photos were taken and return latitude and longitude as accurately as possible. This project approaches that problem as a visible-evidence geolocation workflow: upload an image file or image URL, extract visual and OCR clues, combine the evidence through a backend agent workflow, and pin the final coordinates on a Mapbox GL JS globe.

## Challenge Results

| Image | Predicted location | Coordinates |
| --- | --- | --- |
| Image 1 | Darrell K Royal-Texas Memorial Stadium, Austin, Texas, United States | `30.279030, -97.732460` |
| Image 2 | Texas African American History Memorial, Austin, Texas, United States | `30.273282, -97.741493` |
| Image 3 | Echo Point Lookout / Three Sisters, Katoomba, New South Wales, Australia | `-33.732740, 150.311935` |

### Image 1 Result

![Image 1 geolocation result](assets/results/image-1-stadium-result.png)

### Image 2 Result

![Image 2 geolocation result](assets/results/image-2-memorial-result.png)

### Image 3 Result

![Image 3 geolocation result](assets/results/image-3-three-sisters-result.png)

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
OPENROUTER_MAX_TOKENS=3000
OCR_PROVIDER=google
GOOGLE_VISION_FEATURES=text,landmark,logo,label,web
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
GET  /agent-results
GET  /agent-results/{run_id}
```

Use `/extract-clues` to inspect the visual/OCR clue extraction stage only. Use `/geolocate` for the full LangGraph workflow that runs Google Vision and Gemini clue extraction in parallel, then sends both evidence sets into the final geolocation agent.

Google Cloud Vision is the primary OCR provider. Set `OCR_PROVIDER=google` in `backend/.env`, enable the Cloud Vision API in your Google Cloud project, and paste the service-account JSON as a single-line `GOOGLE_APPLICATION_CREDENTIALS_JSON` value. A file path in `GOOGLE_APPLICATION_CREDENTIALS` is also supported. `GOOGLE_VISION_FEATURES` controls the Google features requested; the current live setting is `text,landmark,logo,label,web`, which returns OCR structure plus landmark, logo, label, and web-detection clues. Leave `OCR_PROVIDER=none` only when you want OpenRouter-only clue extraction without OCR.

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
google_labels        detected general image labels
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
final_geolocation_agent.json final coordinate decision from the final agent
final_result_validation.json backend validation summary for the final result
geolocation_graph.json   full LangGraph workflow output
```

## Prompt Files

Agent prompts are stored as Markdown files so they can be reviewed and improved without changing application code:

```text
backend/prompts/vision_clue_agent.md
backend/prompts/final_geolocation_agent.md
```

The vision clue prompt focuses only on observable image evidence. The final geolocation prompt combines Google Vision evidence and Gemini clue extraction to choose the most likely coordinates.

## Required Setup

1. Create a Mapbox public token from your Mapbox account.
2. Paste it into the app.
3. Use the default geolocation API endpoint, or set it to `http://localhost:8000/geolocate`.
4. Upload an image or enter an image URL.
5. Click `Analyze`.

The `Clear Pin` button removes the current marker and resets the map view.

## UI Surfaces

The side panel remains the full control and debugging surface. A floating dark translucent quick-action panel sits over the globe and uses the same shared state and functions, so File/URL selection, previews, Analyze, Clear Pin, and previous-result loading stay synchronized.

## Image Inputs

Files must be PNG, JPG, JPEG, or WebP and 10 MB or smaller.

Image URLs must start with `http://` or `https://` and the URL path must end in `.png`, `.jpg`, `.jpeg`, or `.webp`.

## Map Style

The app uses a custom Mapbox style with globe projection:

```js
style: "mapbox://styles/renceboey/cmt6tk6rx006q01skha9ndkbs",
projection: "globe"
```

## References

- [Mapbox GL JS documentation](https://docs.mapbox.com/mapbox-gl-js/guides/) - used for the interactive globe, markers, camera movement, popups, and map styling.
- [Mapbox Dark 2D style reference](https://www.mapbox.com/gallery#mapbox-dark-2d) - used as the visual reference for the dark monochrome map theme.
- [Google Cloud Vision documentation](https://cloud.google.com/vision/docs) - used for OCR, landmark detection, logo detection, and web-detection evidence.
- [OpenRouter documentation](https://openrouter.ai/docs) - used to call Gemini vision models through a single model API gateway.
- [LangGraph documentation](https://langchain-ai.github.io/langgraph/) - used to structure the backend workflow so Google Vision and Gemini clue extraction can run as separate steps before the final geolocation agent.
- [OceanIR](https://app.oceanir.ai/?panel=history) - used as a product reference for image geolocation workflow, history, and result presentation.
- [OceanIR photo location finder](https://oceanir.ai/photo-location-finder) - used as a reference for visible-evidence geolocation without relying on EXIF/GPS metadata.
- [Picarta](https://picarta.ai/picarta-v2) - used as another product reference for AI-assisted photo geolocation and coordinate output.
