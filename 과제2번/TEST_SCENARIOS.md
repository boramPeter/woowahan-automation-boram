# 테스트 시나리오

시나리오 번호 = 케이스 ID = 테스트 함수 접두사(`test_cNN_` 또는 `cNN_`). 시나리오 N번은 자동화 함수 1개(또는 파라미터 1건)로 구현되어 있고, `uv run python runner.py --case N`으로 한 건만 실행할 수 있다.

## 1. 문제 요구사항별 커버리지

재고 처리 규칙(문제 원문의 규칙 표)을 R번호로 나누고, 각 규칙을 어떤 시나리오가 검증하는지 정리했다.

| 규칙 | 요구사항 | 커버하는 시나리오 |
|---|---|---|
| R1 | 장바구니 담기 = 조회만, 재고 차감 없음 | 10, 11 |
| R2 | 주문 결제 완료 시 수량만큼 즉시 차감 | 2, 12, 13 |
| R3 | 동시 주문 충돌 시 선착순, 이후 요청은 품절 | 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 37, 38 |
| R4 | 주문 취소 시 재고 즉시 복구, 복구 후 즉시 구매 가능 | 14, 15, 19, 37 |
| R5 | 재고 0이면 품절 전환 (배지·주문 버튼 비활성화 근거) | 16, 17, 18, 19, 21, 32 |
| R6 | 운영자 수동 수정은 입력값으로 즉시 반영 | 9, 20, 21, 33, 34, 35, 36 |
| R7 | 수정 중 주문 발생 시 처리 순서 (정의 필요 → 서버 락으로 도착 순서대로 직렬 처리) | 34, 35, 36 |
| R0 | 입력·에러 응답 (잘못된 수량, 없는 상품/주문) | 1, 3, 4, 5, 6, 7, 8 |
| (R5·R6 보강) | 다른 탭에서 조회 중인 고객에게도 즉시 반영 | 32, 33 |

문제의 "요구사항" 항목:

| 요구사항 | 충족 방법 |
|---|---|
| 정상 케이스, 재고 복구, 품절 전환을 포함한 테스트 10개 이상 | 총 42건 (네거티브 4건 포함) (정상 10, 11, 12, 13, 20, 재고 복구 14, 15, 19, 37, 품절 전환 16, 17, 18, 19, 21, 32) |
| 재고 1개 상품에 두 요청이 수십 ms 간격으로 도달하는 동시성 테스트 (병렬 요청 → 1건 성공/1건 품절) | 시나리오 22~29 (간격 0~1000ms), 30(10명), 31(선착순), 36~38(수정·취소·복수 수량 동시) |
| 검증 헬퍼가 틀린 값을 실제로 잡아내는지 (네거티브) | 시나리오 39~42 (에러가 나와야 PASS, 전체 실행에 포함, `-m negative`로 단독 실행) |
| 실제 서버가 없으므로 Mock/스텁 서버로 실행 가능한 상태 | `server/`(Flask) + `runner.py`가 서버 기동 → 테스트 → 종료 |
| README에 fixture, 데이터 준비, 검증 헬퍼 설명 | `README.md`의 "테스트 구조" 참고 |

## 2. 시나리오 목록

