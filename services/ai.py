import base64
import json
import logging
from dataclasses import dataclass

from config import AI_PROVIDER, ANTHROPIC_API_KEY, CLAUDE_CLI_PATH, GEMINI_API_KEY
from services.nutrition import calc_calories

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
【核心任務】
你是台灣飲食熱量估算助理，透過視覺或文字分析辨識食物種類，依據營養資料庫精準估算營養成分。

分析使用者提供的食物（照片、文字或兩者），只輸出一個合法 JSON，不得有任何前綴文字、後綴文字或 markdown。

【輸入類型處理】
- 純文字：依描述估算；缺份量時套用「台灣餐廳一人份」，confidence 預設 medium
- 純照片：依視覺辨識，confidence 最高為 medium（無文字補充份量資訊）
- 照片＋文字：以文字份量資訊覆蓋視覺估算

【估算原則】
- 預設份量：台灣常見餐廳一人份
- 使用者補充份量時優先採用
- 不確定時偏高估：醬汁、烹調油、勾芡、滷汁一律計入
- 永遠給出估算值，不拒絕分析

【常見錨點】
- 炸排骨便當（含配菜）：800-900 kcal
- 炸雞腿便當（含配菜）：850-950 kcal
- 滷肉飯（一碗）：400-500 kcal
- 蛋炒飯（餐廳一盤）：680-800 kcal
- 鮮奶茶 3分糖 700ml：250-300 kcal
- 燙青菜＋肉燥一匙：90-120 kcal

【視覺份量參考】
- 使用者手掌（不含手指）約 10×9cm，照片中可作為比例尺
- 一顆雞蛋 ≈ 55g

【confidence 標準】
- high：食物種類與份量皆明確
- medium：食物種類明確但份量需推估
- low：食物種類或份量任一不確定

