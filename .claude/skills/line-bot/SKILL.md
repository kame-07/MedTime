---
name: line-bot
description: このリポジトリ(お薬リマインダーLINEボット)を開発・デバッグ・デプロイするための作業手順とハマりどころをまとめたプレイブック。Webhook実装、APSchedulerによる定時リマインド、Renderへの本番デプロイ、複数時刻の一括操作コマンドなどを扱う。
when_to_use: このプロジェクト(LINE Messaging APIを使った服薬リマインダーボット)のコード変更・デバッグ・本番デプロイ・新機能追加を行うときに使う。特に「確認メッセージが届かない」「スケジューラが動かない」「Renderにデプロイしたい」「複数時刻をまとめて操作したい」といった相談で参照する。
---

# LINE Bot(お薬リマインダー)プレイブック

このスキルは、本リポジトリを実際にゼロから構築・デバッグ・本番デプロイした際に得た知見をまとめたものです。プロジェクトの基本方針(技術スタック、ディレクトリ構成、コマンド)は [CLAUDE.md](../../../CLAUDE.md) に既に書かれているので、そちらも必ず参照してください。このスキルは **CLAUDE.mdに書ききれない「なぜそうなっているか」「詰まったときにどう直すか」** を補うものです。

## プロジェクトの要点

- LINE Messaging APIを使った**プッシュ通知が主目的**のボット。指定時刻に「お薬を飲みましたか?」と確認し、「はい/いいえ」または無返答に応じて再確認する。
- 予定時刻の追加・変更・削除も、LINEのメッセージ(`時間追加22時00` など)経由で行う。複数同時指定にも対応済み(後述)。
- コアロジック(`handlers/`, `services/reminder_service.py`, `services/storage.py`)はLINE SDKに一切依存しない。SDK依存は `services/line_client.py` と `app.py` のみに閉じ込めてあるため、テストは実APIを叩かずに検証できる。

## ローカル開発で踏んだ罠

### 1. line-bot-sdk の v3 API は Windows で動かないことがある

このマシンはWindowsの **Smart App Control / WDAC が強制モード** で、未署名DLL(`_pydantic_core`)の読み込みをブロックする。v3 API(`linebot.v3.*`)は `pydantic` のネイティブ拡張に依存するため **import自体が失敗する**。

→ 対策: 純Python実装である **v2 API(`linebot.*`)** を使う。`services/line_client.py` と `app.py` のimportまわりだけがSDKに依存する設計にしてあるので、将来的にv3へ移す場合もそこだけ差し替えればよい。

同様の症状(`ImportError: DLL load failed ... アプリケーション制御ポリシーによってこのファイルがブロックされました`)が出たら、まずこの制約を疑うこと。OneDrive配下かどうかは無関係(どのフォルダでも同じ)。

### 2. gunicorn は Windows にインストールはできるが実行はできない

`pip install gunicorn` 自体はWindowsでも通る(エラーにならない)。実行しようとして初めて失敗する。そのため `requirements.txt` には含めたままにし、ローカル開発では `python app.py` を使う。本番(Render = Linux)でのみ `gunicorn` が使われる。

### 3. 【最重要】gunicorn + APScheduler の fork 問題

**症状**: Renderにデプロイすると、Webhookの応答(コマンド処理・返信)は正常に動くのに、**指定時刻になっても確認メッセージが一切届かない**。ログにも `Added job` は出るが、実際に発火した形跡(`scheduled reminder fired`)がどれだけ待っても出てこない。

**原因**: `app.py` のモジュール直下で `app = create_app()` を呼び、その中で `scheduler.start()` していた。gunicornは `app:app` を解決するためにWSGIアプリを **workerプロセスがfork()される前に一度importする**。このimportのタイミングで `scheduler.start()` が実行されると、APSchedulerの裏方スレッドは **fork前の親プロセス側**で生まれてしまう。Unixのfork()は「呼び出したスレッドだけ」を子プロセスに引き継ぐため、親で生まれた裏方スレッドは子(実際にリクエストを処理するworkerプロセス)には存在しなくなる。結果、`scheduler.running == True` という記録だけが残り、実体のスレッドは動いていない状態になる。

ローカルの `python app.py`(gunicornを使わない、forkが発生しない)ではこの問題が絶対に再現しないため、**ローカルでは正常、本番でだけ確認メッセージが届かない**という形で現れる。

**診断方法**: 原因調査時は一時的に `/debug/jobs` のようなエンドポイントを追加し、`scheduler.running` と `scheduler._thread.is_alive()` を両方確認するとよい(`running=True` なのに `thread.is_alive()=False` なら、まさにこの問題)。加えて `threading.excepthook` を上書きしてスレッドの未捕捉例外を必ずログに残すようにすると、切り分けが早い。Renderの `Logs` タブでgunicorn自身のログ行(`[pid] [INFO] Booting worker with pid: N`)と自前のログ行の**時刻の前後関係**を比べると、workerがforkされる前にアプリがimportされているかどうかが分かる。

