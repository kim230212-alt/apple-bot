"""
프로세스 간 입력 직렬화 — Win32 Named Mutex
두 봇 인스턴스가 동시에 SetForegroundWindow + Interception 입력을 보낼 때 충돌 방지.
단독 실행 시 오버헤드 없음 (단순 mutex 획득/해제, 수 마이크로초).
"""
from contextlib import contextmanager
import ctypes

_MUTEX_NAME = "Global\\EntBotInputLock"
_kernel32 = ctypes.windll.kernel32
_h = None


def _handle():
    global _h
    if _h is None:
        _h = _kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    return _h


@contextmanager
def input_lock(timeout_ms=5000):
    """with input_lock(): 블록 동안 다른 프로세스의 입력 차단"""
    h = _handle()
    _kernel32.WaitForSingleObject(h, timeout_ms)
    try:
        yield
    finally:
        _kernel32.ReleaseMutex(h)
