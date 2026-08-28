import base64
import json
from io import BytesIO
from typing import Any

from PIL import Image

from agent_result_logger import AgentResultLogger
from prompt_loader import load_prompt
from schemas import (
    ClueExtractionResult,
    GoogleVisionResult,
    ImageInfo,
    OCRTextGroup,
    OCRTextItem,
    VisionClues,
    VisionDetection,
    WebEntity,
    WebPageMatch,
)
from settings import get_settings


def image_bytes_to_data_url(image_bytes: bytes) -> str:
    with Image.open(BytesIO(image_bytes)) as image:
        mime = {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
        }.get(image.format or "JPEG", "image/jpeg")
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def model_image_reference(image_bytes: bytes, source_image_url: str | None) -> str:
    # URL uploads keep their original URL for model input; file uploads use inline image bytes.
    return source_image_url or image_bytes_to_data_url(image_bytes)


def model_image_reference_summary(image_bytes: bytes, source_image_url: str | None) -> dict[str, Any]:
    if source_image_url:
        return {
            "type": "image_url",
            "url": source_image_url,
        }

    with Image.open(BytesIO(image_bytes)) as image:
        return {
            "type": "inline_data_url",
            "mime_type": {
                "JPEG": "image/jpeg",
                "PNG": "image/png",
                "WEBP": "image/webp",
            }.get(image.format or "JPEG", "image/jpeg"),
            "width": image.width,
            "height": image.height,
            "byte_size": len(image_bytes),
            "base64_omitted": True,
        }


def _preview_text(value: str, limit: int = 700) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def build_google_vision_credentials():
    from google.oauth2 import service_account

    settings = get_settings()
    credentials_json = settings.google_application_credentials_json
    credentials_path = settings.google_application_credentials

    if credentials_json:
        return service_account.Credentials.from_service_account_info(json.loads(credentials_json))

    if credentials_path and credentials_path.strip().startswith("{"):
        return service_account.Credentials.from_service_account_info(json.loads(credentials_path))

    if credentials_path:
        return service_account.Credentials.from_service_account_file(credentials_path)

    return None


def google_vertices_to_bbox(vertices: Any) -> list[float]:
    return [float(value or 0) for vertex in vertices for value in (getattr(vertex, "x", 0), getattr(vertex, "y", 0))]


