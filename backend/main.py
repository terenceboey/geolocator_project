import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agent_result_logger import AGENT_RESULT_DIR
from agents.vision_ocr_agent import vision_ocr_agent
from image_loader import inspect_image, load_image_bytes
from schemas import ClueExtractionResult, GeolocationWorkflowResult, ImagePayload
from settings import get_settings
from workflows.geolocation_graph import geolocate_with_graph


settings = get_settings()
RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z_[a-f0-9]{8}$")

app = FastAPI(
    title="Image Geolocation Backend",
    description="Backend orchestrator for image geolocation agents. The first implemented stage extracts visual/OCR clues.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extract-clues", response_model=ClueExtractionResult)
async def extract_clues(payload: ImagePayload) -> ClueExtractionResult:
    try:
        original_bytes = await load_image_bytes(payload)
        image_info = inspect_image(original_bytes)
        if payload.image_url:
            image_info.source = "url"
        # Preserve original pixels for OCR/vision accuracy; validation ignores EXIF/GPS metadata.
        # URL uploads are still downloaded for validation/OCR, but the model receives the original URL.
        return await vision_ocr_agent(original_bytes, image_info, source_image_url=payload.image_url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/geolocate", response_model=GeolocationWorkflowResult)
async def geolocate(payload: ImagePayload) -> GeolocationWorkflowResult:
    try:
        original_bytes = await load_image_bytes(payload)
        image_info = inspect_image(original_bytes)
        if payload.image_url:
            image_info.source = "url"
        return await geolocate_with_graph(original_bytes, image_info, source_image_url=payload.image_url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def read_agent_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_dir(run_id: str) -> Path:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise HTTPException(status_code=404, detail="Agent result run not found.")
    path = (AGENT_RESULT_DIR / run_id).resolve()
    root = AGENT_RESULT_DIR.resolve()
    if root not in path.parents or not path.is_dir():
        raise HTTPException(status_code=404, detail="Agent result run not found.")
    return path


@app.get("/agent-results")
async def list_agent_results(limit: int = 20) -> dict:
    results: list[dict] = []
    limit = max(1, min(limit, 100))

    for path in sorted(AGENT_RESULT_DIR.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True):
        if len(results) >= limit:
            break
        if not path.is_dir() or not RUN_ID_PATTERN.fullmatch(path.name):
            continue

        graph_path = path / "geolocation_graph.json"
        if not graph_path.exists():
            continue

        try:
            graph = read_agent_json(graph_path)
            result = graph.get("result") or {}
            final = result.get("final") or {}
            location = result.get("location") or final.get("location")
        except Exception:
            continue

        results.append(
            {
                "run_id": path.name,
                "agent_result_dir": str(Path("agent_result") / path.name),
                "location": location,
                "confidence": result.get("confidence", final.get("confidence")),
                "needs_manual_review": final.get("needs_manual_review"),
                "reasoning": final.get("reasoning", ""),
                "created_at": path.name.split("_", 1)[0],
            }
        )

    return {"results": results}


@app.get("/agent-results/{run_id}")
async def get_agent_result(run_id: str) -> dict:
    path = run_dir(run_id)
    files: dict[str, dict] = {}
    for file_path in sorted(path.glob("*.json")):
        files[file_path.name] = read_agent_json(file_path)

    graph = files.get("geolocation_graph.json")
    if not graph:
        raise HTTPException(status_code=404, detail="Geolocation graph result not found for this run.")

    result = json.loads(json.dumps(graph.get("result") or {}))
    result["agent_files"] = files
    return result
