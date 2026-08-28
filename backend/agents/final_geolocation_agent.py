import json
from typing import Any

from openai import AsyncOpenAI

from agent_result_logger import AgentResultLogger
from prompt_loader import load_prompt
from schemas import FinalGeolocationResult, GoogleVisionResult, VisionClues
from settings import get_settings


def strip_code_fence(raw_text: str) -> str:
    text = raw_text.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def google_vision_evidence(google_vision: GoogleVisionResult) -> dict[str, Any]:
    # Keep the final prompt compact while preserving the strongest structured Google evidence.
    return {
        "ocr_lines": [line.text for line in google_vision.ocr_lines[:20]],
        "landmarks": [item.model_dump(exclude_none=True) for item in google_vision.landmarks[:8]],
        "logos": [item.model_dump(exclude_none=True) for item in google_vision.logos[:8]],
        "web_entities": [item.model_dump(exclude_none=True) for item in google_vision.web_entities[:8]],
        "web_pages": [item.model_dump(exclude_none=True) for item in google_vision.web_pages[:5]],
    }


def build_final_geolocation_prompt(google_vision: GoogleVisionResult, gemini_clues: VisionClues) -> str:
    base_prompt = load_prompt("final_geolocation_agent.md")
    evidence = {
        "google_vision": google_vision_evidence(google_vision),
        "gemini_clues": gemini_clues.model_dump(),
    }
    return f"{base_prompt}\n\nEvidence:\n{json.dumps(evidence, ensure_ascii=False)}"


def parse_final_geolocation_json(raw_text: str) -> FinalGeolocationResult:
    data = json.loads(strip_code_fence(raw_text))
    confidence = data.get("confidence")
    if isinstance(confidence, str):
        try:
            confidence = float(confidence)
        except ValueError:
            confidence = 0.0
    if confidence is None:
        confidence = 0.0
    data["confidence"] = max(0.0, min(1.0, float(confidence)))
    return FinalGeolocationResult.model_validate(data)


async def run_final_geolocation_agent(
    google_vision: GoogleVisionResult,
    gemini_clues: VisionClues,
    result_logger: AgentResultLogger,
) -> FinalGeolocationResult:
    settings = get_settings()
    prompt = build_final_geolocation_prompt(google_vision, gemini_clues)

    if not settings.openrouter_api_key:
        result = FinalGeolocationResult(
            location=None,
            confidence=0.0,
            evidence_used=[],
            evidence_conflicts=[],
            reasoning="OPENROUTER_API_KEY is not set; final geolocation was skipped.",
            needs_manual_review=True,
        )
        result_logger.write(
            "final_geolocation_agent",
            {
                "agent": "final_geolocation_agent",
                "provider": "openrouter",
                "model": settings.openrouter_vision_model,
                "status": "skipped",
                "reason": "OPENROUTER_API_KEY is not set.",
                "input": {"prompt": prompt},
                "parsed": result.model_dump(),
            },
        )
        return result

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    )

    try:
        response = await client.chat.completions.create(
            model=settings.openrouter_vision_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=settings.openrouter_max_tokens,
        )
    except Exception as exc:
        result_logger.write(
            "final_geolocation_agent",
            {
                "agent": "final_geolocation_agent",
                "provider": "openrouter",
                "model": settings.openrouter_vision_model,
                "status": "error",
                "input": {"prompt": prompt},
                "error": str(exc),
            },
        )
        raise

    raw_text = response.choices[0].message.content or ""
    try:
        parsed = parse_final_geolocation_json(raw_text)
    except (json.JSONDecodeError, ValueError) as exc:
        result_logger.write(
            "final_geolocation_agent",
            {
                "agent": "final_geolocation_agent",
                "provider": "openrouter",
                "model": settings.openrouter_vision_model,
                "status": "invalid_json",
                "input": {"prompt": prompt},
                "raw_response": raw_text,
                "error": str(exc),
            },
        )
        raise RuntimeError(f"Final geolocation model returned invalid JSON: {raw_text[:700]}") from exc

    result_logger.write(
        "final_geolocation_agent",
        {
            "agent": "final_geolocation_agent",
            "provider": "openrouter",
            "model": settings.openrouter_vision_model,
            "status": "ok",
            "input": {"prompt": prompt},
            "raw_response": raw_text,
            "parsed": parsed.model_dump(),
        },
    )
    return parsed