def merge_bboxes(bboxes: list[list[float] | None]) -> list[float] | None:
    points = [(bbox[index], bbox[index + 1]) for bbox in bboxes if bbox for index in range(0, len(bbox), 2)]
    if not points:
        return None

    min_x = min(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_x = max(point[0] for point in points)
    max_y = max(point[1] for point in points)
    return [min_x, min_y, max_x, min_y, max_x, max_y, min_x, max_y]


def average_confidence(values: list[float | None]) -> float | None:
    clean_values = [value for value in values if value is not None]
    if not clean_values:
        return None
    return sum(clean_values) / len(clean_values)


def word_text(word: Any) -> str:
    return "".join(symbol.text for symbol in word.symbols).strip()


def text_group_from_block(block: Any) -> OCRTextGroup:
    words: list[str] = []
    word_bboxes: list[list[float] | None] = []
    word_confidences: list[float | None] = []

    for paragraph in block.paragraphs:
        for word in paragraph.words:
            text = word_text(word)
            if text:
                words.append(text)
                word_bboxes.append(google_vertices_to_bbox(word.bounding_box.vertices))
                word_confidences.append(float(word.confidence) if word.confidence else None)

    return OCRTextGroup(
        text=" ".join(words),
        confidence=average_confidence(word_confidences),
        bbox=merge_bboxes(word_bboxes) or google_vertices_to_bbox(block.bounding_box.vertices),
    )


def ocr_lines_from_full_text(full_text: str | None) -> list[OCRTextGroup]:
    if not full_text:
        return []
    return [
        OCRTextGroup(text=line.strip(), source="google_vision_full_text")
        for line in full_text.splitlines()
        if line.strip()
    ]


def parse_google_full_text_annotation(full_text_annotation: Any) -> tuple[str | None, list[OCRTextGroup], list[OCRTextGroup]]:
    full_text = full_text_annotation.text or None
    lines = ocr_lines_from_full_text(full_text)
    blocks: list[OCRTextGroup] = []

    for page in full_text_annotation.pages:
        for block in page.blocks:
            group = text_group_from_block(block)
            if group.text:
                blocks.append(group)

    return full_text, lines, blocks


def parse_google_ocr_items(response: Any) -> list[OCRTextItem]:
    items: list[OCRTextItem] = []
    for annotation in response.text_annotations[1:]:
        bbox = google_vertices_to_bbox(annotation.bounding_poly.vertices)
        items.append(OCRTextItem(text=annotation.description, confidence=None, bbox=bbox, source="google_vision"))
    return items


def parse_google_landmarks(response: Any) -> list[VisionDetection]:
    detections: list[VisionDetection] = []
    for landmark in response.landmark_annotations:
        locations = [
            {"latitude": float(location.lat_lng.latitude), "longitude": float(location.lat_lng.longitude)}
            for location in landmark.locations
            if location.lat_lng
        ]
        detections.append(
            VisionDetection(
                name=landmark.description,
                confidence=float(landmark.score) if landmark.score else None,
                bbox=google_vertices_to_bbox(landmark.bounding_poly.vertices),
                locations=locations,
                source="google_landmark_detection",
            )
        )
    return detections


def parse_google_logos(response: Any) -> list[VisionDetection]:
    detections: list[VisionDetection] = []
    for logo in response.logo_annotations:
        detections.append(
            VisionDetection(
                name=logo.description,
                confidence=float(logo.score) if logo.score else None,
                bbox=google_vertices_to_bbox(logo.bounding_poly.vertices),
                source="google_logo_detection",
            )
        )
    return detections


def parse_google_web_detection(response: Any) -> tuple[list[WebEntity], list[WebPageMatch]]:
    web_detection = response.web_detection
    web_entities = [
        WebEntity(
            description=entity.description,
            score=float(entity.score) if entity.score else None,
            entity_id=entity.entity_id or None,
        )
        for entity in web_detection.web_entities
        if entity.description
    ]
    web_pages = [
        WebPageMatch(
            url=page.url,
            page_title=page.page_title or None,
            score=float(page.score) if page.score else None,
        )
        for page in web_detection.pages_with_matching_images
        if page.url
    ]
    return web_entities, web_pages


def google_vision_features(vision: Any) -> list[Any]:
    settings = get_settings()
    feature_names = {feature.strip().lower() for feature in settings.google_vision_features.split(",") if feature.strip()}
    feature_map = {
        "text": vision.Feature.Type.TEXT_DETECTION,
        "document_text": vision.Feature.Type.DOCUMENT_TEXT_DETECTION,
        "landmark": vision.Feature.Type.LANDMARK_DETECTION,
        "logo": vision.Feature.Type.LOGO_DETECTION,
        "web": vision.Feature.Type.WEB_DETECTION,
    }
    return [vision.Feature(type_=feature_map[name]) for name in feature_names if name in feature_map]


async def run_google_vision_ocr(image_bytes: bytes) -> GoogleVisionResult:
    try:
        from google.cloud import vision
    except ImportError as exc:
        raise RuntimeError("Install google-cloud-vision, or set OCR_PROVIDER=none.") from exc

    credentials = build_google_vision_credentials()
    client = vision.ImageAnnotatorClient(credentials=credentials)
    response = client.annotate_image(
        request=vision.AnnotateImageRequest(
            image=vision.Image(content=image_bytes),
            features=google_vision_features(vision),
        )
    )
    if response.error.message:
        raise RuntimeError(response.error.message)

    full_text, lines, blocks = parse_google_full_text_annotation(response.full_text_annotation)
    web_entities, web_pages = parse_google_web_detection(response)
    return GoogleVisionResult(
        ocr_items=parse_google_ocr_items(response),
        ocr_full_text=full_text,
        ocr_lines=lines,
        ocr_blocks=blocks,
        landmarks=parse_google_landmarks(response),
        logos=parse_google_logos(response),
        web_entities=web_entities,
        web_pages=web_pages,
    )


async def run_ocr_tool(image_bytes: bytes) -> GoogleVisionResult:
    settings = get_settings()

    if settings.ocr_provider == "google":
        return await run_google_vision_ocr(image_bytes)

    return GoogleVisionResult()


def parse_vision_json(raw_text: str) -> VisionClues:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    data = json.loads(text)
    list_fields = [
        "visible_text",
        "businesses",
        "landmarks",
        "road_signs",
        "languages",
        "architecture",
        "terrain",
        "vegetation",
        "vehicles",
        "road_layout",
        "water_coastline",
        "possible_regions",
        "search_queries",
        "notes",
    ]
    for field in list_fields:
        if isinstance(data.get(field), str):
            data[field] = [data[field]]
        elif data.get(field) is None:
            data[field] = []

    return VisionClues.model_validate(data)


def build_clue_prompt() -> str:
    # Prompt is loaded at request time so markdown edits are picked up without changing Python code.
    return load_prompt("vision_clue_agent.md")


async def run_openrouter_vision_clue_model(
    image_bytes: bytes,
    source_image_url: str | None = None,
    result_logger: AgentResultLogger | None = None,
) -> VisionClues:
    settings = get_settings()
    if not settings.openrouter_api_key:
        if result_logger:
            result_logger.write(
                "vision_clue_model",
                {
                    "agent": "vision_clue_model",
                    "provider": "openrouter",
                    "model": settings.openrouter_vision_model,
                    "status": "skipped",
                    "reason": "OPENROUTER_API_KEY is not set.",
                    "input": {
                        "prompt": None,
                        "image": model_image_reference_summary(image_bytes, source_image_url),
                    },
                },
            )
        raise RuntimeError("OPENROUTER_API_KEY is not set.")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    )
    prompt = build_clue_prompt()

    try:
        response = await client.chat.completions.create(
            model=settings.openrouter_vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": model_image_reference(image_bytes, source_image_url)}},
                    ],
                }
            ],
            temperature=0,
            max_tokens=settings.openrouter_max_tokens,
        )
    except Exception as exc:
        if result_logger:
            result_logger.write(
                "vision_clue_model",
                {
                    "agent": "vision_clue_model",
                    "provider": "openrouter",
                    "model": settings.openrouter_vision_model,
                    "status": "error",
                    "max_tokens": settings.openrouter_max_tokens,
                    "input": {
                        "prompt": prompt,
                        "image": model_image_reference_summary(image_bytes, source_image_url),
                    },
                    "error": str(exc),
                },
            )
        raise

    raw_text = response.choices[0].message.content or ""
    try:
        parsed = parse_vision_json(raw_text)
        if result_logger:
            result_logger.write(
                "vision_clue_model",
                {
                    "agent": "vision_clue_model",
                    "provider": "openrouter",
                    "model": settings.openrouter_vision_model,
                    "status": "ok",
                    "max_tokens": settings.openrouter_max_tokens,
                    "input": {
                        "prompt": prompt,
                        "image": model_image_reference_summary(image_bytes, source_image_url),
                    },
                    "raw_response": raw_text,
                    "parsed": parsed.model_dump(),
                },
            )
        return parsed
    except (json.JSONDecodeError, ValueError) as exc:
        if result_logger:
            result_logger.write(
                "vision_clue_model",
                {
                    "agent": "vision_clue_model",
                    "provider": "openrouter",
                    "model": settings.openrouter_vision_model,
                    "status": "invalid_json",
                    "max_tokens": settings.openrouter_max_tokens,
                    "input": {
                        "prompt": prompt,
                        "image": model_image_reference_summary(image_bytes, source_image_url),
                    },
                    "raw_response": raw_text,
                    "error": str(exc),
                },
            )
        raise RuntimeError(
            f"OpenRouter vision model returned invalid clue JSON. Response preview: {_preview_text(raw_text)}"
        ) from exc


