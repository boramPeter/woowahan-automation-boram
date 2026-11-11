"""B마트 재고 API 테스트.

1) 표 기반: 요청 → 기대 상태 코드/에러 코드 (재고 불변은 normal_product fixture teardown이 확인)
2) 흐름/동시성: 상태가 이어지는 시나리오. 데이터 준비는 fixture가 한다.
"""
import asyncio

import httpx
import pytest

from tests.api import LAST, LAST_STOCK, NORMAL, NORMAL_NAME, NORMAL_STOCK, PAID_QTY, SOLD, UNKNOWN
from tests.asserts import (assert_canceled, assert_one_winner, assert_order_paid, assert_orderable_view,
                           assert_message_contains, assert_send_gap, assert_serial_outcome, assert_sold_out_view, assert_status,
                           assert_stock, assert_stock_view, created_order_id)


# ======== 1) 표 기반 ========
def order_body(pid, qty):
    """주문 요청 바디를 만든다 (qty에 0/음수/문자열/None을 넣어 잘못된 요청을 표현)."""
    return {"productId": pid, "quantity": qty, "customerId": "cust-1"}


ERROR_CASES = [
    # 케이스ID 1 | 없는 상품을 조회하면 404 [R0]
    # flow: 존재하지 않는 상품 조회 → 404 PRODUCT_NOT_FOUND
    pytest.param("GET", f"/v1/products/{UNKNOWN}/stock", None, 404, "PRODUCT_NOT_FOUND", id="c01_view_unknown_product"),
    # 케이스ID 2 | 재고보다 많이 주문하면 거절되고 재고는 그대로다 [R2]
    # flow: 재고(10)보다 많은 11개 주문 → 409 INSUFFICIENT_STOCK → 재고 10 유지
    pytest.param("POST", "/v1/orders", order_body(NORMAL, NORMAL_STOCK + 1), 409, "INSUFFICIENT_STOCK", id="c02_order_over_stock"),
    # 케이스ID 3 | 수량 0은 잘못된 요청이다 [R0]
    # flow: 수량 0 주문 → 400 INVALID_QUANTITY → 재고 10 유지
    pytest.param("POST", "/v1/orders", order_body(NORMAL, 0), 400, "INVALID_QUANTITY", id="c03_order_qty_zero"),
    # 케이스ID 4 | 음수 수량은 잘못된 요청이다 [R0]
    # flow: 수량 -1 주문 → 400 INVALID_QUANTITY → 재고 10 유지
    pytest.param("POST", "/v1/orders", order_body(NORMAL, -1), 400, "INVALID_QUANTITY", id="c04_order_qty_negative"),
    # 케이스ID 5 | 문자열 수량은 잘못된 요청이다 [R0]
    # flow: 수량 "2"(문자열) 주문 → 400 INVALID_QUANTITY → 재고 10 유지
    pytest.param("POST", "/v1/orders", order_body(NORMAL, "2"), 400, "INVALID_QUANTITY", id="c05_order_qty_string"),
    # 케이스ID 6 | 수량이 없으면 잘못된 요청이다 [R0]
    # flow: 수량 null 주문 → 400 INVALID_QUANTITY → 재고 10 유지
    pytest.param("POST", "/v1/orders", order_body(NORMAL, None), 400, "INVALID_QUANTITY", id="c06_order_qty_missing"),
    # 케이스ID 7 | 없는 상품을 주문하면 404 [R0]
    # flow: 존재하지 않는 상품 주문 → 404 PRODUCT_NOT_FOUND
    pytest.param("POST", "/v1/orders", order_body(UNKNOWN, 1), 404, "PRODUCT_NOT_FOUND", id="c07_order_unknown_product"),
    # 케이스ID 8 | 없는 주문을 취소하면 404 [R0]
    # flow: 존재하지 않는 주문번호 취소 → 404 ORDER_NOT_FOUND
    pytest.param("POST", "/v1/orders/ORD-9999/cancel", None, 404, "ORDER_NOT_FOUND", id="c08_cancel_unknown_order"),
    # 케이스ID 9 | 음수 재고는 입력할 수 없다 [R6]
    # flow: 재고를 -1로 수정 → 400 INVALID_STOCK → 재고 10 유지
    pytest.param("PUT", f"/v1/admin/products/{NORMAL}/stock", {"stock": -1}, 400, "INVALID_STOCK", id="c09_admin_edit_negative"),
]


@pytest.mark.parametrize("method,path,body,status,code", ERROR_CASES)
async def test_error_response(api, normal_product, method, path, body, status, code):
    """[표 기반 1~9] 요청을 보내 기대한 상태 코드와 에러 코드가 오는지 확인한다. 재고 불변은 fixture teardown이 확인한다."""
    resp = await api.request(method, path, body)
    assert_status(resp, status, code)


