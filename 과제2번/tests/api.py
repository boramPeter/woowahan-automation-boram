"""비동기 API 클라이언트 + 상품 상수. HTTP 호출만 담당하고 검증은 asserts.py에서 한다."""
import asyncio
import time

import httpx

TIMEOUT = 5

# 초기 데이터(server/data/products.json)와 맞춘 상수
NORMAL, NORMAL_NAME, NORMAL_STOCK = "100230451", "국산 생수 2L 6입", 10
LAST = "100871204"      # 한정판 딸기 케이크 (레이스 컨디션 대상: 재고 1개)
LAST_STOCK = 1
SOLD = "100455890"      # 처음부터 품절 (재고 0)
UNKNOWN = "999999999"   # 존재하지 않는 상품
PAID_QTY = 2            # paid_order fixture가 미리 주문해 두는 수량


class BMartApi:
    """B마트 재고 API를 호출하는 비동기 클라이언트. 호출만 하고 검증은 asserts.py가 한다."""

    def __init__(self, base_url):
        """base_url에 연결하는 httpx 클라이언트를 만들고, 원복용 주문 추적 목록을 초기화한다."""
        self._http = httpx.AsyncClient(base_url=base_url, timeout=TIMEOUT)
        self.created_orders = []  # teardown에서 전부 취소(원복)하기 위한 추적 목록
        self.admin_edited = False
        self.last_sent_at = []  # fire_orders가 마지막으로 요청을 보낸 시각(초) 목록

    async def close(self):
        """HTTP 연결을 닫는다."""
        await self._http.aclose()

    async def request(self, method, path, body=None):
        """표 기반 테스트용 범용 호출."""
        return await self._http.request(method, path, json=body)

    async def get_stock(self, pid):
        """GET 재고 조회."""
        return await self._http.get(f"/v1/products/{pid}/stock")

    async def stock_of(self, pid):
        """재고 조회 후 stock 숫자만 돌려준다."""
        return (await self.get_stock(pid)).json()["stock"]

    async def order(self, pid, qty=1, customer="cust-1"):
        """POST 주문 생성. 201이면 주문번호를 추적 목록에 기록한다 (teardown 때 취소하기 위해)."""
        resp = await self._http.post("/v1/orders",
                                     json={"productId": pid, "quantity": qty, "customerId": customer})
        if resp.status_code == 201:
            self.created_orders.append(resp.json()["orderId"])
        return resp

    async def cancel(self, oid):
        """POST 주문 취소."""
        return await self._http.post(f"/v1/orders/{oid}/cancel")

    async def admin_set_stock(self, pid, stock):
        """PUT 운영자 재고 수정. 수정 이력이 있음을 표시한다 (teardown이 원래 값으로 복구하기 위해)."""
        self.admin_edited = True
        return await self._http.put(f"/v1/admin/products/{pid}/stock", json={"stock": stock})

    async def rollback_all(self):
        """이 테스트가 만든 주문을 모두 취소해 재고를 원복한다 (여러 번 불러도 안전)."""
        orders, self.created_orders = self.created_orders, []
        await asyncio.gather(*(self.cancel(oid) for oid in orders))

    async def fire_orders(self, pid, customers, gap_ms, qty=1):
        """customers를 gap_ms 간격으로 시차를 두고 동시에 주문한다. 응답은 입력 순서대로 반환.
        실제 발사 시각은 last_sent_at에 남겨 간격이 지켜졌는지 확인할 수 있게 한다."""
        sent_at = [0.0] * len(customers)

        async def send(i, customer):
            """i번째 고객의 주문을 i*gap_ms 만큼 늦춰서 보낸다."""
            await asyncio.sleep(i * gap_ms / 1000)
            sent_at[i] = time.perf_counter()
            return await self.order(pid, qty, customer=customer)

        results = await asyncio.gather(*(send(i, c) for i, c in enumerate(customers)))
        self.last_sent_at = sent_at
        return results
