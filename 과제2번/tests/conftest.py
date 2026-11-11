import os

import pytest
import pytest_asyncio

from tests.api import LAST, NORMAL, PAID_QTY, BMartApi
from tests.asserts import assert_stock, created_order_id


@pytest.fixture(scope="session")
def base_url():
    """러너가 환경변수로 넘긴 테스트 대상 서버 주소를 읽는다. 없으면 러너로 실행하라는 안내 후 종료."""
    url = os.getenv("BMART_BASE_URL")
    if not url:
        pytest.exit("러너로 실행하세요: uv run python runner.py", returncode=2)
    return url


@pytest_asyncio.fixture
async def api(base_url):
    """테스트마다 새 클라이언트. 이 클라이언트로 만든 주문은 teardown에서 전부 취소한다."""
    client = BMartApi(base_url)
    yield client
    await client.rollback_all()
    await client.close()


async def _restore(api, pid, initial):
    """주문 원복 → 운영자 수정분 복구 → 시작 재고와 같은지 확인(테스트 간 오염·재고 불변 검증)."""
    await api.rollback_all()
    if api.admin_edited:
        await api.admin_set_stock(pid, initial)
    await assert_stock(api, pid, initial)


@pytest_asyncio.fixture
async def normal_product(api):
    """재고 10개 상품. setup: 재고 조회 / teardown: 원복 + 재고 불변 확인."""
    initial = await api.stock_of(NORMAL)
    yield NORMAL
    await _restore(api, NORMAL, initial)


@pytest_asyncio.fixture
async def last_product(api):
    """재고 1개(마지막 1개) 상품. setup: 재고 조회 / teardown: 원복."""
    initial = await api.stock_of(LAST)
    yield LAST
    await _restore(api, LAST, initial)


@pytest_asyncio.fixture
async def paid_order(api, normal_product):
    """재고 10개 상품에 2개가 이미 결제된 상태. 주문번호를 돌려준다."""
    return created_order_id(await api.order(normal_product, PAID_QTY))


@pytest_asyncio.fixture
async def sold_out_product(api, last_product):
    """cust-1이 마지막 1개를 결제해 품절된 상태. (상품 ID, 주문번호)를 돌려준다."""
    return last_product, created_order_id(await api.order(last_product, 1, customer="cust-1"))


@pytest_asyncio.fixture
async def other_tab(base_url):
    """같은 서버를 보는 다른 탭(별도 클라이언트). 조회 전용이라 원복할 주문은 없다."""
    tab = BMartApi(base_url)
    yield tab
    await tab.close()
