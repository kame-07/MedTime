"""ユーザーに送るテキストを一箇所にまとめる。"""

from typing import List, Tuple

from handlers.command_parser import format_time_jp

CONFIRM = "お薬を飲みましたか?\n「はい」か「いいえ」でお答えください。"

CONFIRM_AGAIN = "【再確認】お薬を飲みましたか?\n「はい」か「いいえ」でお答えください。"

YES_ACCEPTED = "確認しました。次の予定時刻までお知らせしません。おだいじに。"

NO_ACCEPTED_TEMPLATE = "わかりました。{minutes}分後にもう一度確認します。"

RETRY_LIMIT_REACHED = (
    "再確認の上限に達したため、今回の確認を終了します。\n"
    "お薬を飲んだら「はい」と送ってください。"
)

NO_PENDING = "現在、確認中のお薬はありません。\n次の予定時刻になったらお知らせします。"

HELP = (
    "【お薬リマインダーの使い方】\n"
    "\n"
    "▼ 予定時刻の管理\n"
    "・追加: 時間追加22時00\n"
    "・変更: 時間変更22時00を19時00\n"
    "・削除: 時間削除22時00\n"
    "・一覧: 時間一覧\n"
    "\n"
    "▼ まとめて指定するとき\n"
    "空白で区切ると、いくつでも一度に指定できます。\n"
    "・時間追加8時00 12時00 22時00\n"
    "・時間削除8時00 12時00\n"
    "・時間変更8時00を7時00 22時00を21時00\n"
    "\n"
    "▼ 服薬確認への返信\n"
    "予定時刻になったら確認メッセージを送ります。\n"
    "「はい」…次の予定時刻までお知らせしません。\n"
    "「いいえ」…5分後にもう一度確認します。\n"
    "5分間お返事がない場合も、もう一度確認します。\n"
    "\n"
    "使い方がわからなくなったら「ヘルプ」と送ってください。"
)

WELCOME = "友だち追加ありがとうございます!\nお薬の時間をお知らせします。\n\n" + HELP

INVALID_TIME_TEMPLATE = (
    "時刻を読み取れませんでした。\n"
    "次のように送ってください。\n"
    "例) {example}"
)

INVALID_TIME_EXAMPLES = {
    "時間追加": "時間追加22時00",
    "時間変更": "時間変更22時00を19時00",
    "時間削除": "時間削除22時00",
}

UNKNOWN = "コマンドを認識できませんでした。\n「ヘルプ」と送ると使い方を表示します。"

# 確認待ちのときに「はい」「いいえ」以外が届いた場合
PENDING_NUDGE = "お薬を飲みましたか?\n「はい」か「いいえ」でお答えください。"


def _section(title: str, lines: List[str]) -> str:
    """該当する時刻があるときだけ「【見出し】+箇条書き」を作る。"""
    if not lines:
        return ""
    body = "\n".join(f"・{line}" for line in lines)
    return f"【{title}】\n{body}\n\n"


def added(added_times: List[str], skipped_times: List[str], times: List[str]) -> str:
    return (
        _section("追加しました", [format_time_jp(t) for t in added_times])
        + _section("すでに登録されています", [format_time_jp(t) for t in skipped_times])
        + time_list(times)
    )


def deleted(deleted_times: List[str], missing_times: List[str], times: List[str]) -> str:
    return (
        _section("削除しました", [format_time_jp(t) for t in deleted_times])
        + _section("登録されていません", [format_time_jp(t) for t in missing_times])
        + time_list(times)
    )


def changed(
    changed_pairs: List[Tuple[str, str]],
    missing_times: List[str],
    duplicate_times: List[str],
    times: List[str],
) -> str:
    return (
        _section(
            "変更しました",
            [f"{format_time_jp(old)} → {format_time_jp(new)}" for old, new in changed_pairs],
        )
        + _section("登録されていません", [format_time_jp(t) for t in missing_times])
        + _section(
            "変更先がすでに登録されています", [format_time_jp(t) for t in duplicate_times]
        )
        + time_list(times)
    )


def time_list(times: List[str]) -> str:
    if not times:
        return "現在、登録されている時刻はありません。\n「時間追加22時00」のように送ると追加できます。"
    lines = "\n".join(f"・{format_time_jp(t)}" for t in times)
    return f"【現在の予定時刻】\n{lines}"
