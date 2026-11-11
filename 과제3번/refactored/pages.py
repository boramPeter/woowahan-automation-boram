"""화면별 Page Object. 각 동작이 다음 화면 Page를 반환해서 흐름 순서를 코드 구조가 강제한다.

Shop → Menu → Payment → OrderStatus
"""
from dataclasses import dataclass

from base_page import BasePage, TIMEOUT_DEFAULT, TIMEOUT_PAY, UiTimeoutError


@dataclass(frozen=True)
class OrderSummary:
    """주문 상태 화면에 표시된 값. 검증은 테스트가 하고, Page는 읽기만 한다."""
    status: str
    order_no: str
    shop: str
    menu: str


class OrderStatusPage(BasePage):
    # resourceId 이름은 가정값 → 실제 앱 값으로 교체. u2 resourceId는 전체 ID 정확 일치라 패키지 접두어는 정규식으로 흡수한다
    STATUS = {"resourceIdMatches": ".*:id/order_status"}
    ORDER_NO = {"resourceIdMatches": ".*:id/order_no"}
    SHOP = {"resourceIdMatches": ".*:id/order_shop"}
    MENU = {"resourceIdMatches": ".*:id/order_menu"}
    ANCHOR = STATUS

    def read(self, expected_status=None, timeout=TIMEOUT_DEFAULT):
        """주문 결과를 읽는다. expected_status를 주면 상태 텍스트가 그 값이 될 때까지 먼저 기다린다.

        화면이 '결제 처리중' → '접수 대기'처럼 바뀌는 앱에서 이른 시점의 값을 읽어 거짓 실패하는 것을 막는다.
        시간이 지나도 안 바뀌면 예외 없이 마지막 값을 읽는다 → 타임아웃이 아니라 verify의 '상태 불일치' 검증 실패로 보고된다.
        """
        if expected_status is not None:
            try:
                self.wait_until(lambda: self.is_present({**self.STATUS, "text": expected_status}),
                                f"주문 상태 '{expected_status}' 전환", timeout)
            except UiTimeoutError:
                pass
        return OrderSummary(
            status=self.text_of(self.STATUS, "order_status"),
            order_no=self.text_of(self.ORDER_NO, "order_no"),
            shop=self.text_of(self.SHOP, "order_shop"),
            menu=self.text_of(self.MENU, "order_menu"),
        )


class PaymentPage(BasePage):
    PAY_BTN = {"text": "결제하기"}                 # textContains("결제")는 "결제 수단" 등을 오클릭할 수 있어 정확 일치
    PAY_ERROR = {"textContains": "결제에 실패"}
    ANCHOR = PAY_BTN

    def pay(self):
        # 결제 버튼 직전에 표시: 이후 실패는 retry가 재시도하지 않는다 (중복 주문 방지)
        self.d.payment_started = True
        self.tap(self.PAY_BTN, "pay_btn")

        # Thread.sleep(5000) 대체: 성공/실패 중 먼저 나타나는 쪽에서 즉시 반환, 둘 다 없으면 TIMEOUT_PAY까지만 대기
        def result():
            if self.is_present(self.PAY_ERROR):             # 실패를 먼저 본다 (오탐 방지)
                return "FAILED"
            if self.is_present(OrderStatusPage.STATUS):
                return "SUCCESS"
            return None

        if self.wait_until(result, "결제 결과(주문상태 화면/실패 얼럿)", timeout=TIMEOUT_PAY) == "FAILED":
            # 환경 문제가 아니라 '검증 실패' → UiTimeoutError가 아닌 AssertionError (재시도 대상 아님)
            raise AssertionError("결제 실패 얼럿 노출")
        return OrderStatusPage(self.d)


class MenuPage(BasePage):
    ORDER_BTN = {"text": "주문하기"}
    ANCHOR = ORDER_BTN

    @staticmethod
    def menu_item(name):
        return {"text": name}

    def select_menu(self, name):
        self.tap(self.menu_item(name), f"menu({name})")
        return self

    def order(self):
        self.tap(self.ORDER_BTN, "order_btn")
        return PaymentPage(self.d)


class ShopPage(BasePage):
    # 시작 화면의 고유 요소를 모르므로 ANCHOR 없음 (앱 확인 후 지정)

    @staticmethod
    def shop_item(name):
        return {"text": name}       # 정확 일치: "치킨" 포함 문구가 여럿이어도 의도한 가게만 누른다

    def select_shop(self, name):
        self.tap(self.shop_item(name), f"shop({name})")
        return MenuPage(self.d)
