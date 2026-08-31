import pytest

from services.storage import Storage

USER = "U_test"


@pytest.fixture
def storage(tmp_path):
    return Storage(str(tmp_path / "data" / "schedules.json"))


def test_add_and_list(storage):
    assert storage.add_time(USER, "22:00") is True
    assert storage.add_time(USER, "08:00") is True
    # 常に時刻順に並ぶ
    assert storage.get_times(USER) == ["08:00", "22:00"]


def test_add_duplicate(storage):
    storage.add_time(USER, "22:00")
    assert storage.add_time(USER, "22:00") is False
    assert storage.get_times(USER) == ["22:00"]


def test_remove(storage):
    storage.add_time(USER, "22:00")
    assert storage.remove_time(USER, "22:00") is True
    assert storage.remove_time(USER, "22:00") is False
    assert storage.get_times(USER) == []


def test_change(storage):
    storage.add_time(USER, "22:00")
    assert storage.change_time(USER, "22:00", "19:00") == "ok"
    assert storage.get_times(USER) == ["19:00"]


def test_change_not_found(storage):
    assert storage.change_time(USER, "22:00", "19:00") == "not_found"


def test_change_duplicate(storage):
    storage.add_time(USER, "22:00")
    storage.add_time(USER, "19:00")
    assert storage.change_time(USER, "22:00", "19:00") == "duplicate"
    assert storage.get_times(USER) == ["19:00", "22:00"]


def test_pending_roundtrip(storage):
    assert storage.get_pending(USER) is None
    storage.set_pending(USER, "22:00", 1)
    assert storage.get_pending(USER) == {"time": "22:00", "sent_count": 1}
    storage.clear_pending(USER)
    assert storage.get_pending(USER) is None


def test_persisted_across_instances(tmp_path):
    path = str(tmp_path / "data" / "schedules.json")
    first = Storage(path)
    first.add_time(USER, "22:00")

    second = Storage(path)
    assert second.get_times(USER) == ["22:00"]
    assert USER in second.user_ids()


def test_broken_file_does_not_crash(tmp_path):
    path = tmp_path / "schedules.json"
    path.write_text("{ broken", encoding="utf-8")
    storage = Storage(str(path))
    assert storage.get_times(USER) == []
