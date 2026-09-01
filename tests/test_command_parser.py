import pytest

from handlers import command_parser as cp


@pytest.mark.parametrize(
    "text,expected",
    [
        ("時間追加22時00", "22:00"),
        ("時間追加 22時00分", "22:00"),
        ("時間追加22:00", "22:00"),
        ("時間追加8時5", "08:05"),
        ("時間追加22時", "22:00"),
        # 全角で送られてきても NFKC 正規化で吸収する
        ("時間追加２２時００", "22:00"),
        ("時間追加0時00", "00:00"),
        ("時間追加23時59", "23:59"),
    ],
)
def test_add(text, expected):
    command = cp.parse(text)
    assert command.kind == cp.ADD
    assert command.times == [expected]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("時間追加8時00 12時00 22時00", ["08:00", "12:00", "22:00"]),
        ("時間追加8時00、12時00", ["08:00", "12:00"]),
        ("時間追加8時00,12時00", ["08:00", "12:00"]),
        ("時間追加8時00と12時00", ["08:00", "12:00"]),
        ("時間追加8:00 12:00", ["08:00", "12:00"]),
        ("時間追加８時００　１２時００", ["08:00", "12:00"]),
        # 同じ時刻を重ねて書かれても1件にまとめる
        ("時間追加8時00 8時00", ["08:00"]),
    ],
)
def test_add_multiple(text, expected):
    command = cp.parse(text)
    assert command.kind == cp.ADD
    assert command.times == expected


def test_add_multiline():
    command = cp.parse("時間追加\n8時00\n12時00")
    assert command.kind == cp.ADD
    assert command.times == ["08:00", "12:00"]


@pytest.mark.parametrize(
    "text,old,new",
    [
        ("時間変更22時00を19時00", "22:00", "19:00"),
        ("時間変更 22:00 を 19:30", "22:00", "19:30"),
        ("時間変更２２時００を１９時００", "22:00", "19:00"),
    ],
)
def test_change(text, old, new):
    command = cp.parse(text)
    assert command.kind == cp.CHANGE
    assert command.changes == [(old, new)]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("時間変更8時00を7時00 22時00を21時00", [("08:00", "07:00"), ("22:00", "21:00")]),
        ("時間変更8時00を7時00、22時00を21時00", [("08:00", "07:00"), ("22:00", "21:00")]),
        ("時間変更8時00を7時00と22時00を21時00", [("08:00", "07:00"), ("22:00", "21:00")]),
    ],
)
def test_change_multiple(text, expected):
    command = cp.parse(text)
    assert command.kind == cp.CHANGE
    assert command.changes == expected


def test_delete():
    command = cp.parse("時間削除22時00")
    assert command.kind == cp.DELETE
    assert command.times == ["22:00"]


def test_delete_multiple():
    command = cp.parse("時間削除8時00 12時00 22時00")
    assert command.kind == cp.DELETE
    assert command.times == ["08:00", "12:00", "22:00"]


@pytest.mark.parametrize(
    "text",
    [
        "時間削除全部",
        "時間削除 全部",
        "時間削除すべて",
        "時間削除全て",
        "時間削除ぜんぶ",
        "時間削除全件",
        "時間削除全部削除",
    ],
)
def test_delete_all(text):
    command = cp.parse(text)
    assert command.kind == cp.DELETE_ALL
    assert command.times == []


@pytest.mark.parametrize("text", ["はい", "ハイ", "はい。", " はい ", "Yes"])
def test_yes(text):
    assert cp.parse(text).kind == cp.YES


@pytest.mark.parametrize("text", ["いいえ", "イイエ", "いいえ!", "no"])
def test_no(text):
    assert cp.parse(text).kind == cp.NO


def test_list_and_help():
    assert cp.parse("時間一覧").kind == cp.LIST
    assert cp.parse("ヘルプ").kind == cp.HELP


@pytest.mark.parametrize(
    "text,keyword",
    [
        ("時間追加25時00", "時間追加"),  # 時が範囲外
        ("時間追加22時70", "時間追加"),  # 分が範囲外
        ("時間追加あさ", "時間追加"),
        ("時間変更22時00", "時間変更"),  # 変更先がない
        ("時間削除", "時間削除"),
        # 複数指定のうち1つでも読み取れなければ、全体をやり直してもらう
        ("時間追加8時00 あさ", "時間追加"),
        ("時間追加8時00 25時00", "時間追加"),
        ("時間削除8時00 12時99", "時間削除"),
        ("時間変更8時00を7時00 22時00", "時間変更"),
    ],
)
def test_invalid_time(text, keyword):
    command = cp.parse(text)
    assert command.kind == cp.INVALID_TIME
    assert command.keyword == keyword


@pytest.mark.parametrize("text", ["こんにちは", "", "薬"])
def test_unknown(text):
    assert cp.parse(text).kind == cp.UNKNOWN


def test_format_time_jp():
    assert cp.format_time_jp("22:00") == "22時00分"
    assert cp.format_time_jp("08:05") == "8時05分"
