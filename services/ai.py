import base64
import json
import logging
import re
from dataclasses import dataclass

from config import AI_PROVIDER, ANTHROPIC_API_KEY, CLAUDE_CLI_MODEL, CLAUDE_CLI_PATH, GEMINI_API_KEY
from services.nutrition import calc_calories

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
【任務】
你是台灣飲食熱量估算助理。分析使用者提供的食物資訊——文字描述、實體食物照片、
營養標示照片，或其組合——估算三大營養素。只輸出一個合法 JSON，不得有任何前綴文
字、後綴文字或 markdown。

【輸出格式】
{"description":"...","protein_g":數字,"carbs_g":數字,"fat_g":數字,
 "confidence":"high|medium|low","note":"..."}
- 系統只採計三大營養素，最終熱量以「4×蛋白質＋4×碳水＋9×脂肪」重算，你回傳的
  kcal 不會被使用。當目標熱量已知（官方值、標示值、定值錨）時，回傳的三大營養素
  必須使重算結果貼近目標熱量
- description：品名，含品牌與規格（若有）
- note：必須以「官方值：」「標示轉錄：」「推估：」三者之一逐字開頭（含全形冒號），
  後接數值依據與組成拆解。僅當熱量錨定官方資訊時用「官方值：」，且回填的三大營養
  素須註明；同一餐混合官方與非官方品項時，整筆用「推估：」、官方部分在後文說明
- confidence：high＝有官方值或標示依據，或種類與份量皆明確；medium＝種類明確但
  份量推估（實體食物照片無文字份量補充時最高 medium）；low＝種類或份量任一不確定

【數值來源優先序】
1. 營養標示照片：直接轉錄標示數值，不自行估算。注意標示基準（每份／每100g／
   每100ml），依使用者說明的食用量換算；未說明時以「整包／整瓶」計。note 標明
   採用基準與換算（如「每100ml×600ml整瓶」）。confidence high；標示不完整
   （看不到淨重或關鍵欄位）時以可見資訊推算，confidence 降為 medium。
2. 知名連鎖品牌品項（速食、超商、咖啡連鎖）：若你記憶中有官方公開營養資訊，
   優先採用。官方常只揭露熱量：以官方熱量為目標回填三大營養素（按品類合理比例，
   使 4-4-9 重算貼近官方熱量），note 用「官方值：」並註明回填。沒有把握時不得
   杜撰官方值，改走推估。
3. 手搖飲（含連鎖品牌）：官方僅依法揭露加糖量、無總熱量資訊——一律推估；
   命中【定值錨】品項與規格時直接採用錨點值，不自行變動。
4. 一般食物：預設份量為台灣餐廳／小吃一人份；使用者提供精確克數時，以【單位基準】
   逐項組合計算；以【品類校準區間】檢核合理性。

【估算原則】
- 照片與文字並存時，文字提供的份量與規格一律優先於視覺推估
- 描述末尾的 xN（如 x2、x0.5）為倍數：所有數值乘上 N，description 保留 xN 標記，
  note 註明
- 不確定時偏高估：醬汁、烹調油、勾芡、滷汁一律計入
- 永遠給出估算值，不拒絕分析
- 聚餐／多道菜的模糊總量描述（如「迴轉壽司約12盤」）：按描述拆解主要組成加總
  直接給總量，note 列拆解，不要求使用者逐道說明

【定值錨】（重複品項，命中規格時直接採用；note 以「推估：」開頭並註明命中定值錨）
- 手搖飲未註明容量時以 700cc（大杯）計；包裝品項有營養標示或官方值時優先走前兩層
- 700cc 奶精奶茶：全糖 525 kcal／半糖 435 kcal
- 700cc 鮮奶茶 3 分糖：280 kcal
- 400cc 豆漿：無糖 130 kcal／半糖 190 kcal

【品類校準區間】（泛用品項合理性檢核；品牌品項優先走官方值）
- 炸排骨／炸雞腿便當（含配菜白飯）：800-950 kcal
- 牛肉麵（一碗含湯）：600-900 kcal；乾拌麵／麻醬麵：500-650 kcal
- 早餐店肉蛋三明治：330-420 kcal；原味蛋餅：230-300 kcal；
  花生／奶酥厚片：320-420 kcal
- 葡式蛋塔 1 顆：210-260 kcal；紅豆餅 1 個：160-230 kcal

