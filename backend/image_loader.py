import base64
from io import BytesIO
from urllib.parse import urlparse

import httpx
from PIL import Image, UnidentifiedImageError

from schemas import ImageInfo, ImagePayload
from settings import get_settings


ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _extension_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    dot_index = path.rfind(".")
    return path[dot_index:] if dot_index >= 0 else ""


async def load_image_bytes(payload: ImagePayload) -> bytes:
    settings = get_settings()

    if payload.image_b64:
        try:
            image_bytes = base64.b64decode(payload.image_b64, validate=True)
        except ValueError as exc:
            raise ValueError("image_b64 is not valid base64.") from exc
    else:
        image_url = str(payload.image_url)
        extension = _extension_from_url(image_url)
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("Image URL path must end in .png, .jpg, .jpeg, or .webp.")

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(image_url)
            response.raise_for_status()
            image_bytes = response.content

    if len(image_bytes) > settings.max_image_bytes:
        raise ValueError("Image must be 10 MB or smaller.")

    return image_bytes


def inspect_image(image_bytes: bytes) -> ImageInfo:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image_format = image.format
            width, height = image.size
    except UnidentifiedImageError as exc:
        raise ValueError("Uploaded content is not a supported image.") from exc

    if image_format not in ALLOWED_FORMATS:
        raise ValueError("Image must be PNG, JPG, JPEG, or WebP.")

    return ImageInfo(
        format=image_format,
        width=width,
        height=height,
        byte_size=len(image_bytes),
    )


def normalize_image(image_bytes: bytes, max_side: int = 1600) -> bytes:
    # No EXIF/GPS metadata is read or trusted; pixels are normalized only for OCR/vision.
    with Image.open(BytesIO(image_bytes)) as image:
        image = image.convert("RGB")
        image.thumbnail((max_side, max_side))
        output = BytesIO()
        image.save(output, format="JPEG", quality=92, optimize=True)
        return output.getvalue()

