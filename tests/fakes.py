"""テスト用のスケジューラ / LINE クライアントの代替。"""


class FakeJob:
    def __init__(self, scheduler, job_id, func, args):
        self.id = job_id
        self.func = func
        self.args = args
        self._scheduler = scheduler

    def remove(self):
        self._scheduler.jobs.pop(self.id, None)


class FakeScheduler:
    """ジョブを実行せずに保持し、テストから任意のタイミングで発火させる。"""

    def __init__(self):
        self.jobs = {}

    def add_job(self, func, trigger=None, args=None, id=None, **kwargs):
        job = FakeJob(self, id, func, list(args or []))
        self.jobs[id] = job
        return job

    def get_jobs(self):
        return list(self.jobs.values())

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def fire(self, job_id):
        """cron ジョブの発火。実行後もジョブは残る。"""
        job = self.jobs[job_id]
        job.func(*job.args)

    def fire_once(self, job_id):
        """date ジョブの発火。実際の APScheduler と同じく実行時に取り除かれる。"""
        job = self.jobs.pop(job_id)
        job.func(*job.args)


class FakeLineClient:
    def __init__(self):
        self.pushed = []  # (user_id, text) のリスト

    def push_text(self, user_id, text, quick_reply_labels=None):
        self.pushed.append((user_id, text))

    def reply_text(self, reply_token, text, quick_reply_labels=None):
        pass
