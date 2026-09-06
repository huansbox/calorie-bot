import os
import time

from scheduler import ORPHAN_MEDIA_MAX_AGE_HOURS, sweep_orphan_media


def _make_file(directory, name: str, age_hours: float) -> str:
    path = os.path.join(str(directory), name)
    with open(path, "wb") as f:
        f.write(b"x")
    mtime = time.time() - age_hours * 3600
    os.utime(path, (mtime, mtime))
    return path


class TestSweepOrphanMedia:
    def test_removes_file_older_than_threshold(self, tmp_path):
        path = _make_file(tmp_path, "old.jpg", age_hours=72)
        assert sweep_orphan_media(tmp_path) == 1
        assert not os.path.exists(path)

    def test_keeps_recent_file(self, tmp_path):
        """DB 引用中的照片最長活 24h，不能被兜底掃掉。"""
        path = _make_file(tmp_path, "fresh.jpg", age_hours=12)
        assert sweep_orphan_media(tmp_path) == 0
        assert os.path.exists(path)

    def test_boundary_just_inside_threshold(self, tmp_path):
        """略新於門檻不刪。用 3 分鐘邊際避開「設 mtime 到實際比對」之間的耗時。"""
        path = _make_file(
            tmp_path, "edge.jpg", age_hours=ORPHAN_MEDIA_MAX_AGE_HOURS - 0.05
        )
        assert sweep_orphan_media(tmp_path) == 0
        assert os.path.exists(path)

    def test_boundary_just_past_threshold(self, tmp_path):
        path = _make_file(
            tmp_path, "edge.jpg", age_hours=ORPHAN_MEDIA_MAX_AGE_HOURS + 0.05
        )
        assert sweep_orphan_media(tmp_path) == 1
        assert not os.path.exists(path)

    def test_mixed_directory(self, tmp_path):
        old_a = _make_file(tmp_path, "a.jpg", age_hours=100)
        old_b = _make_file(tmp_path, "b.jpg", age_hours=49)
        fresh = _make_file(tmp_path, "c.jpg", age_hours=1)
        assert sweep_orphan_media(tmp_path) == 2
        assert not os.path.exists(old_a)
        assert not os.path.exists(old_b)
        assert os.path.exists(fresh)

    def test_custom_max_age(self, tmp_path):
        path = _make_file(tmp_path, "old.jpg", age_hours=3)
        assert sweep_orphan_media(tmp_path, max_age_hours=2) == 1
        assert not os.path.exists(path)

    def test_keeps_gitkeep(self, tmp_path):
        """data/media/.gitkeep 是版控佔位檔，永遠是最舊的，不能被掃掉。"""
        path = _make_file(tmp_path, ".gitkeep", age_hours=5000)
        assert sweep_orphan_media(tmp_path) == 0
        assert os.path.exists(path)

    def test_keeps_dotfiles_but_sweeps_the_rest(self, tmp_path):
        keep = _make_file(tmp_path, ".gitkeep", age_hours=5000)
        gone = _make_file(tmp_path, "old.jpg", age_hours=100)
        assert sweep_orphan_media(tmp_path) == 1
        assert os.path.exists(keep)
        assert not os.path.exists(gone)

    def test_missing_directory_is_noop(self, tmp_path):
        assert sweep_orphan_media(os.path.join(str(tmp_path), "nope")) == 0

    def test_empty_directory(self, tmp_path):
        assert sweep_orphan_media(tmp_path) == 0

    def test_subdirectory_is_left_alone(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        old_mtime = time.time() - 100 * 3600
        os.utime(str(sub), (old_mtime, old_mtime))
        assert sweep_orphan_media(tmp_path) == 0
        assert sub.is_dir()

    def test_unremovable_file_does_not_abort_sweep(self, tmp_path, monkeypatch):
        """單一檔案刪除失敗不能中斷整輪掃描。"""
        _make_file(tmp_path, "a.jpg", age_hours=100)
        _make_file(tmp_path, "b.jpg", age_hours=100)
        real_remove = os.remove
        calls = []

        def flaky_remove(path):
            calls.append(path)
            if len(calls) == 1:
                raise OSError("permission denied")
            real_remove(path)

        monkeypatch.setattr(os, "remove", flaky_remove)
        assert sweep_orphan_media(tmp_path) == 1
        assert len(calls) == 2
