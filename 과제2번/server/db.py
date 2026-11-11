"""JSON 파일 기반 미니 DB. 초기 데이터(data/products.json)는 건드리지 않고 임시 파일로 복사해 읽고 쓴다."""
import json
import os
import tempfile
from pathlib import Path

SEED = Path(__file__).parent / "data" / "products.json"


class JsonDb:
    """재고·주문을 담는 JSON 파일 DB. 초기 데이터를 임시 파일로 복사해 쓰므로 원본은 바뀌지 않는다."""
    def __init__(self):
        """임시 폴더에 db.json을 만들고 초기 상품 데이터 + 빈 주문 목록으로 채운다."""
        self._tmp = tempfile.TemporaryDirectory(prefix="bmart_db_")  # 객체가 사라지면 같이 삭제
        self.path = Path(self._tmp.name) / "db.json"
        self.save({"products": json.loads(SEED.read_text(encoding="utf-8")), "orders": {}, "seq": 0})

    def load(self):
        """db.json 전체를 읽어 dict로 돌려준다 (호출할 때마다 파일에서 새로 읽음)."""
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data):
        """dict를 db.json에 저장한다. 임시 파일에 쓴 뒤 교체해서 읽는 쪽이 쓰다 만 파일을 보지 않게 한다."""
        tmp = self.path.with_suffix(".tmp")  # 원자적 교체: 락 없는 조회가 쓰다 만 파일을 읽지 않도록
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