【範例】
輸入：「滷肉飯加蛋」
輸出：
{"description":"滷肉飯加蛋","protein_g":24.0,"carbs_g":72.0,"fat_g":19.0,"confidence":"medium","note":"白飯200g + 滷肉醬80g + 荷包蛋55g + 烹調油"}"""

FOOD_JSON_SCHEMA = {
    "type": "object",
    "required": ["description", "protein_g", "carbs_g", "fat_g", "confidence", "note"],
    "properties": {
        "description": {"type": "string"},
        "protein_g": {"type": "number"},
        "carbs_g": {"type": "number"},
        "fat_g": {"type": "number"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "note": {"type": "string"},
    },
}


@dataclass
class FoodAnalysis:
    description: str
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    confidence: str
    note: str
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    provider: str = ""


def parse_ai_response(raw: str) -> FoodAnalysis:
    """解析 AI 回傳的 JSON 字串為 FoodAnalysis。

    處理可能的 markdown code fence 包裹，以及偶發的畸形 JSON。
    """
    text = raw.strip()
    # 移除 markdown code fence
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
        text = text.rstrip("`").strip()

    # 嘗試解析，失敗則修復常見畸形後重試
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        import re
        # 嘗試只擷取 {...} 部分
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group()
        # 修復常見畸形：key">value → key":value
        text = re.sub(r'"\s*>\s*', '": ', text)
        try:
            data = json.loads(text)
            logger.warning("AI 回傳畸形 JSON，已自動修復")
        except json.JSONDecodeError:
            logger.error("無法解析 AI 回傳: %s", raw)
            raise ValueError(f"AI 回傳無法解析的格式: {raw[:200]}")

    protein_g = float(data["protein_g"])
    carbs_g = float(data["carbs_g"])
    fat_g = float(data["fat_g"])

    conf = data.get("confidence", "medium")
    if isinstance(conf, (int, float)):
        conf = "high" if conf >= 0.8 else "medium" if conf >= 0.5 else "low"

    return FoodAnalysis(
        description=data["description"],
        calories=calc_calories(protein_g, carbs_g, fat_g),
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        confidence=conf,
        note=data.get("note", ""),
    )


# ── Gemini ────────────────────────────────────────────


async def _analyze_gemini(
    text: str | None = None,
    image_path: str | None = None,
) -> FoodAnalysis:
    """透過 Gemini API 分析食物。"""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)

    contents = []
    if image_path:
        with open(image_path, "rb") as f:
            image_data = f.read()
        ext = image_path.rsplit(".", 1)[-1].lower()
        mime_type = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
        }.get(ext, "image/jpeg")
        contents.append(types.Part.from_bytes(data=image_data, mime_type=mime_type))

    if text:
        contents.append(types.Part.from_text(text=text))

    if not contents:
        raise ValueError("至少需要提供文字或照片")

    logger.info("Calling Gemini API for food analysis")
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_json_schema=FOOD_JSON_SCHEMA,
            max_output_tokens=8192,
        ),
    )

    raw = response.text
    if not raw:
        # 可能被安全過濾或模型未回應
        block_reason = getattr(response, "prompt_feedback", None)
        logger.error("Gemini 回傳空內容, prompt_feedback=%s, candidates=%s", block_reason, response.candidates)
        raise ValueError(f"Gemini 回傳空內容（可能被安全過濾）: {block_reason}")
    logger.info("Gemini raw response: %s", raw)
    data = json.loads(raw)

    input_tokens = 0
    output_tokens = 0
    thinking_tokens = 0
    if response.usage_metadata:
        input_tokens = response.usage_metadata.prompt_token_count or 0
        output_tokens = response.usage_metadata.candidates_token_count or 0
        thinking_tokens = response.usage_metadata.thoughts_token_count or 0

    protein_g = float(data["protein_g"])
    carbs_g = float(data["carbs_g"])
    fat_g = float(data["fat_g"])

    return FoodAnalysis(
        description=data["description"],
        calories=calc_calories(protein_g, carbs_g, fat_g),
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        confidence=data["confidence"],
        note=data.get("note", ""),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        provider="gemini",
    )


# ── Claude ────────────────────────────────────────────


async def _analyze_claude(
    text: str | None = None,
    image_path: str | None = None,
) -> FoodAnalysis:
    """透過 Claude API 分析食物。"""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    content = []

    if image_path:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
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
    result = parse_ai_response(raw)
    result.input_tokens = response.usage.input_tokens
    result.output_tokens = response.usage.output_tokens
    result.provider = "claude-api"
    return result


# ── Claude CLI ────────────────────────────────────────


async def _analyze_claude_cli(
    text: str | None = None,
    image_path: str | None = None,
) -> FoodAnalysis:
    """透過 claude -p CLI 分析食物（使用 Max 訂閱，零 API 費用）。"""
    import asyncio
    import os

    prompt_parts = [SYSTEM_PROMPT, "\n\n---\n\n"]
    if text:
        prompt_parts.append(f"使用者輸入：{text}")
    if image_path:
        abs_path = os.path.abspath(image_path)
        prompt_parts.append(f"\n請讀取並分析這張食物照片：{abs_path}")
    if not text and not image_path:
        raise ValueError("至少需要提供文字或照片")

    cmd = [CLAUDE_CLI_PATH, "-p", "".join(prompt_parts), "--output-format", "json"]
    if image_path:
        cmd.extend(["--allowedTools", "Read"])

    logger.info("Calling claude -p CLI for food analysis")
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
    except asyncio.TimeoutError:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise ValueError("claude -p 逾時 (60s)")

    if process.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace")[:200] if stderr else "unknown"
        raise ValueError(f"claude -p 非零結束碼 ({process.returncode}): {err_msg}")

    output = json.loads(stdout.decode("utf-8"))
    raw_text = output.get("result", "")
    if not raw_text:
        raise ValueError("claude -p 回傳空結果")

    logger.info("claude -p raw result: %s", raw_text[:300])
    result = parse_ai_response(raw_text)

    # 從 envelope 提取 token 用量（資訊記錄用，費用為 $0）
    usage = output.get("usage", {})
    result.input_tokens = usage.get("input_tokens", 0) or 0
    result.output_tokens = usage.get("output_tokens", 0) or 0
    result.provider = "claude-cli"
    return result


# ── 統一入口 ──────────────────────────────────────────


async def analyze_food(
    text: str | None = None,
    image_path: str | None = None,
) -> FoodAnalysis:
    """分析食物：Gemini API → claude -p CLI fallback。

    若 AI_PROVIDER="claude" 則直接使用 Claude API（無 fallback）。
    """
    if AI_PROVIDER == "claude":
        return await _analyze_claude(text=text, image_path=image_path)

    # Primary: Gemini
    try:
        return await _analyze_gemini(text=text, image_path=image_path)
    except Exception as e:
        logger.warning("Gemini 分析失敗，切換至 claude -p: %s", e)

    # Fallback: claude -p CLI
    try:
        return await _analyze_claude_cli(text=text, image_path=image_path)
    except Exception as e:
        logger.error("claude -p 也失敗: %s", e)
        raise RuntimeError("AI 分析全部失敗（Gemini + claude -p）") from e