async def run_openai_vision_clue_model(
    image_bytes: bytes,
    source_image_url: str | None = None,
    result_logger: AgentResultLogger | None = None,
) -> VisionClues:
    settings = get_settings()
    if not settings.openai_api_key:
        if result_logger:
            result_logger.write(
                "vision_clue_model",
                {
                    "agent": "vision_clue_model",
                    "provider": "openai",
                    "model": settings.openai_vision_model,
                    "status": "skipped",
                    "reason": "OPENAI_API_KEY is not set.",
                    "input": {
                        "prompt": None,
                        "image": model_image_reference_summary(image_bytes, source_image_url),
                    },
                },
            )
        raise RuntimeError("OPENAI_API_KEY is not set.")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    prompt = build_clue_prompt()

    try:
        response = await client.responses.create(
            model=settings.openai_vision_model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": model_image_reference(image_bytes, source_image_url), "detail": "high"},
                    ],
                }
            ],
        )
    except Exception as exc:
        if result_logger:
            result_logger.write(
                "vision_clue_model",
                {
                    "agent": "vision_clue_model",
                    "provider": "openai",
                    "model": settings.openai_vision_model,
                    "status": "error",
                    "input": {
                        "prompt": prompt,
                        "image": model_image_reference_summary(image_bytes, source_image_url),
                    },
                    "error": str(exc),
                },
            )
        raise

    try:
        parsed = parse_vision_json(response.output_text)
        if result_logger:
            result_logger.write(
                "vision_clue_model",
                {
                    "agent": "vision_clue_model",
                    "provider": "openai",
                    "model": settings.openai_vision_model,
                    "status": "ok",
                    "input": {
                        "prompt": prompt,
                        "image": model_image_reference_summary(image_bytes, source_image_url),
                    },
                    "raw_response": response.output_text,
                    "parsed": parsed.model_dump(),
                },
            )
        return parsed
    except (json.JSONDecodeError, ValueError) as exc:
        if result_logger:
            result_logger.write(
                "vision_clue_model",
                {
                    "agent": "vision_clue_model",
                    "provider": "openai",
                    "model": settings.openai_vision_model,
                    "status": "invalid_json",
                    "input": {
                        "prompt": prompt,
                        "image": model_image_reference_summary(image_bytes, source_image_url),
                    },
                    "raw_response": response.output_text,
                    "error": str(exc),
                },
            )
        raise RuntimeError(
            f"OpenAI vision model returned invalid clue JSON. Response preview: {_preview_text(response.output_text)}"
        ) from exc


