import base64
import json
import logging
from dataclasses import dataclass

import anthropic

from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一個營養分析助理，專門分析台灣常見食物。

分析使用者提供的食物（照片和/或文字描述），回傳 JSON。

規則：
- 以台灣常見餐廳的一人份份量為預設基準
- 文字有補充份量資訊時（如「大碗」、「兩份」）優先採用
- 無法確定份量時，以一人份估算並標記 confidence 為 low
- 永遠給出估算值，不拒絕分析

只回傳以下 JSON，不要任何其他文字或 markdown：
{
  "description": "食物的簡短中文描述（15字以內）",
  "calories": 620,
  "protein_g": 22.0,
  "carbs_g": 85.0,
  "fat_g": 18.0,
  "confidence": "high|medium|low",
  "note": "不確定之處說明，無則空字串"
}"""

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


@dataclass
class FoodAnalysis:
    description: str
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    confidence: str
    note: str


def parse_ai_response(raw: str) -> FoodAnalysis:
    """解析 Claude 回傳的 JSON 字串為 FoodAnalysis。

    處理可能的 markdown code fence 包裹。
    """
    text = raw.strip()
    # 移除 markdown code fence
    if text.startswith("```"):
        # 移除開頭的 ```json 或 ```
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
        # 移除結尾的 ```
        text = text.rstrip("`").strip()

    data = json.loads(text)
    return FoodAnalysis(
        description=data["description"],
        calories=int(data["calories"]),
        protein_g=float(data["protein_g"]),
        carbs_g=float(data["carbs_g"]),
        fat_g=float(data["fat_g"]),
        confidence=data["confidence"],
        note=data.get("note", ""),
    )


async def analyze_food(
    text: str | None = None,
    image_path: str | None = None,
) -> FoodAnalysis:
    """呼叫 Claude API 分析食物，回傳 FoodAnalysis。"""
    content = []

    if image_path:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        # 從副檔名判斷 media type
        ext = image_path.rsplit(".", 1)[-1].lower()
        media_type = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
        }.get(ext, "image/jpeg")

        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": image_data},
            }
        )

    if text:
        content.append({"type": "text", "text": text})

    if not content:
        raise ValueError("至少需要提供文字或照片")

    logger.info("Calling Claude API for food analysis")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text
    logger.info("Claude raw response: %s", raw)
    return parse_ai_response(raw)
