"""營養素計算工具。"""


def calc_calories(protein_g: float, carbs_g: float, fat_g: float) -> int:
    """由三大營養素克數計算總熱量 (kcal)。"""
    return round(protein_g * 4 + carbs_g * 4 + fat_g * 9)


def format_macros(protein_g: float, carbs_g: float, fat_g: float) -> list[str]:
    """格式化三大營養素行，含熱量佔比百分比。

    回傳三行字串 list，每行格式如：🍗 蛋白質 25g (18%)
    """
    total = calc_calories(protein_g, carbs_g, fat_g)

    if total == 0:
        return [
            f"🍗 蛋白質 {protein_g:.0f}g",
            f"🍚 碳水 {carbs_g:.0f}g",
            f"🧈 脂肪 {fat_g:.0f}g",
        ]

    p_pct = round(protein_g * 4 / total * 100)
    c_pct = round(carbs_g * 4 / total * 100)
    f_pct = round(fat_g * 9 / total * 100)

    return [
        f"🍗 蛋白質 {protein_g:.0f}g ({p_pct}%)",
        f"🍚 碳水 {carbs_g:.0f}g ({c_pct}%)",
        f"🧈 脂肪 {fat_g:.0f}g ({f_pct}%)",
    ]
