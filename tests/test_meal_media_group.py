"""相簿（media group）聚合測試：同一次傳的多張照片必須合併成一次判讀、一筆記錄。

源起：2026-07-30 傳 3 張同餐照片 + 說明，跑成 3 次評估、3 筆記錄，說明涵蓋的菜色
被重複計算。Telegram 把相簿拆成 N 個獨立 message（只有第一個帶 caption），靠
media_group_id 串起來。
"""
import asyncio
from types import SimpleNamespace

import pytest


class _FakeMessage:
    def __init__(self, caption=None, media_group_id=None, uid="p"):
        self.caption = caption
        self.media_group_id = media_group_id
        self.photo = [SimpleNamespace(file_unique_id=uid)]
        self.replies: list[str] = []

    async def reply_text(self, text):
        self.replies.append(text)
        return SimpleNamespace(message_id=len(self.replies))


def _update(caption=None, media_group_id=None, uid="p"):
    return SimpleNamespace(message=_FakeMessage(caption, media_group_id, uid))


def _context():
    return SimpleNamespace(chat_data={}, user_data={})


@pytest.fixture
def meal(monkeypatch):
    """把下載與後段處理換成 stub，只驗聚合行為。"""
    import handlers.meal as m

    monkeypatch.setattr(m, "MEDIA_GROUP_WAIT", 0.01)

    counter = {"n": 0}

    async def fake_download(update):
        counter["n"] += 1
        return f"/tmp/photo{counter['n']}.jpg"

    monkeypatch.setattr(m, "_download_photo", fake_download)

    calls: list[dict] = []

    async def fake_process(update, context, text=None, image_paths=None, processing_msg=None):
        calls.append({
            "text": text,
            "image_paths": image_paths,
            "processing_msg": processing_msg,
        })

    monkeypatch.setattr(m, "_process_food", fake_process)
    return m, calls


def test_album_merges_into_single_analysis(meal):
    """三張同組照片 → 只判讀一次，三個路徑一起送，caption 沿用第一張的。"""
    m, calls = meal

    async def scenario():
        ctx = _context()
        first = _update(caption="大埔鐵板燒：豆腐、高麗菜、牛肉、白飯4小碗", media_group_id="g1")
        await m.handle_photo(first, ctx)
        await m.handle_photo(_update(media_group_id="g1"), ctx)
        await m.handle_photo(_update(media_group_id="g1"), ctx)
        await asyncio.sleep(0.2)  # 等收集任務判定到齊
        return ctx, first

    ctx, first = asyncio.run(scenario())

    assert len(calls) == 1
    assert calls[0]["image_paths"] == [
        "/tmp/photo1.jpg", "/tmp/photo2.jpg", "/tmp/photo3.jpg",
    ]
    assert calls[0]["text"] == "大埔鐵板燒：豆腐、高麗菜、牛肉、白飯4小碗"
    # 「分析中」只回一次（第一張時），且該訊息被交給後段編輯
    assert first.message.replies == ["分析中..."]
    assert calls[0]["processing_msg"] is not None
    assert ctx.chat_data["media_groups"] == {}


def test_single_photo_unchanged(meal):
    """非相簿的單張照片：立即處理，行為與過去相同。"""
    m, calls = meal

    async def scenario():
        await m.handle_photo(_update(caption="滷肉飯"), _context())

    asyncio.run(scenario())

    assert len(calls) == 1
    assert calls[0]["image_paths"] == ["/tmp/photo1.jpg"]
    assert calls[0]["text"] == "滷肉飯"
    assert calls[0]["processing_msg"] is None  # 由 _process_food 自己回「分析中」


def test_caption_on_later_photo_still_used(meal):
    """caption 不在第一張時也要撿到（Telegram 慣例放第一張，但不倚賴）。"""
    m, calls = meal

    async def scenario():
        ctx = _context()
        await m.handle_photo(_update(media_group_id="g2"), ctx)
        await m.handle_photo(_update(caption="晚餐兩人份", media_group_id="g2"), ctx)
        await asyncio.sleep(0.2)

    asyncio.run(scenario())

    assert len(calls) == 1
    assert calls[0]["text"] == "晚餐兩人份"


def test_two_albums_are_independent(meal):
    """不同 media_group_id 各自成一筆，不會互相混入。"""
    m, calls = meal

    async def scenario():
        ctx = _context()
        await m.handle_photo(_update(caption="A 餐", media_group_id="gA"), ctx)
        await m.handle_photo(_update(caption="B 餐", media_group_id="gB"), ctx)
        await m.handle_photo(_update(media_group_id="gA"), ctx)
        await asyncio.sleep(0.2)

    asyncio.run(scenario())

    assert len(calls) == 2
    by_text = {c["text"]: c["image_paths"] for c in calls}
    assert by_text["A 餐"] == ["/tmp/photo1.jpg", "/tmp/photo3.jpg"]
    assert by_text["B 餐"] == ["/tmp/photo2.jpg"]
