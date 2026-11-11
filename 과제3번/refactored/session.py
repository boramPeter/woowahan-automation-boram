import os

APP_PACKAGE = os.environ.get("APP_PACKAGE", "")     # 실제 앱 패키지를 환경변수로 지정


def restart_app(d):
    """앱을 종료 후 재시작해 시작 화면으로 되돌린다 (테스트 시작 시, retry 재시도 전)."""
    if not APP_PACKAGE:
        raise RuntimeError("APP_PACKAGE 환경변수를 지정하세요")
    d.app_start(APP_PACKAGE, stop=True)
