# CI 안내

MR을 올리거나 master에 머지되면 GitLab이 파트별 검사를 자동으로 돌린다. 검사 결과는 MR 화면에 초록(통과) 또는 빨강(실패)으로 표시된다. 검사가 실패한 MR은 master에 머지하지 않는다.

MR 승인·머지 규칙은 노션 [Git Convention](https://app.notion.com/p/3f2dce3252f680fcbd70da68cc09596b)을 따른다.

## 언제 무엇이 도나

파이프라인은 **MR**과 **master**에서만 돈다. 브랜치에 push만 하고 MR이 없으면 돌지 않는다. 각 검사는 자기 폴더가 바뀌었을 때만 돈다. master에서는 검사 뒤에 배포가 이어진다(아래 "배포").

| 바뀐 곳 | 도는 검사 |
|---|---|
| `backend/` | `backend`, `repo-guard` |
| `frontend/` | `frontend`, `repo-guard` |
| `ai/` | `ai`, `repo-guard` |
| `shared/` | `frontend`, `ai`, `repo-guard` |
| `.gitlab-ci.yml`, `ci/` | 전부 |
| 그 밖의 것(문서 등) | `repo-guard`만 |

## 검사 내용 = 로컬에서 돌릴 명령

CI가 실패하면 아래 명령을 자기 PC에서 그대로 돌려 같은 오류를 재현한다.

| 검사 | 파일 | 명령 (해당 폴더에서) | 이미지 |
|---|---|---|---|
| `backend` | `ci/backend.yml` | `./gradlew spotlessCheck test build` (Docker 필요: 테스트가 PostgreSQL을 띄운다) | `eclipse-temurin:21-jdk` |
| `frontend` | `ci/frontend.yml` | `npm ci` → `npm run lint` → `npm run typecheck` → `npm run format:check` → `npm run build` | `node:24` |
| `ai` | `ci/ai.yml` | `uv sync --locked` → `uv run ruff check .` → `uv run pytest` | `uv` + Python 3.12 |
| `repo-guard` | `.gitlab-ci.yml` | 커밋된 `.env`·`*.pem`·`*.key`·`*.keystore`가 있으면 실패(`.env.example`은 허용) | `alpine` |

`repo-guard`가 실패하면 그 파일을 커밋에서 빼고, 안에 있던 키·비밀번호는 이미 GitLab에 올라간 것으로 보고 **폐기·재발급**한다.

## 배포 (master)

master에 머지되면 검사가 끝난 뒤 운영 배포가 이어진다(`ci/deploy.yml`, BE 관리). MR 파이프라인에서는 돌지 않는다.

| 잡 | 하는 일 |
|---|---|
| `build-images` | 이미지 4개(`mairor-nginx` · `mairor-backend` · `mairor-ai` · `mairor-deploy`)를 빌드해 ECR에 올린다. 태그는 커밋 해시 8자리 |
| `deploy` | SSM Run Command로 **AI 서버(`deploy-ai.sh`) → BE 서버(`deploy.sh`)** 순서로 배포한다. BE는 슬롯 a → b → worker 순서라 배포 중에도 사이트가 끊기지 않는다. 실패한 서버는 스스로 이전 버전으로 되돌리고 잡이 빨강이 된다. AI가 실패하면 BE는 건드리지 않고, AI 성공 뒤 BE가 실패하면 AI는 새 버전으로 남는다(함께 되돌리려면 `rollback`) |
| `rollback` (수동) | 두 서버를 같은 순서로 이전 버전으로 되돌린다. 아래 방법 |
| `deploy-infra` | `infra/`가 바뀌었을 때만 돈다. 인프라 서버에 SSH로 `infra/`를 올리고 `infra/deploy.sh`를 돌린다(`ci/infra.yml`, 박형준 관리). 되돌리기는 예전 파이프라인의 이 잡을 다시 실행 |

**되돌리기:** master 파이프라인 화면에서 `rollback` 잡 **이름**을 누른다. 열린 화면의 변수 칸에 키 `ROLLBACK_TAG`, 값에 되돌릴 태그(예전 `deploy` 잡 로그의 `deploy 완료: <태그>`)를 넣고 **Run job**. 두 서버 모두 그 태그로 성공했던 적이 있어야 한다(AI 서버는 `c5b05159`부터). ▶ 버튼을 바로 누르면 변수 없이 돌아 안내만 찍고 실패한다.

- AWS 자격은 CI 변수(`AWS_ACCESS_KEY_ID` · `AWS_SECRET_ACCESS_KEY` · `EC2_INSTANCE_ID`(BE 서버) · `AI_EC2_INSTANCE_ID`(AI 서버), Protected)라 master에서만 보인다. 키 교체와 서버 쪽 절차는 `deploy/README.md`.
- 배포 잡 로그 아래쪽 "서버 오류 출력"에 `credentials are stored unencrypted` 경고가 보여도 정상이다. 성공 · 실패는 마지막 줄 `결과:`로 본다.

## 결과 보는 곳

- MR 화면 → **Pipelines** 탭 → 빨간 잡을 누르면 로그가 나온다.
- 백엔드 테스트 실패는 MR 화면의 **Test summary**에 실패한 테스트 이름이 뜬다. 자세한 리포트는 잡 화면 오른쪽 **Job artifacts**(7일 보관).

## 검사를 바꾸고 싶을 때

- 각 파트는 **자기 `ci/<파트>.yml`만** 고친다. 검사 명령을 더하거나 빼는 것은 그 파트가 정한다.
- MR 리뷰어에 같은 파트 팀원과 함께 BE 1명(CI 담당)을 넣는다. 루트 `.gitlab-ci.yml`과 러너 설정은 BE가 관리한다.
- 이미지 버전은 각 파트의 버전 파일과 맞춘다(BE `build.gradle` toolchain, FE `.nvmrc`, AI `.python-version`).

## 러너

검사는 SSAFY가 제공한 서버 한 대(GitLab 러너)에서 돈다.

- 한 번에 잡 3개까지 동시에 돈다. 잡 하나는 CPU 2개·메모리 4 GB까지 쓴다.
- 잡마다 새 컨테이너에서 돌고 끝나면 지워진다. 의존성(Gradle·npm·uv)은 캐시로 다음 잡에 재사용한다.
- 서버 방화벽은 SSH만 연다. 테스트용 DB 포트는 서버 안쪽(127.0.0.1)에만 열려 외부에서 접근할 수 없다.

### 러너가 멈췄을 때

잡이 오래 **pending**(대기)으로 남아 있으면 러너가 멈춘 것이다.

1. CI 담당(BE)에게 알린다.
2. 급한 MR은 CI 담당이 "파이프라인 성공 후 머지" 설정을 잠시 끄고 팀에 알린다. 그동안 MR 본문에 위 로컬 명령의 결과를 적는다.
3. 러너가 복구되면 설정을 다시 켜고 팀에 알린다.