# ======== 2) 흐름 / 동시성 ========
# ---- 조회 ----
@pytest.mark.smoke
async def test_c10_view_all_fields(api, normal_product):
    # 케이스ID 10 | 존재하는 상품의 재고 조회 응답이 스펙의 필드를 모두 갖는다 [R1]
    # flow: 재고 10개 상품 조회 → 200 + productId/name/stock/soldOut/orderable 일치
    resp = await api.get_stock(normal_product)
    assert_stock_view(resp, NORMAL, NORMAL_NAME, NORMAL_STOCK)


async def test_c11_view_repeat_no_deduct(api, normal_product):
    # 케이스ID 11 | 장바구니 담기(=조회)를 반복해도 재고가 차감되지 않는다 [R1]
    # flow: 재고 조회 3회 반복 → 재고 조회 → 여전히 10
    for _ in range(3):
        await api.get_stock(normal_product)
    await assert_stock(api, normal_product, NORMAL_STOCK)


# ---- 주문 ----
@pytest.mark.smoke
async def test_c12_order_one_deducts(api, normal_product):
    # 케이스ID 12 | 1개 주문하면 재고가 1 줄어든다 [R2]
    # flow: 1개 주문 → 201 PAID + remainingStock 9 → 재고 조회 9
    resp = await api.order(normal_product, 1)
    assert_order_paid(resp, NORMAL, 1, NORMAL_STOCK - 1)
    await assert_stock(api, normal_product, NORMAL_STOCK - 1)


async def test_c13_order_three_deducts(api, normal_product):
    # 케이스ID 13 | 3개 주문하면 주문 수량만큼 한 번에 차감된다 [R2]
    # flow: 3개 주문 → 201 PAID + remainingStock 7 → 재고 조회 7
    resp = await api.order(normal_product, 3)
    assert_order_paid(resp, NORMAL, 3, NORMAL_STOCK - 3)
    await assert_stock(api, normal_product, NORMAL_STOCK - 3)


# ---- 취소 ----
@pytest.mark.smoke
async def test_c14_cancel_restores_stock(api, normal_product, paid_order):
    # 케이스ID 14 | 취소하면 차감됐던 재고가 즉시 복구된다 [R4]
    # flow: (준비: 2개 결제 완료) 재고 8 확인 → 취소 → 200 CANCELED + restoredStock 10 → 재고 조회 10
    await assert_stock(api, normal_product, NORMAL_STOCK - PAID_QTY)
    resp = await api.cancel(paid_order)
    assert_canceled(resp, paid_order, NORMAL_STOCK)
    await assert_stock(api, normal_product, NORMAL_STOCK)


async def test_c15_cancel_twice(api, normal_product, paid_order):
    # 케이스ID 15 | 같은 주문을 두 번 취소해도 재고가 두 번 복구되지 않는다 [R4]
    # flow: (준비: 2개 결제 완료) 취소 200 → 같은 주문 재취소 → 409 ALREADY_CANCELED → 재고 10(12가 되면 안 됨)
    assert_status(await api.cancel(paid_order), 200)
    resp = await api.cancel(paid_order)
    assert_status(resp, 409, "ALREADY_CANCELED")
    await assert_stock(api, normal_product, NORMAL_STOCK)


# ---- 품절 ----
async def test_c16_last_item_sold_out(api, last_product):
    # 케이스ID 16 | 마지막 1개가 팔려 재고가 0이 되면 품절 상태로 바뀐다 [R5]
    # flow: 마지막 1개 주문 201 → 재고 조회 → stock 0 / soldOut true / orderable false
    created_order_id(await api.order(last_product, 1))
    resp = await api.get_stock(last_product)
    assert_sold_out_view(resp, LAST)


async def test_c17_order_on_sold_out(api, sold_out_product):
    # 케이스ID 17 | 품절된 상품은 주문할 수 없고 재고는 음수가 되지 않는다 [R5]
    # flow: (준비: cust-1이 마지막 1개 결제) 다른 고객이 주문 → 409 SOLD_OUT → 재고 0 유지
    pid, _ = sold_out_product
    resp = await api.order(pid, 1, customer="cust-2")
    assert_status(resp, 409, "SOLD_OUT")
    await assert_stock(api, pid, 0)


async def test_c18_seed_sold_out_product(api):
    # 케이스ID 18 | 처음부터 재고 0인 상품은 품절 표시 + 주문 불가다 [R5]
    # flow: 재고 0 상품 조회 → 품절 상태 확인 → 주문 → 409 SOLD_OUT
    assert_sold_out_view(await api.get_stock(SOLD), SOLD)
    resp = await api.order(SOLD, 1)
    assert_status(resp, 409, "SOLD_OUT")


