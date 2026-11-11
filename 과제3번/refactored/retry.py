import functools
import time

from base_page import UiTimeoutError
from session import restart_app


def retry(retries=1, delay=2):
    """환경 불안정(UiTimeoutError)만 재시도한다. 총 실행 횟수 = retries + 1.

    - AssertionError(결제 실패·값 불일치)는 제품 결함일 수 있으므로 재시도하지 않고 즉시 중단한다.
    - device.payment_started 가 True(결제 버튼 이후)면 중복 주문 방지를 위해 재시도하지 않는다.
    - 재시도 전에는 앱을 재시작해 시작 화면에서 다시 시작한다.
    - 마지막 시도까지 실패하면 마지막 예외를 그대로 레이즈한다.
    """
    def decorator(test_func):
        @functools.wraps(test_func)
        def wrapper(device, *args, **kwargs):
            for attempt in range(retries + 1):
                device.payment_started = False
                try:
                    return test_func(device, *args, **kwargs)
                except UiTimeoutError as e:
                    if device.payment_started:
                        print(f"결제 이후 실패 → 중복 주문 방지를 위해 재시도하지 않음: {e}", flush=True)
                        raise
                    if attempt >= retries:
                        raise
                    print(f"[재시도 {attempt + 1}/{retries}] {e}", flush=True)
                    restart_app(device)
                    time.sleep(delay)
        return wrapper
    return decorator
