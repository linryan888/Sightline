import subprocess

import pytest

from windows import get_duration, make_windows, save_windows


# ---------- make_windows ----------

def test_ten_second_video():
    w = make_windows(10)
    assert w == [(0, 2.5), (2.5, 5.0), (5.0, 7.5), (7.5, 10.0)]


def test_uneven_ending_is_clipped():
    w = make_windows(7)
    assert w == [(0, 2.5), (2.5, 5.0), (5.0, 7.0)]
    assert w[-1][1] <= 7


def test_zero_second_video():
    assert make_windows(0) == []


def test_five_minute_video_gives_120_windows():
    w = make_windows(300)
    assert len(w) == 120
    assert w[-1] == (297.5, 300.0)


# ---------- get_duration (needs ffmpeg installed) ----------

def test_get_duration_on_real_video(tmp_path):
    video = tmp_path / "test.mp4"
    # generate a 7-second test video with ffmpeg's built-in test pattern
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=7:size=160x120:rate=10",
         str(video)],
        check=True,
    )
    assert get_duration(video) == pytest.approx(7.0, abs=0.1)


def test_get_duration_bad_path():
    with pytest.raises(subprocess.CalledProcessError):
        get_duration("does_not_exist.mp4")


# ---------- save_windows (fake Supabase client, no network) ----------

class FakeClient:
    def __init__(self):
        self.inserted = None
        self.table_name = None

    def table(self, name):
        self.table_name = name
        return self

    def insert(self, rows):
        self.inserted = rows
        return self

    def execute(self):
        class Resp:
            data = self.inserted
        return Resp()


def test_save_windows_builds_rows():
    client = FakeClient()
    save_windows("chunk-123", [(0, 2.5), (2.5, 5.0)], client)
    assert client.table_name == "windows"
    assert client.inserted == [
        {"chunk_id": "chunk-123", "start_seconds": 0, "end_seconds": 2.5},
        {"chunk_id": "chunk-123", "start_seconds": 2.5, "end_seconds": 5.0},
    ]
