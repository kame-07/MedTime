"""gunicornの設定。

workerプロセスがfork()された直後にAPSchedulerを起動する(post_fork)。
importのタイミングで起動すると、fork前に作られた裏方スレッドが
fork後のworkerプロセスに引き継がれず、確認メッセージが永久に発火しなくなる
問題があったため、明示的にこのタイミングで起動している。
"""


def post_fork(server, worker):
    from app import start_scheduler

    start_scheduler()
