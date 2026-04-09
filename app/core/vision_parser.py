"""Vision parser — uses Gemini Vision to describe charts and images from PDFs.

Sends extracted images to a multimodal LLM and returns text descriptions
that can be embedded alongside the source text for richer RAG retrieval.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from langchain_core.messages import HumanMessage

from app.config import get_settings
from app.core.llm_client import get_llm_client

logger = logging.getLogger(__name__)

VISION_PROMPT = """Analyze this image from Khazanah Nasional Berhad's Annual Review. Describe what you see in detail:

1. If it's a CHART or GRAPH: describe the type (bar, pie, line), the axes/labels, all data values you can read, and the trend or key takeaway.
2. If it's a TABLE: transcribe the headers and all data cells as accurately as possible.
3. If it's an INFOGRAPHIC: describe the layout, key figures, labels, and any relationships shown.
4. If it's a LOGO or DECORATIVE IMAGE: respond with just "decorative" — no further description needed.

Be precise with numbers and currency values (RM billion, %, etc.). Include ALL readable data points."""

# Models known to support vision
VISION_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
]


async def describe_image(
    image_bytes: bytes,
    page_number: int = 0,
    source_file: str = "",
    model_override: str | None = None,
) -> str | None:
    """Send an image to the vision LLM and get a text description.

    Args:
        image_bytes: Raw PNG/JPEG image bytes.
        page_number: Source page number for logging.
        source_file: Source filename for logging.
        model_override: Specific model to use (must support vision).

    Returns:
        Text description of the image, or None if analysis fails or image is decorative.
    """
    settings = get_settings()
    llm_client = get_llm_client()

    # Use the default model — Gemini models support multimodal natively
    vision_model = model_override or settings.gemini_model

    try:
        # Build multimodal message with base64-encoded image
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        message = HumanMessage(
            content=[
                {"type": "text", "text": VISION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                },
            ]
        )

        model = llm_client.get_chat_model(temperature=0.1, model_override=vision_model)
        response = await model.ainvoke([message])
        description = response.content.strip()

        # Skip decorative images
        if description.lower().startswith("decorative"):
            logger.debug(f"Skipping decorative image on page {page_number} of {source_file}")
            return None

        logger.info(f"Described image on page {page_number} of {source_file} ({len(description)} chars)")
        return description

    except Exception as e:
        logger.warning(f"Vision analysis failed for page {page_number} of {source_file}: {e}")
        return None


async def describe_images_batch(
    images: list[tuple[bytes, int, str]],
    model_override: str | None = None,
    rate_limit_delay: float = 2.0,
) -> list[dict[str, Any]]:
    """Describe multiple images with rate limiting.

    Args:
        images: List of (image_bytes, page_number, source_file) tuples.
        model_override: Specific vision model to use.
        rate_limit_delay: Seconds between API calls.

    Returns:
        List of dicts with page, source, and description.
    """
    import asyncio

    results = []
    for i, (image_bytes, page_num, source_file) in enumerate(images):
        if i > 0:
            await asyncio.sleep(rate_limit_delay)

        description = await describe_image(
            image_bytes,
            page_number=page_num,
            source_file=source_file,
            model_override=model_override,
        )

        if description:
            results.append({
                "page": page_num,
                "source": source_file,
                "description": description,
                "content_type": "image_description",
            })

    logger.info(f"Described {len(results)}/{len(images)} images (skipped {len(images) - len(results)} decorative)")
    return results