async def test_c19_cancel_reopens_sale(api, sold_out_product):
    # 케이스ID 19 | 품절 후 취소로 재고가 복구되면 다른 고객이 즉시 구매할 수 있다 [R4, R5]
    # flow: (준비: cust-1이 마지막 1개 결제) 품절 확인 → 취소 → 구매 가능 상태 확인 → cust-2 주문 201
    pid, oid = sold_out_product
    assert_sold_out_view(await api.get_stock(pid), LAST)
    assert_canceled(await api.cancel(oid), oid, 1)
    assert_orderable_view(await api.get_stock(pid), LAST, 1)
    created_order_id(await api.order(pid, 1, customer="cust-2"))


# ---- 운영자 수동 수정 ----
async def test_c20_admin_edit_applied(api, normal_product):
    # 케이스ID 20 | 운영자가 입력한 재고가 즉시 반영된다 [R6]
    # flow: 재고를 25로 수정 → 200 + 수정값 응답 → 재고 조회 25
    resp = await api.admin_set_stock(normal_product, 25)
    assert_stock_view(resp, NORMAL, NORMAL_NAME, 25)
    await assert_stock(api, normal_product, 25)


async def test_c21_admin_edit_zero(api, normal_product):
    # 케이스ID 21 | 운영자가 재고를 0으로 수정하면 품절 처리되고 주문이 막힌다 [R6, R5]
    # flow: 재고를 0으로 수정 → 조회 시 품절 상태 → 주문 → 409 SOLD_OUT
    assert_status(await api.admin_set_stock(normal_product, 0), 200)
    assert_sold_out_view(await api.get_stock(normal_product), NORMAL)
    resp = await api.order(normal_product, 1)
    assert_status(resp, 409, "SOLD_OUT")


# ---- 동시성: 마지막 1개에 여러 고객이 도달 ----
RACE_CASES = [
    # 케이스ID 22 | A, B가 0ms 간격으로 결제 [R3]
    # flow: 재고 1 확인 → A 발사 → 0ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답
    pytest.param(["cust-A", "cust-B"], 0, id="c22_race_gap_0ms", marks=pytest.mark.smoke),
    # 케이스ID 23 | A, B가 5ms 간격으로 결제 [R3]
    # flow: 재고 1 확인 → A 발사 → 5ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답
    pytest.param(["cust-A", "cust-B"], 5, id="c23_race_gap_5ms"),
    # 케이스ID 24 | A, B가 10ms 간격으로 결제 [R3]
    # flow: 재고 1 확인 → A 발사 → 10ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답
    pytest.param(["cust-A", "cust-B"], 10, id="c24_race_gap_10ms"),
    # 케이스ID 25 | A, B가 20ms 간격으로 결제 [R3]
    # flow: 재고 1 확인 → A 발사 → 20ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답
    pytest.param(["cust-A", "cust-B"], 20, id="c25_race_gap_20ms"),
    # 케이스ID 26 | A, B가 50ms 간격으로 결제 [R3]
    # flow: 재고 1 확인 → A 발사 → 50ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답
    pytest.param(["cust-A", "cust-B"], 50, id="c26_race_gap_50ms"),
    # 케이스ID 27 | A, B가 100ms 간격으로 결제 [R3]
    # flow: 재고 1 확인 → A 발사 → 100ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답
    pytest.param(["cust-A", "cust-B"], 100, id="c27_race_gap_100ms"),
    # 케이스ID 28 | A, B가 500ms 간격으로 결제 [R3]
    # flow: 재고 1 확인 → A 발사 → 500ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답
    pytest.param(["cust-A", "cust-B"], 500, id="c28_race_gap_500ms"),
    # 케이스ID 29 | A, B가 1000ms 간격으로 결제 [R3]
    # flow: 재고 1 확인 → A 발사 → 1000ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답
    pytest.param(["cust-A", "cust-B"], 1000, id="c29_race_gap_1000ms"),
    # 케이스ID 30 | 10명이 5ms 간격으로 연달아 결제 [R3]
    # flow: 재고 1 확인 → 10명이 5ms 간격으로 주문 → 201 1건(remainingStock 0) + 409 SOLD_OUT 9건 → 재고 0 + 품절 응답
    pytest.param([f"cust-{i}" for i in range(10)], 5, id="c30_race_burst_10"),
]


