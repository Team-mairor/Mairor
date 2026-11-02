# guide-input 공유 형식

BE가 AI 서버에 넘기는 가이드 입력(`GuideInput`)의 JSON Schema다. BE와 AI가 **같은 파일**로 입력을 검사한다.
칸 설명과 예시는 [ai/docs/GUIDE_INPUT.md](../../ai/docs/GUIDE_INPUT.md)에 있다.

| 파일 | 내용 | 출처 |
| --- | --- | --- |
| `guide_input.v1.schema.json` | JSON Schema (draft 2020-12) | `ai/app/schemas/guide.py`의 `GuideInput`에서 생성 (`ai/tools/export_guide_schema.py`) |

## 사용 위치

- AI: `ai/tests/test_guide_schema.py`가 이 파일이 모델과 같은지, 샘플(`ai/samples/local_01/guide_input.json`)이 통과하는지 본다.
- BE (예정): 테스트에서 AI 서버로 보낼 JSON을 이 스키마로 검사한다.

## 스키마에 없는 검사

JSON Schema는 칸끼리 비교하지 못한다. 아래는 AI 서버만 검사하고, 어기면 `VALIDATION_FAILED`로 거절한다.

- `endSeconds`가 `startSeconds`보다 큼
- `endSeconds`가 `durationSeconds` 이하
- `stepId` · `order`가 겹치지 않음

스키마에 없는 칸은 막지 않고 AI 서버도 버린다. 11.02에 뺀 `steps[].images`를 BE가 보내도 통과한다.

## 형식을 바꿀 때

1. `ai/app/schemas/guide.py`의 입력 모델을 고친다.
2. `ai/`에서 `uv run python tools/export_guide_schema.py`로 스키마를 다시 만든다. 안 하면 `uv run pytest`가 실패한다.
3. MR 리뷰어에 BE 담당을 넣는다.

BE가 보내던 JSON이 거절되는 변경(칸 삭제·이름 변경, 필수 칸 추가, 범위 좁히기)이면 `export_guide_schema.py`에서 파일 이름의 버전을 올려 새 파일로 만들고, BE가 옮긴 뒤 이전 파일을 지운다.
