import signal
from contextlib import contextmanager


class TimeoutError(Exception):
    pass


@contextmanager
def timeout(seconds: int):
    def _handler(signum, frame):
        raise TimeoutError(f"Request timed out after {seconds}s")

    signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