async def run_vision_clue_model(
    image_bytes: bytes,
    source_image_url: str | None = None,
    result_logger: AgentResultLogger | None = None,
) -> VisionClues:
    settings = get_settings()

    if settings.vision_provider == "openrouter":
        return await run_openrouter_vision_clue_model(
            image_bytes=image_bytes,
            source_image_url=source_image_url,
            result_logger=result_logger,
        )

    if settings.vision_provider == "openai":
        return await run_openai_vision_clue_model(
            image_bytes=image_bytes,
            source_image_url=source_image_url,
            result_logger=result_logger,
        )

    if result_logger:
        result_logger.write(
            "vision_clue_model",
            {
                "agent": "vision_clue_model",
                "provider": settings.vision_provider,
                "status": "skipped",
                "reason": "VISION_PROVIDER is none.",
                "input": {
                    "prompt": build_clue_prompt(),
                    "image": model_image_reference_summary(image_bytes, source_image_url),
                },
            },
        )
    raise RuntimeError("VISION_PROVIDER is none.")


async def vision_ocr_agent(
    image_bytes: bytes,
    image_info: ImageInfo,
    source_image_url: str | None = None,
) -> ClueExtractionResult:
    # Agent node: combines OCR tooling, vision-model interpretation, and deterministic cleanup.
    result_logger = AgentResultLogger()
    warnings: list[str] = []

    try:
        google_vision = await run_ocr_tool(image_bytes)
    except Exception as exc:
        # OCR failures should not block the vision model from extracting broader clues.
        google_vision = GoogleVisionResult()
        warnings.append(str(exc))
        result_logger.write(
            "google_vision",
            {
                "agent": "google_vision",
                "status": "error",
                "error": str(exc),
            },
        )
    else:
        result_logger.write(
            "google_vision",
            {
                "agent": "google_vision",
                "status": "ok",
                "features": get_settings().google_vision_features,
                "result": google_vision.model_dump(),
            },
        )

    try:
        vision_clues = await run_vision_clue_model(
            image_bytes=image_bytes,
            source_image_url=source_image_url,
            result_logger=result_logger,
        )
    except Exception as exc:
        # Model/API failures should not inject Google Vision into Gemini clue output.
        warnings.append(str(exc))
        vision_clues = VisionClues(notes=["Vision clue model failed; returned empty Gemini clue result."])

    result = ClueExtractionResult(
        image=image_info,
        agent_result_run_id=result_logger.run_id,
        agent_result_dir=result_logger.relative_run_dir(),
        ocr_full_text=google_vision.ocr_full_text,
        ocr_lines=google_vision.ocr_lines,
        google_landmarks=google_vision.landmarks,
        google_logos=google_vision.logos,
        google_web_entities=google_vision.web_entities,
        google_web_pages=google_vision.web_pages,
        clues=vision_clues,
        warnings=warnings,
    )
    result_logger.write(
        "final_response",
        {
            "agent": "backend_orchestrator",
            "status": "ok",
            "result": result.model_dump(),
        },
    )
    return result
