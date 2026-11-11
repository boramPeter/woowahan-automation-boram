# 프롬프트

단계마다 파일이 하나씩 있고, 파일 내용이 그대로 시스템 프롬프트가 됩니다. 고칠 때는 이 폴더의 `.md`만 바꾸면 됩니다.

| 파일 | 상수 | 단계 | 입력 (JSON) | 출력 (JSON) |
|---|---|---|---|---|
| `tree.md` | `TREE_SYSTEM` | ① 트리 생성 | `spec`, (다시 만들 때) `previous`, `revise_feedback` | 노드마다 `quote`가 있는 트리 |
| `tree_check.md` | `TREE_CHECK_SYSTEM` | ② 트리 검사 (누락 판단) | `tree`(줄마다 "이름 \| 인용"), `sentences`(어느 노드에도 안 걸린 기획서 문장) | `verdicts`: 문장마다 `index`, `verdict`(누락/포함됨/기능 아님), `reason` |
| `requirements.md` | `REQ_SYSTEM` | ③ TC 생성: leaf별 요구사항 | `spec`, `leaf`, (다시 만들 때) `previous`, `revise_feedback` | `status`(정의됨/공백), `acs`, `hints`, `priority` |
| `plan.md` | `PLAN_SYSTEM` | ③ TC 생성: 계획 | `requirement` | `outline`, `excluded` |
| `write.md` | `WRITE_SYSTEM` | ③ TC 생성: 작성, 다시 쓰기 | `path`, `source`, `outline`, (다시 쓸 때) `previous`, `revise_feedback` | `precondition`, `steps`, `expected` |
| `judge.md` | `JUDGE_SYSTEM` | ④ TC 검사 | `source`, `test_case` | `correctness`, `completeness`, `clarity` 각각 PASS/FAIL |

입력은 `user` 메시지에 JSON 문자열로 넘기고, 출력은 JSON 하나로 받습니다. 입출력 필드 이름은 코드가 그대로 읽는 키라서, 프롬프트의 출력 형식을 바꾸면 해당 단계 코드(`tree.py`, `tree_check.py`, `tc.py`, `tc_check.py`)도 같이 바꿔야 합니다.

## 공통 원칙

1. TC 개수는 우선순위가 아니라 "확인할 게 몇 개인지"로 정합니다. 개수를 정해 주면 억지로 TC를 채웁니다.
2. TC 하나에는 확인할 것 하나만 둡니다. 값이 여러 개인 조건은 값마다 TC를 나눕니다.
3. 원문에 없는 동작과 수치는 쓰지 않습니다. 환각은 대개 기대결과에 들어간 "그럴듯한 값"으로 나타납니다.
4. 만들지 않은 시나리오는 이유를 남깁니다. 빠뜨린 것과 일부러 뺀 것을 구분하려는 겁니다.
5. 트리의 모든 노드는 기획서 원문 인용을 갖습니다. 지어낸 기능은 인용 대조에서 걸립니다.
6. 기획서에 동작이 없는 기능은 채우지 않고 "공백"으로 올립니다. 추측으로 AC를 만들지 않습니다.
7. 누락 판단은 문장에 적힌 내용만 근거로 합니다. 기획서에 없는 기능을 상상해서 누락이라고 하지 않습니다. 다만 어느 노드가 다루는지 확실하지 않으면 누락으로 답합니다.
8. 다시 만들 때는 지적받은 부분만 고치고 나머지는 그대로 둡니다.

## 고친 뒤 확인

```bash
python3 -m unittest discover -s tests
```

테스트는 정해진 답을 주는 가짜 모델로 돌기 때문에, 프롬프트 문구가 더 좋아졌는지는 알려 주지 않습니다. 파일이 있는지, 비어 있지 않은지, 코드가 읽는 출력 필드가 그대로인지, 폴더의 모든 `.md`에 대응하는 상수가 있는지만 확인합니다.