@pytest.mark.concurrency
@pytest.mark.parametrize("customers,gap_ms", RACE_CASES)
async def test_race_one_winner(api, last_product, customers, gap_ms):
    """[동시성 22~30] 재고 1개 상품에 여러 고객이 동시에 주문 → 1건만 성공해 재고가 1→0이 되고, 조회 응답이 품절로 내려온다."""
    await assert_stock(api, last_product, LAST_STOCK)
    results = await api.fire_orders(last_product, customers, gap_ms)
    assert_send_gap(api.last_sent_at, gap_ms)
    assert_one_winner(results, LAST)
    assert_sold_out_view(await api.get_stock(last_product), LAST)


@pytest.mark.concurrency
async def test_c31_race_first_arrival_wins(api, last_product):
    # 케이스ID 31 | 먼저 도달한 요청이 선착순으로 성공하고 나중 요청은 품절이다 [R3]
    # flow: 재고 1 확인 → A 발사 → 30ms 뒤 B 발사 → A 201(remainingStock 0) / B 409 SOLD_OUT → 재고 0 + 품절 응답
    await assert_stock(api, last_product, LAST_STOCK)
    a, b = await api.fire_orders(last_product, ["cust-A", "cust-B"], gap_ms=30)
    assert_order_paid(a, LAST, 1, 0)
    assert_status(b, 409, "SOLD_OUT")
    assert_sold_out_view(await api.get_stock(last_product), LAST)


# ---- 다른 탭 즉시 반영 ----
async def test_c32_other_tab_sees_sold_out(api, other_tab, last_product):
    # 케이스ID 32 | 한 탭에서 마지막 1개를 주문하면 다른 탭에서 조회한 화면도 바로 품절이다 [R5]
    # flow: 다른 탭이 재고 1 조회(구매 가능) → 이 탭이 마지막 1개 주문 → 다른 탭이 다시 조회 → 즉시 stock 0 / soldOut true
    assert_orderable_view(await other_tab.get_stock(last_product), LAST, LAST_STOCK)
    created_order_id(await api.order(last_product, 1))
    assert_sold_out_view(await other_tab.get_stock(last_product), LAST)


async def test_c33_other_tab_sees_admin_edit(api, other_tab, normal_product):
    # 케이스ID 33 | 운영자가 재고를 수정하면 다른 탭에서 조회한 재고도 바로 바뀐다 [R6]
    # flow: 다른 탭이 재고 10 조회 → 운영자가 25로 수정 → 다른 탭이 다시 조회 → 즉시 25
    await assert_stock(other_tab, normal_product, NORMAL_STOCK)
    assert_status(await api.admin_set_stock(normal_product, 25), 200)
    await assert_stock(other_tab, normal_product, 25)


# ---- 운영자 수정 중 주문 발생 (처리 순서 정의: 서버가 도착 순서대로 직렬 처리) ----
async def test_c34_order_after_admin_edit_uses_new_stock(api, normal_product):
    # 케이스ID 34 | 운영자 수정이 먼저 처리되면 이후 주문은 수정된 재고를 기준으로 차감된다 [R6, R7]
    # flow: 운영자가 재고를 5로 수정 → 3개 주문 → 201 + remainingStock 2 → 재고 조회 2
    assert_status(await api.admin_set_stock(normal_product, 5), 200)
    resp = await api.order(normal_product, 3)
    assert_order_paid(resp, NORMAL, 3, 2)
    await assert_stock(api, normal_product, 2)


async def test_c35_admin_edit_after_order_overwrites(api, last_product):
    # 케이스ID 35 | 주문이 먼저 처리되고 뒤에 운영자 수정이 오면 수정값이 최종 재고가 된다 [R6, R7]
    # flow: 마지막 1개 주문 → remainingStock 0 → 운영자가 5로 수정 → 재고 조회 5(품절 해제)
    resp = await api.order(last_product, 1)
    assert_order_paid(resp, LAST, 1, 0)
    assert_status(await api.admin_set_stock(last_product, 5), 200)
    await assert_stock(api, last_product, 5)


@pytest.mark.concurrency
async def test_c36_order_and_admin_edit_at_once(api, last_product):
    # 케이스ID 36 | 운영자 수정과 주문이 동시에 와도 결과는 한쪽이 먼저 처리된 직렬 결과와 같다 [R6, R7]
    # flow: 재고 1에서 주문 1개와 운영자 5 수정을 동시에 발사 → 주문 201 → (remainingStock, 최종 재고)가 (0, 5) 또는 (4, 4)
    order_resp, edit_resp = await asyncio.gather(api.order(last_product, 1), api.admin_set_stock(last_product, 5))
    assert_status(order_resp, 201)
    assert_status(edit_resp, 200)
    final = await api.stock_of(last_product)
    assert_serial_outcome((order_resp.json()["remainingStock"], final), {(0, 5), (4, 4)})


