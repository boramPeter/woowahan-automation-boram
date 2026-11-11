from dataclasses import dataclass

from pages import OrderSummary, ShopPage
from retry import retry


@dataclass(frozen=True)
class OrderScenario:
    """테스트 데이터. 하드코딩을 본문 밖으로 빼서 시나리오 추가·파라미터화가 쉽다."""
    shop: str
    menu: str
    expected_status: str


SCENARIO = OrderScenario(shop="치킨", menu="후라이드", expected_status="접수 대기")


@retry(retries=1, delay=2)
def test_order_flow(device):
    """가게 → 메뉴 → 주문 → 결제 후, 주문 내역이 선택한 내용과 일치하고 '접수 대기' 상태다. (실결제: 테스트 계정/샌드박스 전용)"""
    summary = (
        ShopPage(device)
        .select_shop(SCENARIO.shop)
        .select_menu(SCENARIO.menu)
        .order()
        .pay()
        .read(SCENARIO.expected_status)     # 상태가 기대값으로 바뀔 때까지 대기 후 읽기
    )
    verify(summary, SCENARIO)


def verify(actual: OrderSummary, expected: OrderScenario):
    """실패 항목을 모아 한 번에 보고한다 (첫 불일치에서 멈추면 나머지 원인을 다시 돌려야 알 수 있다)."""
    errors = []
    if actual.status != expected.expected_status:
        errors.append(f"주문 상태 불일치: {actual.status!r} (기대 {expected.expected_status!r})")
    if not actual.order_no.strip():
        errors.append("주문번호 미노출")
    if expected.shop not in actual.shop:
        errors.append(f"가게 불일치: {actual.shop!r} (기대 {expected.shop!r} 포함)")
    if expected.menu not in actual.menu:
        errors.append(f"메뉴 불일치: {actual.menu!r} (기대 {expected.menu!r} 포함)")
    assert not errors, " / ".join(errors)
