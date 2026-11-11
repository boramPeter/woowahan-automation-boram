"""검증(assert) 모음. 테스트 본문에는 assert를 직접 쓰지 않고 여기 함수만 호출한다."""


def assert_status(resp, expected, code=None):
    """HTTP 상태와 에러 code 검증. 실패 시 응답 바디를 함께 보여준다."""
    body = resp.text[:200]
    assert resp.status_code == expected, f"기대 {expected}, 실제 {resp.status_code} {body}"
    if code is not None:
        assert resp.json().get("code") == code, f"기대 code={code}, 실제 {body}"


async def assert_stock(api, pid, expected):
    """상품의 현재 재고가 기대값과 같은지 조회해서 확인한다."""
    actual = await api.stock_of(pid)
    assert actual == expected, f"재고 기대 {expected}, 실제 {actual} (상품 {pid})"


def assert_stock_view(resp, pid, name, stock):
    """재고 조회/운영자 수정 응답의 필드 전체 검증."""
    assert_status(resp, 200)
    assert resp.json() == {"productId": pid, "name": name, "stock": stock,
                           "soldOut": stock == 0, "orderable": stock > 0}, resp.text


def assert_sold_out_view(resp, pid):
    """재고 조회 응답이 품절 상태(stock 0, soldOut true, orderable false)인지 확인한다."""
    assert_status(resp, 200)
    body = resp.json()
    assert body["productId"] == pid
    assert (body["stock"], body["soldOut"], body["orderable"]) == (0, True, False), body


def assert_orderable_view(resp, pid, stock):
    """재고 조회 응답이 구매 가능 상태(soldOut false, orderable true, 기대 재고)인지 확인한다."""
    assert_status(resp, 200)
    body = resp.json()
    assert body["productId"] == pid
    assert (body["stock"], body["soldOut"], body["orderable"]) == (stock, False, True), body


def assert_order_paid(resp, pid, qty, remaining):
    """주문 응답이 201 PAID이고 상품·수량·차감 후 재고가 기대값과 같은지 확인한다."""
    assert_status(resp, 201)
    body = resp.json()
    assert body["orderId"].startswith("ORD-"), body
    assert (body["status"], body["productId"], body["quantity"], body["remainingStock"]) == \
           ("PAID", pid, qty, remaining), body


def created_order_id(resp):
    """사전 단계(setup)용: 주문이 201로 만들어졌는지 확인하고 orderId를 돌려준다."""
    assert_status(resp, 201)
    return resp.json()["orderId"]


def assert_canceled(resp, oid, restored):
    """취소 응답이 200 CANCELED이고 복구 후 재고가 기대값과 같은지 확인한다."""
    assert_status(resp, 200)
    assert resp.json() == {"orderId": oid, "status": "CANCELED", "restoredStock": restored}, resp.text


def assert_one_winner(responses, pid, qty=1, remaining=0, loser_code="SOLD_OUT"):
    """동시 주문 결과: 정확히 1건 201(차감 후 재고 remaining), 나머지는 모두 409 loser_code."""
    codes = sorted(r.status_code for r in responses)
    expected = [201] + [409] * (len(responses) - 1)
    detail = [(r.status_code, r.text[:60]) for r in responses]
    assert codes == expected, f"기대 {expected}, 실제 {codes} {detail}"
    for r in responses:
        if r.status_code == 409:
            assert_status(r, 409, loser_code)
        else:
            body = r.json()
            assert (body["productId"], body["quantity"], body["remainingStock"]) == (pid, qty, remaining), body


def assert_serial_outcome(actual, allowed):
    """동시 요청의 결과가 '어느 한쪽이 먼저 처리된' 직렬 실행 결과 중 하나와 같은지 확인한다 (중간 상태가 섞이면 실패)."""
    assert actual in allowed, f"직렬 실행 결과 {sorted(allowed)} 중 하나여야 하는데 실제 {actual}"


def assert_send_gap(sent_at, gap_ms, tolerance_ms=50):
    """요청 발사 간격이 목표(gap_ms)대로 지켜졌는지 확인한다 (너무 일찍/너무 늦게 나가면 시나리오가 성립하지 않음)."""
    for prev, cur in zip(sent_at, sent_at[1:]):
        actual_ms = (cur - prev) * 1000
        assert gap_ms - 2 <= actual_ms <= gap_ms + tolerance_ms, f"목표 간격 {gap_ms}ms, 실제 {actual_ms:.1f}ms"


def assert_message_contains(exc_info, *words):
    """네거티브 케이스용: pytest.raises로 잡은 AssertionError 메시지에 기대한 단어가 모두 들어 있는지 확인한다."""
    text = str(exc_info.value)
    assert all(w in text for w in words), f"실패 메시지에 {words}가 없음: {text}"