# ---- 동시성 추가 ----
@pytest.mark.concurrency
async def test_c37_cancel_and_order_at_once(api, sold_out_product):
    # 케이스ID 37 | 품절 상태에서 취소와 다른 고객의 주문이 동시에 와도 재고가 어긋나지 않는다 [R3, R4]
    # flow: (준비: cust-1이 마지막 1개 결제) 취소와 cust-2 주문을 동시에 발사 → (주문 결과, 최종 재고)가 (201, 0) 또는 (409, 1)
    pid, oid = sold_out_product
    cancel_resp, order_resp = await asyncio.gather(api.cancel(oid), api.order(pid, 1, customer="cust-2"))
    assert_status(cancel_resp, 200)
    final = await api.stock_of(pid)
    assert_serial_outcome((order_resp.status_code, final), {(201, 0), (409, 1)})


@pytest.mark.concurrency
async def test_c38_two_big_orders_at_once(api, normal_product):
    # 케이스ID 38 | 재고 10개에 6개씩 동시에 주문하면 한 명만 성공하고 다른 한 명은 재고 부족이다 [R3]
    # flow: A, B가 6개씩 동시에 주문 → 201 1건(remainingStock 4) + 409 INSUFFICIENT_STOCK 1건 → 재고 4
    results = await api.fire_orders(normal_product, ["cust-A", "cust-B"], gap_ms=0, qty=6)
    assert_one_winner(results, NORMAL, qty=6, remaining=4, loser_code="INSUFFICIENT_STOCK")
    await assert_stock(api, normal_product, 4)


# ---- 네거티브: 검증 함수가 틀린 값을 실제로 잡아내는지 (실패가 나와야 PASS) ----
@pytest.mark.negative
async def test_c39_negative_wrong_stock_is_caught(api, normal_product):
    # 케이스ID 39 | (네거티브) 기대 재고가 틀리면 재고 검증이 실패로 잡힌다. 실패가 확인되면 PASS [검증 헬퍼]
    # flow: 재고 10개 상품에서 기대 재고를 11로 잘못 지정 → AssertionError(기대 11, 실제 10) 발생 확인 → PASS
    with pytest.raises(AssertionError) as exc:
        await assert_stock(api, normal_product, NORMAL_STOCK + 1)
    assert_message_contains(exc, "기대 11", "실제 10")


@pytest.mark.negative
async def test_c40_negative_wrong_status_is_caught(api):
    # 케이스ID 40 | (네거티브) 기대 상태 코드가 틀리면 상태 검증이 실패로 잡힌다. 실패가 확인되면 PASS [검증 헬퍼]
    # flow: 없는 상품 조회(실제 404)에 대해 200을 기대 → AssertionError(기대 200, 실제 404) 발생 확인 → PASS
    resp = await api.get_stock(UNKNOWN)
    with pytest.raises(AssertionError) as exc:
        assert_status(resp, 200)
    assert_message_contains(exc, "기대 200", "실제 404")


@pytest.mark.negative
async def test_c41_negative_oversell_is_caught():
    # 케이스ID 41 | (네거티브) 마지막 1개에 둘 다 성공(과판매)하면 동시성 검증이 실패로 잡힌다. 실패가 확인되면 PASS [검증 헬퍼]
    # flow: 둘 다 201인 가짜 응답 2개를 만들어 검증 → AssertionError(기대 [201, 409], 실제 [201, 201]) 발생 확인 → PASS
    sold = {"orderId": "ORD-0001", "status": "PAID", "productId": LAST, "quantity": 1, "remainingStock": 0}
    both_paid = [httpx.Response(201, json=sold), httpx.Response(201, json={**sold, "orderId": "ORD-0002"})]
    with pytest.raises(AssertionError) as exc:
        assert_one_winner(both_paid, LAST)
    assert_message_contains(exc, "[201, 409]", "[201, 201]")


@pytest.mark.negative
async def test_c42_negative_not_sold_out_is_caught(api, normal_product):
    # 케이스ID 42 | (네거티브) 품절이 아닌 상품을 품절로 기대하면 품절 검증이 실패로 잡힌다. 실패가 확인되면 PASS [검증 헬퍼]
    # flow: 재고 10개 상품 조회 결과에 품절 검증 적용 → AssertionError(soldOut False) 발생 확인 → PASS
    resp = await api.get_stock(normal_product)
    with pytest.raises(AssertionError) as exc:
        assert_sold_out_view(resp, NORMAL)
    assert_message_contains(exc, "soldOut")