| 시나리오 | 영역 | 검증 내용 | 절차 → 기대 결과 | 커버하는 요구사항 | 자동화 함수 |
|---|---|---|---|---|---|
| 1 | 재고 조회 | 없는 상품을 조회하면 404 | 존재하지 않는 상품 조회 → 404 PRODUCT_NOT_FOUND | R0 입력·에러 | `test_stock_api.py::test_error_response[c01_view_unknown_product]` |
| 2 | 주문 | 재고보다 많이 주문하면 거절되고 재고는 그대로다 | 재고(10)보다 많은 11개 주문 → 409 INSUFFICIENT_STOCK → 재고 10 유지 | R2 즉시 차감 | `test_stock_api.py::test_error_response[c02_order_over_stock]` |
| 3 | 주문 | 수량 0은 잘못된 요청이다 | 수량 0 주문 → 400 INVALID_QUANTITY → 재고 10 유지 | R0 입력·에러 | `test_stock_api.py::test_error_response[c03_order_qty_zero]` |
| 4 | 주문 | 음수 수량은 잘못된 요청이다 | 수량 -1 주문 → 400 INVALID_QUANTITY → 재고 10 유지 | R0 입력·에러 | `test_stock_api.py::test_error_response[c04_order_qty_negative]` |
| 5 | 주문 | 문자열 수량은 잘못된 요청이다 | 수량 "2"(문자열) 주문 → 400 INVALID_QUANTITY → 재고 10 유지 | R0 입력·에러 | `test_stock_api.py::test_error_response[c05_order_qty_string]` |
| 6 | 주문 | 수량이 없으면 잘못된 요청이다 | 수량 null 주문 → 400 INVALID_QUANTITY → 재고 10 유지 | R0 입력·에러 | `test_stock_api.py::test_error_response[c06_order_qty_missing]` |
| 7 | 주문 | 없는 상품을 주문하면 404 | 존재하지 않는 상품 주문 → 404 PRODUCT_NOT_FOUND | R0 입력·에러 | `test_stock_api.py::test_error_response[c07_order_unknown_product]` |
| 8 | 취소 | 없는 주문을 취소하면 404 | 존재하지 않는 주문번호 취소 → 404 ORDER_NOT_FOUND | R0 입력·에러 | `test_stock_api.py::test_error_response[c08_cancel_unknown_order]` |
| 9 | 운영자 수정 | 음수 재고는 입력할 수 없다 | 재고를 -1로 수정 → 400 INVALID_STOCK → 재고 10 유지 | R6 운영자 수정 | `test_stock_api.py::test_error_response[c09_admin_edit_negative]` |
| 10 | 재고 조회 | 존재하는 상품의 재고 조회 응답이 스펙의 필드를 모두 갖는다 | 재고 10개 상품 조회 → 200 + productId/name/stock/soldOut/orderable 일치 | R1 조회만 | `test_stock_api.py::test_c10_view_all_fields` |
| 11 | 재고 조회 | 장바구니 담기(=조회)를 반복해도 재고가 차감되지 않는다 | 재고 조회 3회 반복 → 재고 조회 → 여전히 10 | R1 조회만 | `test_stock_api.py::test_c11_view_repeat_no_deduct` |
| 12 | 주문 | 1개 주문하면 재고가 1 줄어든다 | 1개 주문 → 201 PAID + remainingStock 9 → 재고 조회 9 | R2 즉시 차감 | `test_stock_api.py::test_c12_order_one_deducts` |
| 13 | 주문 | 3개 주문하면 주문 수량만큼 한 번에 차감된다 | 3개 주문 → 201 PAID + remainingStock 7 → 재고 조회 7 | R2 즉시 차감 | `test_stock_api.py::test_c13_order_three_deducts` |
| 14 | 취소 | 취소하면 차감됐던 재고가 즉시 복구된다 | (준비: 2개 결제 완료) 재고 8 확인 → 취소 → 200 CANCELED + restoredStock 10 → 재고 조회 10 | R4 즉시 복구 | `test_stock_api.py::test_c14_cancel_restores_stock` |
| 15 | 취소 | 같은 주문을 두 번 취소해도 재고가 두 번 복구되지 않는다 | (준비: 2개 결제 완료) 취소 200 → 같은 주문 재취소 → 409 ALREADY_CANCELED → 재고 10(12가 되면 안 됨) | R4 즉시 복구 | `test_stock_api.py::test_c15_cancel_twice` |
| 16 | 품절 | 마지막 1개가 팔려 재고가 0이 되면 품절 상태로 바뀐다 | 마지막 1개 주문 201 → 재고 조회 → stock 0 / soldOut true / orderable false | R5 품절 전환 | `test_stock_api.py::test_c16_last_item_sold_out` |
| 17 | 품절 | 품절된 상품은 주문할 수 없고 재고는 음수가 되지 않는다 | (준비: cust-1이 마지막 1개 결제) 다른 고객이 주문 → 409 SOLD_OUT → 재고 0 유지 | R5 품절 전환 | `test_stock_api.py::test_c17_order_on_sold_out` |
| 18 | 품절 | 처음부터 재고 0인 상품은 품절 표시 + 주문 불가다 | 재고 0 상품 조회 → 품절 상태 확인 → 주문 → 409 SOLD_OUT | R5 품절 전환 | `test_stock_api.py::test_c18_seed_sold_out_product` |
| 19 | 품절 | 품절 후 취소로 재고가 복구되면 다른 고객이 즉시 구매할 수 있다 | (준비: cust-1이 마지막 1개 결제) 품절 확인 → 취소 → 구매 가능 상태 확인 → cust-2 주문 201 | R4 즉시 복구; R5 품절 전환 | `test_stock_api.py::test_c19_cancel_reopens_sale` |
| 20 | 운영자 수정 | 운영자가 입력한 재고가 즉시 반영된다 | 재고를 25로 수정 → 200 + 수정값 응답 → 재고 조회 25 | R6 운영자 수정 | `test_stock_api.py::test_c20_admin_edit_applied` |
| 21 | 운영자 수정 | 운영자가 재고를 0으로 수정하면 품절 처리되고 주문이 막힌다 | 재고를 0으로 수정 → 조회 시 품절 상태 → 주문 → 409 SOLD_OUT | R6 운영자 수정; R5 품절 전환 | `test_stock_api.py::test_c21_admin_edit_zero` |
| 22 | 동시성 | A, B가 0ms 간격으로 결제 | 재고 1 확인 → A 발사 → 0ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답 | R3 선착순 | `test_stock_api.py::test_race_one_winner[c22_race_gap_0ms]` |
| 23 | 동시성 | A, B가 5ms 간격으로 결제 | 재고 1 확인 → A 발사 → 5ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답 | R3 선착순 | `test_stock_api.py::test_race_one_winner[c23_race_gap_5ms]` |
| 24 | 동시성 | A, B가 10ms 간격으로 결제 | 재고 1 확인 → A 발사 → 10ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답 | R3 선착순 | `test_stock_api.py::test_race_one_winner[c24_race_gap_10ms]` |
| 25 | 동시성 | A, B가 20ms 간격으로 결제 | 재고 1 확인 → A 발사 → 20ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답 | R3 선착순 | `test_stock_api.py::test_race_one_winner[c25_race_gap_20ms]` |
| 26 | 동시성 | A, B가 50ms 간격으로 결제 | 재고 1 확인 → A 발사 → 50ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답 | R3 선착순 | `test_stock_api.py::test_race_one_winner[c26_race_gap_50ms]` |
| 27 | 동시성 | A, B가 100ms 간격으로 결제 | 재고 1 확인 → A 발사 → 100ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답 | R3 선착순 | `test_stock_api.py::test_race_one_winner[c27_race_gap_100ms]` |
| 28 | 동시성 | A, B가 500ms 간격으로 결제 | 재고 1 확인 → A 발사 → 500ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답 | R3 선착순 | `test_stock_api.py::test_race_one_winner[c28_race_gap_500ms]` |
| 29 | 동시성 | A, B가 1000ms 간격으로 결제 | 재고 1 확인 → A 발사 → 1000ms 뒤 B 발사(실제 발사 간격 확인) → 응답 {201(remainingStock 0), 409 SOLD_OUT} → 재고 0 + 품절 응답 | R3 선착순 | `test_stock_api.py::test_race_one_winner[c29_race_gap_1000ms]` |
| 30 | 동시성 | 10명이 5ms 간격으로 연달아 결제 | 재고 1 확인 → 10명이 5ms 간격으로 주문 → 201 1건(remainingStock 0) + 409 SOLD_OUT 9건 → 재고 0 + 품절 응답 | R3 선착순 | `test_stock_api.py::test_race_one_winner[c30_race_burst_10]` |
| 31 | 동시성 | 먼저 도달한 요청이 선착순으로 성공하고 나중 요청은 품절이다 | 재고 1 확인 → A 발사 → 30ms 뒤 B 발사 → A 201(remainingStock 0) / B 409 SOLD_OUT → 재고 0 + 품절 응답 | R3 선착순 | `test_stock_api.py::test_c31_race_first_arrival_wins` |
| 32 | 품절 | 한 탭에서 마지막 1개를 주문하면 다른 탭에서 조회한 화면도 바로 품절이다 | 다른 탭이 재고 1 조회(구매 가능) → 이 탭이 마지막 1개 주문 → 다른 탭이 다시 조회 → 즉시 stock 0 / soldOut true | R5 품절 전환; 다른 탭 즉시 반영 | `test_stock_api.py::test_c32_other_tab_sees_sold_out` |
| 33 | 운영자 수정 | 운영자가 재고를 수정하면 다른 탭에서 조회한 재고도 바로 바뀐다 | 다른 탭이 재고 10 조회 → 운영자가 25로 수정 → 다른 탭이 다시 조회 → 즉시 25 | R6 운영자 수정; 다른 탭 즉시 반영 | `test_stock_api.py::test_c33_other_tab_sees_admin_edit` |
| 34 | 운영자 수정 | 운영자 수정이 먼저 처리되면 이후 주문은 수정된 재고를 기준으로 차감된다 | 운영자가 재고를 5로 수정 → 3개 주문 → 201 + remainingStock 2 → 재고 조회 2 | R6 운영자 수정; R7 수정 중 주문 | `test_stock_api.py::test_c34_order_after_admin_edit_uses_new_stock` |
| 35 | 운영자 수정 | 주문이 먼저 처리되고 뒤에 운영자 수정이 오면 수정값이 최종 재고가 된다 | 마지막 1개 주문 → remainingStock 0 → 운영자가 5로 수정 → 재고 조회 5(품절 해제) | R6 운영자 수정; R7 수정 중 주문 | `test_stock_api.py::test_c35_admin_edit_after_order_overwrites` |
| 36 | 동시성 | 운영자 수정과 주문이 동시에 와도 결과는 한쪽이 먼저 처리된 직렬 결과와 같다 | 재고 1에서 주문 1개와 운영자 5 수정을 동시에 발사 → 주문 201 → (remainingStock, 최종 재고)가 (0, 5) 또는 (4, 4) | R6 운영자 수정; R7 수정 중 주문 | `test_stock_api.py::test_c36_order_and_admin_edit_at_once` |
| 37 | 동시성 | 품절 상태에서 취소와 다른 고객의 주문이 동시에 와도 재고가 어긋나지 않는다 | (준비: cust-1이 마지막 1개 결제) 취소와 cust-2 주문을 동시에 발사 → (주문 결과, 최종 재고)가 (201, 0) 또는 (409, 1) | R3 선착순; R4 즉시 복구 | `test_stock_api.py::test_c37_cancel_and_order_at_once` |
| 38 | 동시성 | 재고 10개에 6개씩 동시에 주문하면 한 명만 성공하고 다른 한 명은 재고 부족이다 | A, B가 6개씩 동시에 주문 → 201 1건(remainingStock 4) + 409 INSUFFICIENT_STOCK 1건 → 재고 4 | R3 선착순 | `test_stock_api.py::test_c38_two_big_orders_at_once` |
| 39 | 네거티브 | (네거티브) 기대 재고가 틀리면 재고 검증이 실패로 잡힌다. 실패가 확인되면 PASS | 재고 10개 상품에서 기대 재고를 11로 잘못 지정 → AssertionError(기대 11, 실제 10) 발생 확인 → PASS | 검증 헬퍼 자체 검증 (틀린 값을 실제로 잡아내는지) | `test_stock_api.py::test_c39_negative_wrong_stock_is_caught` |
| 40 | 네거티브 | (네거티브) 기대 상태 코드가 틀리면 상태 검증이 실패로 잡힌다. 실패가 확인되면 PASS | 없는 상품 조회(실제 404)에 대해 200을 기대 → AssertionError(기대 200, 실제 404) 발생 확인 → PASS | 검증 헬퍼 자체 검증 (틀린 값을 실제로 잡아내는지) | `test_stock_api.py::test_c40_negative_wrong_status_is_caught` |
| 41 | 네거티브 | (네거티브) 마지막 1개에 둘 다 성공(과판매)하면 동시성 검증이 실패로 잡힌다. 실패가 확인되면 PASS | 둘 다 201인 가짜 응답 2개를 만들어 검증 → AssertionError(기대 [201, 409], 실제 [201, 201]) 발생 확인 → PASS | 검증 헬퍼 자체 검증 (틀린 값을 실제로 잡아내는지) | `test_stock_api.py::test_c41_negative_oversell_is_caught` |
| 42 | 네거티브 | (네거티브) 품절이 아닌 상품을 품절로 기대하면 품절 검증이 실패로 잡힌다. 실패가 확인되면 PASS | 재고 10개 상품 조회 결과에 품절 검증 적용 → AssertionError(soldOut False) 발생 확인 → PASS | 검증 헬퍼 자체 검증 (틀린 값을 실제로 잡아내는지) | `test_stock_api.py::test_c42_negative_not_sold_out_is_caught` |