**恒久対策**(現在のコードに反映済み):
1. `create_app()` は Flask アプリと `scheduler` / `reminder` オブジェクトを作るだけで、`scheduler.start()` は呼ばない。`app.scheduler = scheduler` のように属性として公開するだけ。
2. `app.py` に `start_scheduler()` 関数を用意し、そこで初めて `scheduler.start()` と `reminder.restore_jobs()` を呼ぶ。
3. ローカル実行(`if __name__ == "__main__":`)では、`app.run()` の直前に `start_scheduler()` を呼ぶ。
4. 本番(gunicorn)では [gunicorn.conf.py](../../../gunicorn.conf.py) の **`post_fork` フック**から `start_scheduler()` を呼ぶ。`post_fork` はworkerがfork()された**直後**に、その子プロセス自身の中で実行される公式フックなので、裏方スレッドが確実に正しいプロセスで生まれる。
5. [Procfile](../../../Procfile) は `gunicorn -c gunicorn.conf.py --workers 1 --bind 0.0.0.0:$PORT app:app` とし、`gunicorn.conf.py` を明示的に読み込ませる。**Renderの管理画面で「Start Command」を手動入力していた場合はProcfileより優先されるので、そちらも同じ内容に更新する必要がある**(手動入力を促されるケースが実際にあった)。

同じパターン(gunicorn + 何らかのバックグラウンドスレッド/プロセス常駐処理)を別プロジェクトで使うときも、この `post_fork` パターンを踏襲すること。

### 4. `--workers` は必ず1にする

APSchedulerは各プロセスで独立してジョブを実行する。workerを2以上にすると、同じ確認メッセージが人数分(worker数分)重複して送られる。スケーラビリティが必要になっても、リマインダー送信の責務は1プロセスに閉じ込め、Webレスポンスだけを複数workerで捌くような設計に分離しない限り、`--workers 1` を崩さないこと。

## Renderへのデプロイ手順(概要)

詳細は [README.md の「本番デプロイ(Render)」](../../../README.md) を参照。要点だけ再掲する。

1. GitHubにpush(`.env` は `.gitignore` 済みなので秘密情報は含まれない。push前に `git status` で確認)
2. Renderで Web Service を作成(Starterプラン、$7/月)
3. 環境変数を `.env` と同じ内容で登録。`DATA_FILE` は永続ディスクのマウント先に合わせて `/var/data/schedules.json` にする
4. **永続ディスクを追加する(Mount Path: `/var/data`, Size: 1GB)**。これを忘れると再デプロイのたびに登録済み時刻が消える
5. Start Commandは `gunicorn -c gunicorn.conf.py --workers 1 --bind 0.0.0.0:$PORT app:app`
6. デプロイ後のURL + `/callback` をLINE Developers ConsoleのWebhook URLに設定し、「検証」で成功を確認

費用目安: Starter $7/月 + ディスク $0.25/GB/月 ≒ 月1,000円強(2026年時点の実測値)。

## 複数時刻の一括操作

`handlers/command_parser.py` の `Command` は `time`/`new_time` 単数フィールドではなく、`times: List[str]` と `changes: List[Tuple[str, str]]` を持つ設計になっている(複数対応のため)。

- 区切り文字は空白・改行・`,`・`、`・`と`のいずれも許容(`_SEPARATOR_RE`)
- **指定の中に1つでも解釈できない時刻が混ざっていたら、全体を`INVALID_TIME`として拒否する**(`_match_all` がテキスト全体をパターンの繰り返し+区切り文字だけで構成されているか検証する)。一部だけ中途半端に反映される状態を避けるための意図的な設計。
- 返信メッセージ(`messages.py`)は「追加しました」「すでに登録されています」のように結果の種類ごとにセクション分けして表示する(`_section` ヘルパー)。

新しいコマンドを追加する際も、この「複数指定は全部成功するかレビューしてから実行、失敗が1つでもあれば全体を拒否」という方針を踏襲すると一貫性が保てる。

## テストの書き方

- `tests/fakes.py` に `FakeScheduler`(ジョブを実行せず保持し、`fire()`/`fire_once()` で明示的に発火させる)と `FakeLineClient`(送信内容を記録するだけ)がある。これらを使えば実際のAPScheduler・LINE APIなしで、確認→はい/いいえ→再確認のフロー全体を検証できる。
- `services/reminder_service.py` や `handlers/message_handler.py` のテストは、この2つのフェイクと `Storage`(`tmp_path` で一時ファイルを使う)を組み合わせて `tests/test_reminder_flow.py` のように書く。
- `app.py` を経由する統合的な動作確認(Flask test_client、実際のAPScheduler、実gunicorn相当の挙動)は、コミットするテストスイートには含めていない。スクラッチパッドに使い捨てスクリプトを書いて確認し、確認が終わったら消す運用にしている。

## コマンド早見表

```powershell
# 依存関係インストール
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# テスト
.\.venv\Scripts\python.exe -m pytest -q

# ローカル起動
.\.venv\Scripts\python.exe app.py
# または start.bat をダブルクリック(Shift-JISで保存されているため要注意。
# cmd.exeは日本語WindowsではバッチファイルをShift-JISとして読むので、
# UTF-8のまま保存すると文字化けして実行できない)

# 本番へ反映
git add -A
git commit -m "..."
git push origin main   # Render側でAuto Deployが有効なら自動的に再デプロイされる
```