【單位基準】（使用者常給精確克數；數值以 TFDA 食品成分資料庫為準）
- 白飯（熟）100g：P 3／C 41／F 0.3（≈180 kcal）
- 蘋果 100g：P 0.2／C 14／F 0.1（≈58 kcal）；芭樂 100g：P 0.7／C 10／F 0.1（≈44 kcal）
- 雞蛋 1 顆（可食 55g）：P 6.5／C 1／F 4.8（≈73 kcal）
- 使用者手掌（不含手指）約 10×9cm，照片中可作比例尺

【範例】
輸入：「滷肉飯加蛋」
輸出：
{"description":"滷肉飯加蛋","protein_g":21.0,"carbs_g":87.0,"fat_g":22.0,"confidence":"medium","note":"推估：白飯200g + 滷肉醬80g + 荷包蛋55g + 烹調油"}

輸入：「7-11大杯冰拿鐵」
輸出：
{"description":"7-11 CITY CAFE 大杯冰拿鐵","protein_g":10.0,"carbs_g":15.0,"fat_g":10.0,"confidence":"high","note":"官方值：CITY CAFE 官方熱量標示 188 kcal，三大營養素依全脂鮮奶拿鐵比例回填"}

輸入：「迴轉壽司 大概12盤 主要鮭魚鮪魚」
輸出：
{"description":"迴轉壽司12盤（鮭魚鮪魚為主）","protein_g":85.0,"carbs_g":170.0,"fat_g":28.0,"confidence":"medium","note":"推估：12盤×2貫，醋飯約400g，生魚片約350g，含炙燒與醬料油脂"}"""

# note 標準關鍵字（v2）：供 parse soft-check 與未來校正係數機讀
NOTE_PREFIXES = ("官方值：", "標示轉錄：", "推估：")

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
    ai_model: str | None = None


def _normalize_model_name(raw: str) -> str:
    """去除 context window 變體後綴，e.g. 'claude-opus-4-7[1m]' → 'claude-opus-4-7'。"""
    return re.sub(r"\[.*?\]$", "", raw).strip()


# claude -p 的 modelUsage 各模型可能出現的 token 欄位。主判讀模型的 system prompt
# 幾乎全進 prompt cache，inputTokens 只剩個位數，故計分必須含 cache 兩欄，否則會被
# 沒有 cache 的內部 haiku（inputTokens ~900）壓過去（2026-09-04~09-05 誤記實案）。
_MODEL_USAGE_TOKEN_FIELDS = (
    "inputTokens",
    "outputTokens",
    "cacheReadInputTokens",
    "cacheCreationInputTokens",
)


def _model_total_tokens(usage: dict) -> int:
    """modelUsage 單一模型的總 token 量（含 prompt cache）。"""
    return sum(usage.get(field, 0) or 0 for field in _MODEL_USAGE_TOKEN_FIELDS)


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

    note = data.get("note", "")
    # soft-check：只警告不擋不改值，供觀測 v2 note 關鍵字遵守率
    if note and not note.startswith(NOTE_PREFIXES):
        logger.warning("note 未以標準關鍵字開頭（官方值：/標示轉錄：/推估：）: %s", note[:50])

    return FoodAnalysis(
        description=data["description"],
        calories=calc_calories(protein_g, carbs_g, fat_g),
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        confidence=conf,
        note=note,
    )


# ── Gemini ────────────────────────────────────────────


async def _analyze_gemini(
    text: str | None = None,
    image_paths: list[str] | None = None,
) -> FoodAnalysis:
    """透過 Gemini API 分析食物。"""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)

    contents = []
    for image_path in image_paths or []:
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

    if len(image_paths or []) > 1:
        # 相簿：多張照片屬同一餐，須合併成一份估算（見 handlers/meal.py 相簿聚合）
        contents.append(types.Part.from_text(
            text=f"以上 {len(image_paths)} 張照片是同一餐的不同角度或不同菜色，"
                 "請全部一起看、合併估算成一筆，勿重複計算同一道菜。"
        ))

    if text:
        contents.append(types.Part.from_text(text=text))

    if not contents:
        raise ValueError("至少需要提供文字或照片")

    logger.info("Calling Gemini API for food analysis")
    response = client.models.generate_content(
        model="gemini-3.1-pro-preview",
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
        ai_model=getattr(response, "model_version", None),
    )


# ── Claude ────────────────────────────────────────────


async def _analyze_claude(
    text: str | None = None,
    image_paths: list[str] | None = None,
) -> FoodAnalysis:
    """透過 Claude API 分析食物。"""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    content = []

    for image_path in image_paths or []:
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

    if len(image_paths or []) > 1:
        # 相簿：多張照片屬同一餐，須合併成一份估算（見 handlers/meal.py 相簿聚合）
        content.append({
            "type": "text",
            "text": f"以上 {len(image_paths)} 張照片是同一餐的不同角度或不同菜色，"
                    "請全部一起看、合併估算成一筆，勿重複計算同一道菜。",
        })

    if text:
        content.append({"type": "text", "text": text})

    if not content:
        raise ValueError("至少需要提供文字或照片")

    logger.info("Calling Claude API for food analysis")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
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
    image_paths: list[str] | None = None,
) -> FoodAnalysis:
    """透過 claude -p CLI 分析食物（使用 Max 訂閱，零 API 費用）。"""
    import asyncio
    import os

    paths = image_paths or []
    if not text and not paths:
        raise ValueError("至少需要提供文字或照片")

    user_parts = []
    if text:
        # 前綴確保 -p 引數不以 "-" 開頭（如「-18度C」），避免被 CLI 當 option 解析
        user_parts.append(f"使用者輸入：{text}")
    if len(paths) == 1:
        user_parts.append(f"請讀取並分析這張食物照片：{os.path.abspath(paths[0])}")
    elif paths:
        # 相簿：多張照片屬同一餐，須合併成一份估算（見 handlers/meal.py 相簿聚合）
        listed = "\n".join(f"- {os.path.abspath(p)}" for p in paths)
        user_parts.append(
            f"以下 {len(paths)} 張照片是同一餐的不同角度或不同菜色，"
            f"請全部讀取後合併估算成一筆，勿重複計算同一道菜：\n{listed}"
        )

    # 指令/資料分離：SYSTEM_PROMPT 走 --append-system-prompt，-p 只放使用者輸入
    cmd = [
        CLAUDE_CLI_PATH, "-p", "\n".join(user_parts),
        "--append-system-prompt", SYSTEM_PROMPT,
        "--output-format", "json", "--model", CLAUDE_CLI_MODEL,
    ]
    if paths:
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

    # 從 modelUsage 取實際判讀模型（稽核用）。
    # 新版 CLI（≥2.1.197）會在 modelUsage 併入內部小模型（如 haiku），主判讀模型
    # 是用量最大的那個；不能取第一個 key，否則會抓到內部 haiku 而非 --model 指定的模型。
    model_usage = output.get("modelUsage") or {}
    if model_usage:
        raw_model = max(model_usage, key=lambda m: _model_total_tokens(model_usage[m]))
        result.ai_model = _normalize_model_name(raw_model)
    else:
        logger.warning("claude -p 回傳缺少 modelUsage 欄位")

    return result


# ── 統一入口 ──────────────────────────────────────────


async def analyze_food(
    text: str | None = None,
    image_paths: list[str] | None = None,
) -> FoodAnalysis:
    """分析食物：預設走 claude -p CLI（唯一路徑，無 fallback）。

    image_paths 可帶多張（Telegram 相簿），一律合併成一次判讀、一筆記錄。

    AI_PROVIDER 路由：
    - "claude"：直接用 Claude API（無 fallback，備選）
    - "gemini"：Gemini API 優先，失敗時 fallback 到 claude -p CLI（保留）
    - 其餘（含預設 "claude-cli"）：只走 claude -p CLI，無 fallback
    """
    if AI_PROVIDER == "claude":
        return await _analyze_claude(text=text, image_paths=image_paths)

    if AI_PROVIDER == "gemini":
        # 保留：Gemini API 優先，失敗時 fallback 到 claude -p CLI
        try:
            return await _analyze_gemini(text=text, image_paths=image_paths)
        except Exception as e:
            logger.warning("Gemini 分析失敗，切換至 claude -p: %s", e)
        return await _analyze_claude_cli(text=text, image_paths=image_paths)

    # 預設 claude-cli：唯一路徑，無 fallback
    return await _analyze_claude_cli(text=text, image_paths=image_paths)
