# B마트 재고 API 응답 스펙

API가 내려주는 response(HTTP 상태 코드 + JSON 바디)만 정리한 문서입니다.

## 공통

### 에러 응답
모든 에러는 같은 바디 구조를 씁니다. `message`는 사람이 읽는 문구라 테스트는 `code`만 검증합니다.
```json
{"code": "PRODUCT_NOT_FOUND", "message": "존재하지 않는 상품"}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `code` | string | 에러 식별자 (아래 엔드포인트별 표 참고) |
| `message` | string | 사람용 설명 |

### 재고 상태 객체
재고 조회와 운영자 수정 응답이 같은 구조를 씁니다.

| 필드 | 타입 | 규칙 |
|---|---|---|
| `productId` | string | 상품 ID |
| `name` | string | 상품명 |
| `stock` | int | 현재 재고. 0 이상이며 음수가 나오면 결함(과판매) |
| `soldOut` | bool | `stock == 0` |
| `orderable` | bool | `stock > 0` (항상 `soldOut`의 반대) |

---

## GET /v1/products/{productId}/stock

| 상태 | 조건 | 바디 |
|---|---|---|
| 200 | 상품이 존재 | 재고 상태 객체 |
| 404 | 없는 상품 | `PRODUCT_NOT_FOUND` |

**200 — 재고 있음**
```json
{"productId": "100230451", "name": "국산 생수 2L 6입", "stock": 10, "soldOut": false, "orderable": true}
```

**200 — 재고 0**
```json
{"productId": "100455890", "name": "품절 상품 샘플", "stock": 0, "soldOut": true, "orderable": false}
```

**404**
```json
{"code": "PRODUCT_NOT_FOUND", "message": "존재하지 않는 상품"}
```

---

## POST /v1/orders

| 상태 | 조건 | 바디 |
|---|---|---|
| 201 | 주문 성공 (재고 즉시 차감) | 주문 객체 |
| 400 | 수량이 1 이상 정수가 아님 (0, 음수, 문자열, 누락) | `INVALID_QUANTITY` |
| 404 | 없는 상품 | `PRODUCT_NOT_FOUND` |
| 409 | 재고 0 | `SOLD_OUT` |
| 409 | 0 < 재고 < 주문 수량 | `INSUFFICIENT_STOCK` |

주문 객체

| 필드 | 타입 | 규칙 |
|---|---|---|
| `orderId` | string | `ORD-` + 4자리 순번 |
| `status` | string | `PAID` |
| `productId` | string | 주문한 상품 |
| `quantity` | int | 주문 수량 |
| `remainingStock` | int | 차감 직후 재고 (이후 조회 값과 같아야 함) |

**201**
```json
{"orderId": "ORD-0001", "status": "PAID", "productId": "100230451", "quantity": 3, "remainingStock": 7}
```

**400**
```json
{"code": "INVALID_QUANTITY", "message": "수량은 1 이상 정수"}
```

**404**
```json
{"code": "PRODUCT_NOT_FOUND", "message": "존재하지 않는 상품"}
```

**409 — 재고 0**
```json
{"code": "SOLD_OUT", "message": "품절"}
```

**409 — 재고 부족**
```json
{"code": "INSUFFICIENT_STOCK", "message": "재고 부족(잔여 10)"}
```

---

## POST /v1/orders/{orderId}/cancel

| 상태 | 조건 | 바디 |
|---|---|---|
| 200 | 취소 성공 (재고 즉시 복구) | 취소 객체 |
| 404 | 없는 주문 | `ORDER_NOT_FOUND` |
| 409 | 이미 취소된 주문 | `ALREADY_CANCELED` |

취소 객체

| 필드 | 타입 | 규칙 |
|---|---|---|
| `orderId` | string | 취소한 주문 |
| `status` | string | `CANCELED` |
| `restoredStock` | int | 복구 직후 재고 (이후 조회 값과 같아야 함) |

**200**
```json
{"orderId": "ORD-0001", "status": "CANCELED", "restoredStock": 10}
```

**404**
```json
{"code": "ORDER_NOT_FOUND", "message": "존재하지 않는 주문"}
```

**409**
```json
{"code": "ALREADY_CANCELED", "message": "이미 취소된 주문"}
```

---

## PUT /v1/admin/products/{productId}/stock (운영자 재고 수정)

| 상태 | 조건 | 바디 |
|---|---|---|
| 200 | 수정 성공 (입력값으로 즉시 반영) | 재고 상태 객체 |
| 400 | 재고가 0 이상 정수가 아님 | `INVALID_STOCK` |
| 404 | 없는 상품 | `PRODUCT_NOT_FOUND` |

**200**
```json
{"productId": "100230451", "name": "국산 생수 2L 6입", "stock": 25, "soldOut": false, "orderable": true}
```

**400**
```json
{"code": "INVALID_STOCK", "message": "재고는 0 이상 정수"}
```

**404**
```json
{"code": "PRODUCT_NOT_FOUND", "message": "존재하지 않는 상품"}
```

---

## 에러 코드 모음
| code | 상태 | 발생 API |
|---|---|---|
| `PRODUCT_NOT_FOUND` | 404 | 재고 조회, 주문, 운영자 수정 |
| `INVALID_QUANTITY` | 400 | 주문 |
| `SOLD_OUT` | 409 | 주문 |
| `INSUFFICIENT_STOCK` | 409 | 주문 |
| `ORDER_NOT_FOUND` | 404 | 취소 |
| `ALREADY_CANCELED` | 409 | 취소 |
| `INVALID_STOCK` | 400 | 운영자 수정 |
