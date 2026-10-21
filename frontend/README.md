# Frontend

Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui

## 시작하기

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

http://localhost:3000 에서 확인한다.

- Node 20.9 이상이 필요하다 (`.nvmrc` 기준 24).
- 환경변수는 `.env.local`에 넣는다. 항목은 `.env.example`을 참고하고, `.env.local`은 커밋하지 않는다.

### 폰에서 카메라 테스트

폰 브라우저는 HTTPS 또는 `localhost`가 아니면 카메라 접근을 막는다.

#### 방법 1. USB 연결 (안드로이드, 같은 와이파이가 없을 때)

폰의 `localhost:3000`을 PC 개발 서버로 연결한다. `localhost`라서 HTTP로도 카메라가 동작한다.

1. 폰에서 개발자 옵션 → **USB 디버깅**을 켜고, USB로 PC에 연결한다.
2. [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools)를 받아 압축을 푼다.
3. 개발 서버를 켜고 포트를 연결한다.
   ```bash
   npm run dev
   adb reverse tcp:3000 tcp:3000
   ```
   처음 연결하면 폰에 "USB 디버깅을 허용하시겠습니까?" 창이 뜬다. "이 컴퓨터에서 항상 허용"에 체크하고 허용한다.
4. 폰 **크롬**에서 `localhost:3000`으로 접속한다.
5. PC 크롬 `chrome://inspect/#devices`에서 해당 페이지의 **inspect**를 누르면 폰 화면과 콘솔을 PC에서 볼 수 있다.

케이블을 다시 꽂으면 `adb reverse tcp:3000 tcp:3000`을 다시 실행한다.

#### 방법 2. 같은 와이파이

```bash
npm run dev:https
```

- 폰에서 `https://<PC의 IP>:3000` 으로 접속한다.
- 자체 서명 인증서라서 폰에서 보안 경고가 뜨면 "계속 진행"을 누른다.
- 처음 실행할 때 로컬 인증서가 `certificates/` 폴더에 만들어진다. 이 폴더는 커밋하지 않는다.

## 스크립트

| 명령                   | 설명                                   |
| ---------------------- | -------------------------------------- |
| `npm run dev`          | 개발 서버                              |
| `npm run dev:https`    | HTTPS 개발 서버 (폰 카메라 테스트용)   |
| `npm run build`        | 정적 파일로 빌드 (`out/`)              |
| `npm run preview`      | 빌드 결과(`out/`)를 로컬에서 띄워 보기 |
| `npm run lint`         | ESLint 검사                            |
| `npm run typecheck`    | TypeScript 타입 검사                   |
| `npm run format`       | Prettier로 전체 포맷                   |
| `npm run format:check` | 포맷 검사만                            |

## 폴더 구조

```
src/
├─ app/                    # 페이지 (Next.js 규칙)
│  ├─ layout.tsx           # 전체 공통 레이아웃
│  ├─ page.tsx             # 메인
│  ├─ select/page.tsx      # 영상 선택
│  └─ (camera)/            # 카메라를 쓰는 페이지 묶음
│     ├─ layout.tsx        # 카메라·얼굴 추적을 여기서 한 번만 시작
│     ├─ preview/page.tsx  # 미리보기
│     └─ tutorial/page.tsx # 단계별 튜토리얼
├─ components/ui/          # shadcn/ui 컴포넌트
├─ features/face/          # 카메라·추적·오버레이 ('use client')
└─ lib/                    # 공통 유틸
scripts/
└─ sync-mediapipe-assets.mjs  # MediaPipe wasm·모델을 public/으로 복사
```

## MediaPipe 파일

얼굴 추적(MediaPipe Face Landmarker)은 인터넷 없이도 동작하도록 wasm과 모델 파일을 직접 서빙한다.

| 파일 | 원본                                                   | 서빙 경로                      |
| ---- | ------------------------------------------------------ | ------------------------------ |
| wasm | `node_modules/@mediapipe/tasks-vision/wasm`            | `/mediapipe/wasm/`             |
| 모델 | `../shared/face-mesh/face_landmarker.task` (AI와 공유) | `/models/face_landmarker.task` |

- `npm run dev`, `npm run dev:https`, `npm run build` 전에 자동으로 `public/`에 복사된다. 직접 복사하려면 `npm run sync:mediapipe`.
- `public/mediapipe`, `public/models`는 복사본이라 커밋하지 않는다.
- `@mediapipe/tasks-vision`은 wasm과 버전이 맞아야 해서 정확한 버전으로 고정했다. 올릴 때는 `npm install`만 하면 다음 실행 때 wasm도 같이 바뀐다.

## 규칙

- **정적 내보내기(`output: 'export'`)** 로 배포한다. API 라우트, 서버 액션, 쿠키 등 서버 기능은 쓰지 않는다. API는 BE 서버를 호출한다.
- 카메라·MediaPipe처럼 브라우저에서만 동작하는 코드는 `src/features/face/`에 두고 `'use client'`로 작성한다.
- UI 컴포넌트는 `npx shadcn@latest add <컴포넌트>` 로 추가한다.
- 커밋 전에 `npm run lint`, `npm run typecheck`, `npm run format:check` 를 통과시킨다.
