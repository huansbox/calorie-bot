from scheduler import _calc_api_cost


def test_gemini_cost():
    """Gemini: input $1.25/1M, output+thinking $10/1M"""
    cost = _calc_api_cost(
        input_tokens=1_000_000,
        output_tokens=100_000,
        thinking_tokens=900_000,
        provider="gemini",
    )
    assert abs(cost - 11.25) < 1e-9


def test_claude_cost():
    """Claude: input $3/1M, output $15/1M, no thinking"""
    cost = _calc_api_cost(
        input_tokens=1_000_000,
        output_tokens=100_000,
        thinking_tokens=0,
        provider="claude",
    )
    assert abs(cost - 4.5) < 1e-9


def test_gemini_real_world():
    """實際案例：48 次分析，含 thinking tokens"""
    cost = _calc_api_cost(
        input_tokens=30_463,
        output_tokens=3_921,
        thinking_tokens=39_210,
        provider="gemini",
    )
    expected = (30_463 * 1.25 + (3_921 + 39_210) * 10) / 1_000_000
    assert abs(cost - expected) < 1e-9
