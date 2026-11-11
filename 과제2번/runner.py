"""테스트 러너: 테스트 서버 기동 → pytest 실행 → 서버 종료. 터미널 하나로 실행한다.

    uv run python runner.py                  # 전체
    uv run python runner.py -m smoke         # 마커 선택
    uv run python runner.py --case 14        # 시나리오(케이스 ID) 14번만
    uv run python runner.py -k cancel        # 이름 필터
    uv run python runner.py --base-url URL   # 서버를 띄우지 않고 해당 서버를 대상으로 실행
"""
import argparse
import os
import re
import sys
from pathlib import Path

import pytest

from server.app import ServerThread

ROOT = Path(__file__).resolve().parent


def load_titles():
    """TEST_SCENARIOS.md에서 {케이스 ID: 검증 내용}을 읽는다. 파일이 없으면 빈 dict."""
    path = ROOT / "TEST_SCENARIOS.md"
    if not path.exists():
        return {}
    rows = re.findall(r"^\| (\d+) \| [^|]+ \| ([^|]+) \|", path.read_text(encoding="utf-8"), re.M)
    return {int(cid): title.strip() for cid, title in rows}


class CaseReporter:
    """케이스별 결과를 한 줄씩 출력하는 pytest 플러그인: [PASS] #22 검증 내용 (0.01s)."""

    def __init__(self, titles):
        """titles: {케이스 ID: 검증 내용}."""
        self.titles = titles
        self.state = {}
        self.config = None

    def pytest_configure(self, config):
        """terminalreporter를 쓰기 위해 config를 보관한다."""
        self.config = config

    def pytest_report_teststatus(self, report):
        """기본 진행 표시(점, 퍼센트)를 없애고 집계(passed/failed/error)만 유지한다."""
        if report.passed and report.when != "call":
            return None
        category = "error" if report.failed and report.when != "call" else report.outcome
        return category, "", ""

    def pytest_runtest_logreport(self, report):
        """setup/call/teardown 결과를 합쳐 케이스 하나가 끝나면(teardown) 한 줄 출력한다."""
        st = self.state.setdefault(report.nodeid, {"result": "PASS", "time": 0.0, "reasons": []})
        st["time"] += report.duration
        if report.failed:  # 실패 원인: 트레이스백 중 "E " 로 시작하는 첫 줄
            errors = [l[1:].strip() for l in report.longreprtext.splitlines() if l.startswith("E ")]
            st["reasons"].append(f"{report.when}: {errors[0] if errors else report.longreprtext[-120:]}")
        if report.failed and st["result"] == "PASS":
            st["result"] = "FAIL" if report.when == "call" else "ERROR"  # call 실패=검증 실패, 그 외=준비/원복 오류
        elif report.skipped and st["result"] == "PASS":
            st["result"] = "SKIP"
        if report.when == "teardown":
            found = re.search(r"c(\d\d)_", report.nodeid)
            cid = int(found[1]) if found else None
            title = self.titles.get(cid, report.nodeid)
            label = f"#{cid:02d}" if cid else "#--"
            reporter = self.config.pluginmanager.get_plugin("terminalreporter")
            reporter.write_line(f"[{st['result']:5}] {label} {title} ({st['time']:.2f}s)")
            for reason in st["reasons"]:
                reporter.write_line(f"          ↳ {reason}")


def parse_args():
    """커맨드라인 옵션(-m, -c, -k, --base-url, -v)을 읽는다."""
    ap = argparse.ArgumentParser(description="B마트 재고 API 테스트 러너")
    ap.add_argument("-m", "--marker", help="pytest 마커 식 (예: smoke, 'order or cancel')")
    ap.add_argument("-c", "--case", type=int, help="케이스 ID (TEST_SCENARIOS.md의 시나리오 번호)")
    ap.add_argument("-k", "--keyword", help="테스트 이름 필터")
    ap.add_argument("--base-url", help="외부 서버 주소. 지정하면 테스트 서버를 띄우지 않는다")
    ap.add_argument("-v", "--verbose", action="store_true")
    return ap.parse_args()


def main():
    """서버를 띄우고(또는 --base-url 사용) pytest를 실행한 뒤 서버를 내린다. pytest 종료 코드를 반환한다."""
    args = parse_args()
    server = None
    if args.base_url:
        base_url = args.base_url
    else:
        server = ServerThread()
        server.start()
        base_url = server.base_url
    os.environ["BMART_BASE_URL"] = base_url

    # 어느 위치에서 실행해도 같은 설정·경로를 쓰도록 절대 경로로 지정
    pytest_args = [str(ROOT / "tests"), "-c", str(ROOT / "pytest.ini"), "--rootdir", str(ROOT)]
    if args.marker:
        pytest_args += ["-m", args.marker]
    keywords = [f"c{args.case:02d}_"] if args.case else []
    if args.keyword:
        keywords.append(args.keyword)
    if keywords:
        pytest_args += ["-k", " and ".join(keywords)]
    pytest_args += ["-v"] if args.verbose else ["-q", "--tb=no", "-o", "console_output_style=classic"]  # 기본은 케이스별 한 줄(CaseReporter), -v는 pytest 기본 상세 출력

    print(f"[runner] target: {base_url}")
    try:
        return pytest.main(pytest_args, plugins=[] if args.verbose else [CaseReporter(load_titles())])
    finally:
        if server:
            server.stop()


if __name__ == "__main__":
    sys.exit(main())
