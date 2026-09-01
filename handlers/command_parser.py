"""ユーザーから届いたテキストを、ボットが解釈できるコマンドに変換する。

対応する書式:
    時間追加22時00                     予定時刻の追加
    時間追加8時00 12時00 22時00        まとめて追加
    時間変更22時00を19時00              予定時刻の変更
    時間変更8時00を7時00 22時00を21時00 まとめて変更
    時間削除22時00                     予定時刻の削除
    時間削除8時00 12時00               まとめて削除
    時間一覧                           登録済みの予定時刻を表示
    はい / いいえ                      服薬確認への返信

時刻は「22時00」「22時00分」「22:00」「22時」のいずれの書き方でも受け付ける。
複数指定するときの区切りは、空白・改行・「,」「、」「と」のいずれでもよい。
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# コマンドの種類
ADD = "add"
CHANGE = "change"
DELETE = "delete"
LIST = "list"
YES = "yes"
NO = "no"
HELP = "help"
INVALID_TIME = "invalid_time"
UNKNOWN = "unknown"


@dataclass
class Command:
    kind: str
    # ADD / DELETE で指定された時刻(重複は除去済み、指定順)
    times: List[str] = field(default_factory=list)
    # CHANGE で指定された (変更前, 変更後) の組(指定順)
    changes: List[Tuple[str, str]] = field(default_factory=list)
    keyword: Optional[str] = None


# 「22時00」「22時00分」「22時」「22:00」を拾うためのゆるい塊。
# 妥当性(0〜23時 / 0〜59分)は _to_hhmm で検証する。
_TIME_CHUNK = r"\d{1,2}\s*(?:時|:)\s*\d{0,2}\s*分?"

_TIME_CHUNK_RE = re.compile(_TIME_CHUNK)
_CHANGE_PAIR_RE = re.compile(rf"({_TIME_CHUNK})\s*を\s*({_TIME_CHUNK})")

# 複数指定するときの区切り。ここに挙げた文字だけなら「余分な文字はない」とみなす。
_SEPARATOR_RE = re.compile(r"[\s,、と]*")

_TIME_PARTS_RE = re.compile(r"^(\d{1,2})\s*(?:時|:)\s*(\d{0,2})\s*分?$")

ADD_KEYWORD = "時間追加"
CHANGE_KEYWORD = "時間変更"
DELETE_KEYWORD = "時間削除"

_YES_WORDS = {"はい", "ハイ", "yes", "y", "飲んだ", "のんだ", "のみました", "飲みました"}
_NO_WORDS = {"いいえ", "イイエ", "no", "n", "まだ", "飲んでない", "のんでない"}
_LIST_WORDS = {"時間一覧", "時間確認", "一覧", "時間リスト"}
_HELP_WORDS = {"ヘルプ", "help", "使い方", "?"}


def normalize(text: str) -> str:
    """全角英数字・全角スペース・全角コロンを半角に揃え、末尾の句読点を落とす。"""
    normalized = unicodedata.normalize("NFKC", text or "")
    return normalized.strip().strip("。．！!、,.　 ")


def _to_hhmm(chunk: str) -> Optional[str]:
    """「22時00」のような文字列を "22:00" に変換する。不正なら None。"""
    match = _TIME_PARTS_RE.match(chunk.strip())
    if not match:
        return None
    hour = int(match.group(1))
    minute_text = match.group(2)
    minute = int(minute_text) if minute_text else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def _match_all(pattern: re.Pattern, text: str) -> Optional[List[re.Match]]:
    """text が「pattern の繰り返し + 区切り文字」だけで構成されているか検証する。

    余分な文字が混ざっていたり、1件も見つからない場合は None を返す。
    「時間追加8時00 あさ」のような中途半端な指定を弾くための検証。
    """
    matches = list(pattern.finditer(text))
    if not matches:
        return None

    position = 0
    for match in matches:
        if not _SEPARATOR_RE.fullmatch(text[position : match.start()]):
            return None
        position = match.end()
    if not _SEPARATOR_RE.fullmatch(text[position:]):
        return None
    return matches


def _parse_times(text: str) -> Optional[List[str]]:
    """「8時00 12時00」のような並びを ["08:00", "12:00"] にする。"""
    matches = _match_all(_TIME_CHUNK_RE, text)
    if matches is None:
        return None

    times: List[str] = []
    for match in matches:
        hhmm = _to_hhmm(match.group(0))
        if hhmm is None:
            return None
        if hhmm not in times:  # 同じ時刻を2回書かれても1件として扱う
            times.append(hhmm)
    return times


def _parse_changes(text: str) -> Optional[List[Tuple[str, str]]]:
    """「8時00を7時00 22時00を21時00」のような並びを組のリストにする。"""
    matches = _match_all(_CHANGE_PAIR_RE, text)
    if matches is None:
        return None

    changes: List[Tuple[str, str]] = []
    for match in matches:
        old = _to_hhmm(match.group(1))
        new = _to_hhmm(match.group(2))
        if old is None or new is None:
            return None
        changes.append((old, new))
    return changes


def parse(text: str) -> Command:
    normalized = normalize(text)
    lowered = normalized.lower()

    if lowered in _YES_WORDS:
        return Command(kind=YES)
    if lowered in _NO_WORDS:
        return Command(kind=NO)
    if normalized in _LIST_WORDS:
        return Command(kind=LIST)
    if lowered in _HELP_WORDS:
        return Command(kind=HELP)

    if normalized.startswith(CHANGE_KEYWORD):
        changes = _parse_changes(normalized[len(CHANGE_KEYWORD) :])
        if changes:
            return Command(kind=CHANGE, changes=changes)
        return Command(kind=INVALID_TIME, keyword=CHANGE_KEYWORD)

    if normalized.startswith(ADD_KEYWORD):
        times = _parse_times(normalized[len(ADD_KEYWORD) :])
        if times:
            return Command(kind=ADD, times=times)
        return Command(kind=INVALID_TIME, keyword=ADD_KEYWORD)

    if normalized.startswith(DELETE_KEYWORD):
        times = _parse_times(normalized[len(DELETE_KEYWORD) :])
        if times:
            return Command(kind=DELETE, times=times)
        return Command(kind=INVALID_TIME, keyword=DELETE_KEYWORD)

    return Command(kind=UNKNOWN)


def format_time_jp(hhmm: str) -> str:
    """"22:00" を「22時00分」に整形する(ユーザーへの表示用)。"""
    hour, minute = hhmm.split(":")
    return f"{int(hour)}時{minute}分"
