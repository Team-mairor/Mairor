# 레퍼런스 프레임 전달 요청

- 작성: 김현수
- 받는 사람: 김정윤
- 날짜: 2026-10-28
- 기한: 2026-11-01
- 관련 Jira: S15P31A306-215, S15P31A306-216
- 관련 문서: [2026-10-26 ADR-008·010 수정안](https://app.notion.com/p/405dce3252f681468be0f0d89ee6ce0e)의 `frames[]`, [미리보기 입력·적용 데이터 규격](https://app.notion.com/p/401dce3252f681c186c7c3e3d67e421c) 3.1·3.2

## 요청 배경

AI는 레퍼런스 영상의 사진에서 얼굴 점을 찾고(S15P31A306-215), 단계 직전·직후 사진을 비교해 단계마다 바를 영역을 찾습니다.
가이드 입력(`shared/guide-input`)의 대표 사진은 단계마다 1~3장이고 단계 구간 안이어야 해서, 아래 일을 할 수 없습니다.

- 첫 단계 전 맨얼굴과 단계 직전·직후 사진은 단계 구간 밖이라 받을 수 없습니다
- 여러 장 중에서 손이 가리지 않은 좋은 장면을 고를 수 없습니다

그래서 가이드 입력과 별도로 영상 전체의 프레임 목록이 필요합니다. 10-21과 10-27에 메신저로 요청드린 내용을 한 문서로 정리해 다시 올립니다 (10-27에 해 주신다고 답 주셨습니다).

## 요청 내용

### 1. 어떤 사진

- [ ] 영상 전체에서 캡처해 주세요. 첫 단계 전 맨얼굴 구간도 포함해 주세요
- [ ] 간격: 기본 초당 2장, 단계 시작·끝 앞뒤 3초는 초당 10장 (영상 1: 8분 45초, 단계 19개 기준 약 2,000장)
- [ ] 원본 해상도 그대로 (최소 720p, 가능하면 1080p), 자르거나 줄이지 않기
- [ ] 밝기·필터·색 보정 없이, JPEG 품질 95 이상 또는 PNG

### 2. 같이 보내 주실 칸

| 칸 | 타입 | 설명 |
| --- | --- | --- |
| `source.width` · `source.height` | integer | 원본 영상 크기 |
| `source.fps` | number | 원본 영상 fps. 영상 길이는 가이드 입력의 `durationSeconds`를 씁니다 |
| `frames[].frameIndex` | integer | 원본 영상의 몇 번째 프레임인지 (캡처 시각(초) × fps 반올림) |
| `frames[].timestampMs` | integer | 영상 시각 (ms) |
| `frames[].stepId` | string \| null | 그 시각이 속한 단계. 맨얼굴·단계 사이는 `null` |
| `frames[].url` | string | 이미지 주소 |
| `frames[].width` · `frames[].height` | integer | 이미지 크기 |

### 3. 예시

가이드 입력과 같은 JSON에 싣는 경우입니다. `steps`는 가이드 입력 그대로라 줄였습니다.

```json
{
  "videoId": "eFzG30avtOI",
  "durationSeconds": 525,
  "source": { "width": 1920, "height": 1080, "fps": 30 },
  "steps": [],
  "frames": [
    { "frameIndex": 0, "timestampMs": 0, "stepId": null, "url": "https://storage.example.com/frames/000000.jpg", "width": 1920, "height": 1080 },
    { "frameIndex": 9180, "timestampMs": 306000, "stepId": "s10", "url": "https://storage.example.com/frames/009180.jpg", "width": 1920, "height": 1080 }
  ]
}
```

## 확인 부탁드릴 것

- [ ] 이미지 URL이 만료되는지, 된다면 얼마 뒤인지 (AI는 분석을 시작할 때 내려받습니다)
- [ ] 가이드 입력과 같은 JSON에 실어 주실 수 있는지 (위 예시처럼)
- [ ] 제안한 간격이 저장 공간상 괜찮은지 (참고: AI 로컬 시험용 PNG는 1장에 약 1.9MB)
- [ ] 영상·프레임 보관 기간
- [ ] `videoId`와 시작·끝 시각으로 프레임 목록을 조회할 수 있는지
