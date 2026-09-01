# LINE チャットボット開発

## プロジェクト概要
LINE Messaging API を使った通知・リマインダー配信ボット。ユーザーからのメッセージに応じた会話応答ではなく、こちらからプッシュメッセージで通知を送ることが主用途。

## 技術スタック
- 言語: Python
- フレームワーク: **Flask**(決定済み)
- LINE連携: `line-bot-sdk`(公式Python SDK)の **v2 API(`linebot.*`)**
  - v3 API(`linebot.v3.*`)は `pydantic` のネイティブ拡張に依存する。開発機では Windows の
    Smart App Control / WDAC が強制モードのため未署名DLL(`_pydantic_core`)がブロックされ、
    import 自体に失敗する。v2 API は純Python実装なので環境を選ばない。
  - 移行が必要になった場合、差し替えるのは `services/line_client.py` と `app.py` の import まわりだけ。
- スケジューラ: `APScheduler`(`BackgroundScheduler`)
- 本番WSGIサーバー: `gunicorn`(Windowsでは動作しないため、ローカル開発では `python app.py` を使う。
  `pip install` 自体はWindowsでも通るので `requirements.txt` に含めている)
- ホスティング: **Render**(Starterプラン, $7/月 + 永続ディスク $0.25/GB/月)に決定。
  手順は README.md の「本番デプロイ(Render)」を参照。
  `gunicorn` は必ず `--workers 1` で起動すること(複数worker化するとAPSchedulerのジョブが
  worker数だけ重複起動し、確認メッセージが二重に送られる)。

## ディレクトリ構成
- `app.py`: エントリーポイント(Flask Webhookサーバー + スケジューラ起動)
- `config.py`: 環境変数の読み込み
- `messages.py`: ユーザーに送る文面
- `handlers/command_parser.py`: 受信テキスト→コマンドの解析(SDK非依存)
- `handlers/message_handler.py`: コマンドの振り分けと返信文の決定(SDK非依存)
- `services/reminder_service.py`: 確認・再確認のスケジューリング(SDK非依存)
- `services/storage.py`: 予定時刻と確認待ち状態のJSON永続化
- `services/line_client.py`: LINE Messaging API 送信ラッパー(**SDK依存はここだけ**)
- `.env`: シークレット類(**必ず.gitignoreに追加し、コミットしない**)
- `data/schedules.json`: 実行時データ(gitignore対象)
- `tests/`: テストコード

## 重要な設計方針
- **プッシュ通知が主目的**なので、Webhook受信(ユーザー発言への応答)よりも、LINE Messaging APIの `push message` / `multicast` / スケジュール配信の実装を優先する。
- リマインダーのスケジューリングには、当面は `APScheduler` などの軽量ライブラリを想定。将来的に外部Cronやクラウドのスケジューラに置き換える可能性がある。
- Webhookエンドポイントを実装する場合は、LINEからのリクエストであることを **署名検証(X-Line-Signature)** で必ず確認すること。

## シークレット管理
- `CHANNEL_ACCESS_TOKEN` と `CHANNEL_SECRET` は環境変数(`.env`)で管理し、コードに直書きしない。
- サンプル用に `.env.example` を用意し、実際の値が入った `.env` はコミットしない。

## コマンド
- 仮想環境の作成: `python -m venv .venv`
- 依存関係インストール: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- ローカル起動: `.\.venv\Scripts\python.exe app.py`(既定で `http://localhost:5000`)
- 外部公開(別ターミナル): `ngrok http 5000` → 発行URL + `/callback` をWebhook URLに設定
- テスト実行: `.\.venv\Scripts\python.exe -m pytest -q`

## 実装済みの仕様(お薬リマインダー)
- 予定時刻(ユーザーごと、`HH:MM`)ごとにcronジョブを立て、確認メッセージをプッシュする。
- 返信「はい」→ 確認待ちを解除し、次の予定時刻まで何もしない。
- 返信「いいえ」→ `RETRY_INTERVAL_MINUTES`(既定5分)後に再確認。
- 無返答のまま既定5分経過 →「いいえ」と同じ扱い。既定(`TIMEOUT_BEHAVIOR=immediate`)では
  その時点で即再送し、`delayed` にするとさらに5分待ってから再送する。
- 時刻管理コマンド: `時間追加22時00` / `時間変更22時00を19時00` / `時間削除22時00` / `時間一覧` / `ヘルプ`
  - `22時00` `22時00分` `22:00` `22時` および全角数字を受け付ける(NFKC正規化)。
  - 追加・変更・削除は複数同時指定に対応(`時間追加8時00 12時00 22時00`)。
    区切りは空白・改行・`,`・`、`・`と`。結果は種類ごと(追加済み/登録済み等)に分けて返す。
  - 複数指定のうち1つでも解釈できない場合は、**一部も実行せず**に `INVALID_TIME` を返す。
    中途半端に登録された状態を作らないための方針。
- 追いかけ確認のジョブIDは `followup:{userId}` に固定し、上書きすることで
  「ユーザーごとに未処理の再確認は常に1件だけ」を保証している。

## 注意事項
- LINEの公式アカウント設定(Webhook URL、応答モードなど)はLINE Developers ConsoleおよびLINE Official Account Managerで行う。認証情報やコンソールの設定変更はコード変更とは別に、ユーザー自身が行うか、事前に明示された場合のみ支援する。
