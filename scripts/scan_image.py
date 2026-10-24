"""Extract text from job scam flyers, offer letters, or WhatsApp screenshots and verify with Jaanch.

Supports:
1. Local Tesseract OCR (via pytesseract) if installed.
2. ASI1 / Vision LLM OCR fallback (base64 image extraction).

Usage:
    python scripts/scan_image.py path/to/whatsapp_screenshot.png
    python scripts/scan_image.py path/to/offer_letter.jpg
"""

import asyncio
import base64
import os
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
import aiohttp  # noqa: E402

from jaanch import llm  # noqa: E402
from jaanch.pipeline import run_local  # noqa: E402


def extract_with_pytesseract(image_path: Path) -> Optional[str]:
    """Attempt local OCR using pytesseract if available."""
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        if text and len(text.strip()) > 20:
            return text.strip()
    except Exception:
        pass
    return None


async def extract_with_vision_api(image_path: Path) -> Optional[str]:
    """Extract text from image using ASI1 / Vision endpoint with base64 encoding."""
    key = os.getenv("ASI1_API_KEY") or os.getenv("ASI_ONE_API_KEY")
    if not key:
        return None

    mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    data_url = f"data:{mime};base64,{b64}"
    body = {
        "model": os.getenv("ASI1_MODEL", "asi1"),
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Transcribe the exact text from this job/internship offer screenshot or flyer. Return ONLY the extracted text with no extra commentary.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            }
        ],
        "max_tokens": 1000,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post("https://api.asi1.ai/v1/chat/completions", json=body, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return None


async def main(image_path_str: str):
    image_path = Path(image_path_str)
    if not image_path.exists():
        sys.exit(f"Error: Image file not found at '{image_path}'")

    print(f"📸 Reading offer image: {image_path.name}...")

    # 1. Try local OCR first, then vision fallback
    extracted_text = extract_with_pytesseract(image_path)
    ocr_source = "Local Tesseract OCR"
    if not extracted_text:
        extracted_text = await extract_with_vision_api(image_path)
        ocr_source = "ASI1 Vision Model"

    if not extracted_text:
        sys.exit(
            "❌ Could not extract text from image.\n"
            "Tip: Install 'pytesseract' with Tesseract-OCR, or set ASI1_API_KEY in .env for vision transcription."
        )

    print(f"✅ Extracted text via {ocr_source}:\n" + "─" * 50)
    print(extracted_text[:400] + ("..." if len(extracted_text) > 400 else ""))
    print("─" * 50)

    # 2. Run Jaanch forensic scan on the transcribed text
    print("\n🔍 Running Jaanch multi-agent verification...")
    result = await run_local(extracted_text)

    print(f"\n📊 RISK SCORE: {result.risk}/10 — {result.verdict_text}")
    print("\nDetected Signals & Evidence:")
    for s in result.signals:
        mark = "▲" if s.weight > 0 else "✓"
        print(f"  {mark} {s.weight:+.1f}  {s.label} [{s.source}: {s.evidence[:80]}]")

    narration = await llm.explain(extracted_text, result.risk, result.verdict_text, result.signals)
    print(f"\n💬 Verdict Explanation:\n{narration}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()
    if len(sys.argv) < 2:
        sys.exit("Usage: python scripts/scan_image.py <path_to_image>")
    asyncio.run(main(sys.argv[1]))
