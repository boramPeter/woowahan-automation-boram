"""모든 Page Object의 부모. 찾기·대기·탭·읽기만 제공하고, 화면별 지식(로케이터, 이동 흐름)은 자식 Page가 가진다."""
import time

TIMEOUT_DEFAULT = 5
TIMEOUT_PAY = 30        # 결제는 서버 지연 고려. 조건 충족 시 즉시 통과하므로 길어도 느려지지 않는다


class UiTimeoutError(Exception):
    """요소/조건 대기 시간 초과 (환경 불안정 가능 → 재시도 대상).
    검증 실패인 AssertionError와 타입으로 구분해 retry가 '재시도할 실패 / 즉시 중단할 실패'를 가른다."""


class BasePage:
    ANCHOR = None       # 이 화면이 떴다는 증거 로케이터. 자식 Page가 지정한다 (없으면 로딩 검증 생략)

    def __init__(self, d):
        self.d = d      # uiautomator2 단말 객체
        self.assert_loaded()

    def assert_loaded(self):
        """화면 진입 검증. 다음 동작에서 엉뚱한 요소의 타임아웃으로 드러나지 않고, 어느 화면에서 막혔는지 바로 알려준다."""
        if self.ANCHOR is not None:
            self._find(self.ANCHOR, f"{type(self).__name__} 화면 진입")

    def _find(self, locator, name, timeout=TIMEOUT_DEFAULT):
        """요소가 나타날 때까지 기다린다. 못 찾으면 '무엇이 안 보였는지' 담긴 예외 (원본은 None → NPE)."""
        el = self.d(**locator)
        if not el.wait(timeout=timeout):
            raise UiTimeoutError(f"'{name}' 미노출 ({timeout}s) locator={locator}")
        return el

    def tap(self, locator, name, timeout=TIMEOUT_DEFAULT):
        self._find(locator, name, timeout).click(timeout=1)     # 노출을 이미 확인했으므로 u2 기본 대기를 다시 타지 않는다

    def text_of(self, locator, name, timeout=TIMEOUT_DEFAULT):
        return self._find(locator, name, timeout).get_text() or ""

    def is_present(self, locator):
        """대기 없이 현재 화면만 즉시 확인 (폴링용)."""
        return bool(self.d(**locator).exists)

    @staticmethod
    def wait_until(condition, name, timeout=TIMEOUT_DEFAULT, poll=0.3):
        """condition()이 참값을 돌려주는 즉시 그 값을 반환한다 (고정 sleep 없음). 시간 초과 시 UiTimeoutError."""
        end = time.time() + timeout
        while time.time() < end:
            result = condition()
            if result:
                return result
            time.sleep(poll)
        raise UiTimeoutError(f"'{name}' 조건 미충족 ({timeout}s)")
