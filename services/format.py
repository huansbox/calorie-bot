"""訊息格式化共用工具。"""


def format_meal_groups(
    meals: list[dict],
    *,
    force_meal_types: list[str] | None = None,
    empty_placeholder: str = "（無）",
) -> list[str]:
    """格式化餐別分組清單。

    Args:
        meals: meal dict 列表，每筆需含 meal_type / description / calories。
        force_meal_types: 強制列出的餐別（即使空也顯示）。預設不強制。
        empty_placeholder: force 模式下空餐別顯示的文字。

    Returns:
        多行字串 list，第一行為空行（用於與前文分隔）。
        meals 為空且無 force 時回傳 []。
    """
    meal_order = ["早餐", "午餐", "晚餐", "其他"]
    grouped: dict[str, list] = {t: [] for t in meal_order}
    for m in meals:
        meal_type = m.get("meal_type") or "其他"
        if meal_type not in grouped:
            grouped[meal_type] = []
        grouped[meal_type].append(m)

    force_set = set(force_meal_types or [])
    lines: list[str] = []

    for mt in meal_order:
        items = grouped[mt]
        if not items and mt not in force_set:
            continue
        if not items:
            lines.append(f"【{mt}】{empty_placeholder}")
        else:
            sub_cal = sum(m["calories"] or 0 for m in items)
            lines.append(f"【{mt}】{sub_cal:,} kcal")
            for m in items:
                desc = m.get("description") or ""
                cal = m.get("calories") or 0
                lines.append(f"  {desc}　{cal:,} kcal")

    if lines:
        lines.insert(0, "")

    return lines
