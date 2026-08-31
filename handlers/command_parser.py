"""ユーザーから届いたテキストを、ボットが解釈できるコマンドに変換する。

対応する書式:
    時間追加22時00            予定時刻の追加
    時間変更22時00を19時00     予定時刻の変更
    時間削除22時00            予定時刻の削除
    時間一覧                  登録済みの予定時刻を表示
    はい / いいえ              服薬確認への返信

時刻は「22時00」「22時00分」「22:00」「22時」のいずれの書き方でも受け付ける。
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

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
    time: Optional[str] = None
    new_time: Optional[str] = None
    keyword: Optional[str] = None


# 「22時00」「22時00分」「22時」「22:00」を拾うためのゆるい塊。
# 妥当性(0〜23時 / 0〜59分)は _to_hhmm で検証する。
_TIME_CHUNK = r"\d{1,2}\s*(?:時|:)\s*\d{0,2}\s*分?"

_ADD_RE = re.compile(rf"^時間追加\s*({_TIME_CHUNK})$")
_CHANGE_RE = re.compile(rf"^時間変更\s*({_TIME_CHUNK})\s*を\s*({_TIME_CHUNK})$")
_DELETE_RE = re.compile(rf"^時間削除\s*({_TIME_CHUNK})$")

# 時刻部分が読み取れなかったときに、どのコマンドを打とうとしたのか判別する
_KEYWORD_RE = re.compile(r"^(時間追加|時間変更|時間削除)")

_TIME_PARTS_RE = re.compile(r"^(\d{1,2})\s*(?:時|:)\s*(\d{0,2})\s*分?$")

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

    match = _CHANGE_RE.match(normalized)
    if match:
        old = _to_hhmm(match.group(1))
        new = _to_hhmm(match.group(2))
        if old and new:
            return Command(kind=CHANGE, time=old, new_time=new)
        return Command(kind=INVALID_TIME, keyword="時間変更")

    match = _ADD_RE.match(normalized)
    if match:
        hhmm = _to_hhmm(match.group(1))
        if hhmm:
            return Command(kind=ADD, time=hhmm)
        return Command(kind=INVALID_TIME, keyword="時間追加")

    match = _DELETE_RE.match(normalized)
    if match:
        hhmm = _to_hhmm(match.group(1))
        if hhmm:
            return Command(kind=DELETE, time=hhmm)
        return Command(kind=INVALID_TIME, keyword="時間削除")

    # キーワードだけ一致した(書式が崩れている)場合は、専用の案内を返せるようにする
    keyword_match = _KEYWORD_RE.match(normalized)
    if keyword_match:
        return Command(kind=INVALID_TIME, keyword=keyword_match.group(1))

    return Command(kind=UNKNOWN)


def format_time_jp(hhmm: str) -> str:
    """"22:00" を「22時00分」に整形する(ユーザーへの表示用)。"""
    hour, minute = hhmm.split(":")
    return f"{int(hour)}時{minute}分"
