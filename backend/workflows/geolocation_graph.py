import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agent_result_logger import AgentResultLogger
from agents.final_geolocation_agent import run_final_geolocation_agent
from agents.vision_ocr_agent import (
    run_ocr_tool,
    run_vision_clue_model,
)
from schemas import FinalGeolocationResult, GeolocationWorkflowResult, GoogleVisionResult, ImageInfo, VisionClues
from settings import get_settings


class GeolocationState(TypedDict, total=False):
    image_bytes: bytes
    image_info: ImageInfo
    source_image_url: str | None
    result_logger: AgentResultLogger
    google_vision: GoogleVisionResult
    gemini_clues: VisionClues
    final_result: FinalGeolocationResult
    warnings: Annotated[list[str], operator.add]


async def google_vision_node(state: GeolocationState) -> dict[str, Any]:
    logger = state["result_logger"]
    warnings: list[str] = []

    try:
        google_vision = await run_ocr_tool(state["image_bytes"])
    except Exception as exc:
        google_vision = GoogleVisionResult()
        warnings.append(str(exc))
        logger.write(
            "google_vision",
            {
                "agent": "google_vision",
                "status": "error",
                "error": str(exc),
            },
        )
    else:
        logger.write(
            "google_vision",
            {
                "agent": "google_vision",
                "status": "ok",
                "features": get_settings().google_vision_features,
                "result": google_vision.model_dump(),
            },
        )

    return {"google_vision": google_vision, "warnings": warnings}


async def gemini_clue_node(state: GeolocationState) -> dict[str, Any]:
    logger = state["result_logger"]
    warnings: list[str] = []

    try:
        model_clues = await run_vision_clue_model(
            image_bytes=state["image_bytes"],
            source_image_url=state.get("source_image_url"),
            result_logger=logger,
        )
    except Exception as exc:
        warnings.append(str(exc))
        model_clues = VisionClues(notes=["Vision clue model failed; returned empty Gemini clue result."])

    return {"gemini_clues": model_clues, "warnings": warnings}


async def final_geolocation_node(state: GeolocationState) -> dict[str, Any]:
    logger = state["result_logger"]
    warnings: list[str] = []

    try:
        final_result = await run_final_geolocation_agent(
            state.get("google_vision") or GoogleVisionResult(),
            state["gemini_clues"],
            logger,
        )
    except Exception as exc:
        warnings.append(str(exc))
        final_result = FinalGeolocationResult(
            location=None,
            confidence=0.0,
            evidence_used=[],
            evidence_conflicts=[],
            reasoning="Final geolocation model failed; no defensible coordinates were produced.",
            needs_manual_review=True,
        )

    return {"final_result": final_result, "warnings": warnings}


async def validate_final_result_node(state: GeolocationState) -> dict[str, Any]:
    logger = state["result_logger"]
    final_result = state["final_result"]
    warnings: list[str] = []

    if final_result.location is None:
        final_result.confidence = 0.0
        final_result.needs_manual_review = True
        warnings.append("Final result had no location; forced needs_manual_review=true and confidence=0.0.")
    elif final_result.confidence < 0.75:
        final_result.needs_manual_review = True
        warnings.append("Final result confidence is below 0.75; forced needs_manual_review=true.")

    logger.write(
        "final_result_validation",
        {
            "agent": "final_result_validation",
            "status": "ok",
            "rules": [
                "location=null => confidence=0.0 and needs_manual_review=true",
                "confidence < 0.75 => needs_manual_review=true",
            ],
            "result": final_result.model_dump(),
            "warnings": warnings,
        },
    )
    return {"final_result": final_result, "warnings": warnings}


def build_geolocation_graph():
    graph = StateGraph(GeolocationState)
    graph.add_node("google_vision", google_vision_node)
    graph.add_node("gemini_clues", gemini_clue_node)
    graph.add_node("final_geolocation", final_geolocation_node)
    graph.add_node("validate_final_result", validate_final_result_node)

    graph.add_edge(START, "google_vision")
    graph.add_edge(START, "gemini_clues")
    graph.add_edge(["google_vision", "gemini_clues"], "final_geolocation")
    graph.add_edge("final_geolocation", "validate_final_result")
    graph.add_edge("validate_final_result", END)
    return graph.compile()


GEOLOCATION_GRAPH = build_geolocation_graph()


async def geolocate_with_graph(
    image_bytes: bytes,
    image_info: ImageInfo,
    source_image_url: str | None = None,
) -> GeolocationWorkflowResult:
    logger = AgentResultLogger()
    state = await GEOLOCATION_GRAPH.ainvoke(
        {
            "image_bytes": image_bytes,
            "image_info": image_info,
            "source_image_url": source_image_url,
            "result_logger": logger,
            "warnings": [],
        }
    )

    result = GeolocationWorkflowResult(
        image=image_info,
        agent_result_run_id=logger.run_id,
        agent_result_dir=logger.relative_run_dir(),
        google_vision=state.get("google_vision") or GoogleVisionResult(),
        gemini_clues=state["gemini_clues"],
        final=state["final_result"],
        location=state["final_result"].location,
        confidence=state["final_result"].confidence,
        warnings=state.get("warnings", []),
    )
    logger.write(
        "geolocation_graph",
        {
            "agent": "langgraph_orchestrator",
            "status": "ok",
            "nodes": ["google_vision", "gemini_clues", "final_geolocation", "validate_final_result"],
            "result": result.model_dump(),
        },
    )
    return result
