"""B마트 재고 API 테스트 서버 (Flask).

재고의 기준은 JSON 파일(JsonDb) 하나다. 주문마다 JSON의 현재 재고를 읽어 판단한다:
0이면 SOLD_OUT, 부족하면 INSUFFICIENT_STOCK, 충분하면 차감 후 저장.
읽기→판단→쓰기를 락 하나로 묶어 동시 호출도 현재 재고 기준 선착순으로 처리한다.
"""
import threading

from flask import Flask, jsonify, request
from werkzeug.serving import make_server

from server.db import JsonDb


def _is_int(value):
    """bool은 제외한 순수 정수인지 확인한다 (True가 1로 통과되는 것을 막음)."""
    return isinstance(value, int) and not isinstance(value, bool)


def create_app():
    """Flask 앱을 만든다. 재고 JSON(JsonDb)과 읽기→판단→쓰기를 묶는 락을 앱마다 하나씩 가진다."""
    app = Flask(__name__)
    db = JsonDb()
    lock = threading.Lock()

    def err(status, code, message):
        """공통 에러 바디 {"code", "message"}와 상태 코드를 만든다."""
        return jsonify({"code": code, "message": message}), status

    def stock_body(p):
        """상품 레코드를 재고 조회 응답(soldOut/orderable 포함)으로 변환한다."""
        return {"productId": p["productId"], "name": p["name"], "stock": p["stock"],
                "soldOut": p["stock"] == 0, "orderable": p["stock"] > 0}

    @app.get("/v1/products/<pid>/stock")
    def get_stock(pid):
        """GET /v1/products/<pid>/stock: JSON의 현재 재고를 그대로 조회한다. 없는 상품은 404."""
        product = db.load()["products"].get(pid)
        if not product:
            return err(404, "PRODUCT_NOT_FOUND", "존재하지 않는 상품")
        return jsonify(stock_body(product)), 200

    @app.post("/v1/orders")
    def create_order():
        """POST /v1/orders: 수량 검증 → (락) 재고 확인 → 차감·저장. 0이면 SOLD_OUT, 부족하면 INSUFFICIENT_STOCK."""
        body = request.get_json(silent=True) or {}
        pid, qty = body.get("productId"), body.get("quantity")
        if not _is_int(qty) or qty < 1:
            return err(400, "INVALID_QUANTITY", "수량은 1 이상 정수")
        with lock:
            data = db.load()
            product = data["products"].get(pid)
            if not product:
                return err(404, "PRODUCT_NOT_FOUND", "존재하지 않는 상품")
            have = product["stock"]
            if have == 0:
                return err(409, "SOLD_OUT", "품절")
            if have < qty:
                return err(409, "INSUFFICIENT_STOCK", f"재고 부족(잔여 {have})")
            product["stock"] = have - qty
            data["seq"] += 1
            oid = f"ORD-{data['seq']:04d}"
            data["orders"][oid] = {"productId": pid, "quantity": qty,
                                   "customerId": body.get("customerId"), "status": "PAID"}
            db.save(data)
            return jsonify({"orderId": oid, "status": "PAID", "productId": pid,
                            "quantity": qty, "remainingStock": product["stock"]}), 201

    @app.post("/v1/orders/<oid>/cancel")
    def cancel_order(oid):
        """POST /v1/orders/<oid>/cancel: 주문을 취소 상태로 바꾸고 재고를 복구한다. 이미 취소됐으면 409."""
        with lock:
            data = db.load()
            order = data["orders"].get(oid)
            if not order:
                return err(404, "ORDER_NOT_FOUND", "존재하지 않는 주문")
            if order["status"] == "CANCELED":
                return err(409, "ALREADY_CANCELED", "이미 취소된 주문")
            order["status"] = "CANCELED"
            product = data["products"][order["productId"]]
            product["stock"] += order["quantity"]
            db.save(data)
            return jsonify({"orderId": oid, "status": "CANCELED", "restoredStock": product["stock"]}), 200

    @app.put("/v1/admin/products/<pid>/stock")
    def admin_set_stock(pid):
        """운영자 재고 수동 수정: 입력값으로 즉시 반영."""
        value = (request.get_json(silent=True) or {}).get("stock")
        with lock:
            data = db.load()
            product = data["products"].get(pid)
            if not product:
                return err(404, "PRODUCT_NOT_FOUND", "존재하지 않는 상품")
            if not _is_int(value) or value < 0:
                return err(400, "INVALID_STOCK", "재고는 0 이상 정수")
            product["stock"] = value
            db.save(data)
            return jsonify(stock_body(product)), 200

    return app


class ServerThread(threading.Thread):
    """러너가 테스트 동안 임의 포트로 띄우는 서버 스레드."""

    def __init__(self):
        """임의 포트(0)에 바인딩한 서버를 만든다. 실제 포트는 base_url로 노출된다."""
        super().__init__(daemon=True)
        self._srv = make_server("127.0.0.1", 0, create_app(), threaded=True)
        self.base_url = f"http://127.0.0.1:{self._srv.server_port}"

    def run(self):
        """스레드 본체: 서버가 종료될 때까지 요청을 처리한다."""
        self._srv.serve_forever()

    def stop(self):
        """서버를 종료한다."""
        self._srv.shutdown()
