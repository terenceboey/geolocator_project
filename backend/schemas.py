from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ImagePayload(BaseModel):
    image_b64: str | None = None
    image_url: str | None = None
    filename: str | None = None

    @model_validator(mode="after")
    def require_one_image_source(self) -> "ImagePayload":
        if bool(self.image_b64) == bool(self.image_url):
            raise ValueError("Provide exactly one image source: image_b64 or image_url.")
        return self


class OCRTextItem(BaseModel):
    text: str
    confidence: float | None = None
    bbox: list[float] | None = None
    source: str = "ocr"


class OCRTextGroup(BaseModel):
    text: str
    confidence: float | None = None
    bbox: list[float] | None = None
    source: str = "google_vision"


class VisionDetection(BaseModel):
    name: str
    confidence: float | None = None
    bbox: list[float] | None = None
    locations: list[dict[str, float]] = Field(default_factory=list)
    source: str


class WebEntity(BaseModel):
    description: str
    score: float | None = None
    entity_id: str | None = None
    source: str = "google_web_detection"


class WebPageMatch(BaseModel):
    url: str
    page_title: str | None = None
    score: float | None = None
    source: str = "google_web_detection"


class GoogleVisionResult(BaseModel):
    ocr_items: list[OCRTextItem] = Field(default_factory=list)
    ocr_full_text: str | None = None
    ocr_lines: list[OCRTextGroup] = Field(default_factory=list)
    ocr_blocks: list[OCRTextGroup] = Field(default_factory=list)
    landmarks: list[VisionDetection] = Field(default_factory=list)
    logos: list[VisionDetection] = Field(default_factory=list)
    labels: list[VisionDetection] = Field(default_factory=list)
    web_entities: list[WebEntity] = Field(default_factory=list)
    web_pages: list[WebPageMatch] = Field(default_factory=list)


class VisionClues(BaseModel):
    visible_text: list[str] = Field(default_factory=list)
    businesses: list[str] = Field(default_factory=list)
    landmarks: list[str] = Field(default_factory=list)
    road_signs: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    architecture: list[str] = Field(default_factory=list)
    terrain: list[str] = Field(default_factory=list)
    vegetation: list[str] = Field(default_factory=list)
    vehicles: list[str] = Field(default_factory=list)
    road_layout: list[str] = Field(default_factory=list)
    water_coastline: list[str] = Field(default_factory=list)
    possible_regions: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ImageInfo(BaseModel):
    format: Literal["PNG", "JPEG", "WEBP"]
    width: int
    height: int
    byte_size: int
    source: Literal["file", "url"] = "file"


class ClueExtractionResult(BaseModel):
    image: ImageInfo
    agent_result_run_id: str | None = None
    agent_result_dir: str | None = None
    ocr_full_text: str | None = None
    ocr_lines: list[OCRTextGroup] = Field(default_factory=list)
    google_landmarks: list[VisionDetection] = Field(default_factory=list)
    google_logos: list[VisionDetection] = Field(default_factory=list)
    google_labels: list[VisionDetection] = Field(default_factory=list)
    google_web_entities: list[WebEntity] = Field(default_factory=list)
    google_web_pages: list[WebPageMatch] = Field(default_factory=list)
    clues: VisionClues
    warnings: list[str] = Field(default_factory=list)


class FinalLocation(BaseModel):
    latitude: float
    longitude: float
    name: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None


class FinalGeolocationResult(BaseModel):
    location: FinalLocation | None = None
    confidence: float = 0.0
    evidence_used: list[str] = Field(default_factory=list)
    evidence_conflicts: list[str] = Field(default_factory=list)
    reasoning: str = ""
    needs_manual_review: bool = True


class GeolocationWorkflowResult(BaseModel):
    image: ImageInfo
    agent_result_run_id: str | None = None
    agent_result_dir: str | None = None
    google_vision: GoogleVisionResult
    gemini_clues: VisionClues
    final: FinalGeolocationResult
    location: FinalLocation | None = None
    confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)
