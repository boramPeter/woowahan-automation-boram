import os

import pytest
import uiautomator2 as u2

from session import restart_app


@pytest.fixture
def device():
    """매 테스트를 깨끗한 앱 상태에서 시작한다 (이전 테스트가 남긴 화면에 영향받지 않도록 앱 재시작)."""
    d = u2.connect(os.environ.get("ANDROID_SERIAL") or None)
    restart_app(d)
    return d
