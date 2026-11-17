# 화면별 API 대조

화면마다 서버에 필요한 데이터·동작 중 **아직 남은 것**만 API 명세 v2(`docs/references/api-spec.md`)와 BE 구현에 맞춰 적는다. 구현·연결이 끝난 줄은 지운다.

- FE가 BE API를 쓰는 범위는 `frontend/README.md` 규칙 절에 있다(회원·파우치·영상 입력·분석·가이드 실행·리포트)
- 기준 문서는 BE 개발 서버의 Swagger(`/swagger-ui`, `/v3/api-docs`)다. 명세와 다르면 Swagger를 따른다

## 가이드 조회 모의 응답

`NEXT_PUBLIC_API_MOCK=success`로 개발 서버를 띄우면 `GET /v1/guides/{guideId}`가 `mocks/mock-guide-api.ts`의 모의 가이드로 답한다. 목표 색은 실제처럼 null이다.

| guideId                                | 내용                                                                                             |
| -------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `a0000000-0000-4000-8000-000000000001` | 샘플 영상(AI 샘플 local_01). 19단계 중 GUIDE 13단계, 영역은 `fixtures/guide-areas/local_01.json` |
| `a0000000-0000-4000-8000-000000000002` | 화장 종류 9가지를 한 단계씩 (기본 가이드). 샘플 영상에 없는 눈썹까지 확인                        |
| 그 밖의 UUID                           | 404                                                                                              |

## 화면별

| 화면                   | 필요한 것            | 명세 v2       | BE   | 문제·할 일                                                                          |
| ---------------------- | -------------------- | ------------- | ---- | ----------------------------------------------------------------------------------- |
| 01 로그인              | 로그인 기기 관리     | USERS-014~016 | 구현 | 화면 없음                                                                           |
| 02-1 온보딩, 12 파우치 | 제품 대표 색 여러 개 | POUCH-001~008 | 일부 | 응답 `PouchItem`에 명세의 `colors[]`가 BE 코드에 아직 없어 대표 색은 `color`만 쓴다 |

## 명세 문서 자체의 문제

- 개수: "현행 API 44개"인데 표는 46행이다. 신규 API 블록 제목도 11개인데 내용은 14개다
- 같은 개념에 다른 이름: `verificationToken`/`emailVerificationToken`, `enabled`/`photoConsent`, `result`/`matchingResult`, `title`/`videoTitle`, `createdAt`/`requestedAt`, `jobId`/`analysisJobId`
- 공통 규칙과 다른 곳: 생성인데 200(VIDEO-001, GUIDE-005), CSRF 표기가 빠진 변경 요청(CAMERA-001·003, VIDEO-006), 429인데 Retry-After 없음(USERS-009·013 ATTEMPTS_EXCEEDED)

## FE에서 할 일

- 로그인 기기 관리 화면
