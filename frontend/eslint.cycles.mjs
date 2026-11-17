import base from "./eslint.config.mjs";

/**
 * 파일 단위 순환 검사. 전체 소스를 따라가 5분 가까이 걸려 기본 lint에서는 빼 두었다.
 * 폴더 단위 순환은 src/architecture.test.ts가 빠르게 막는다. 구조를 크게 바꾼 뒤에 `npm run lint:cycles`로 돌린다
 */
const cycleConfig = [
  ...base,
  {
    files: ["src/**/*.{ts,tsx}"],
    rules: { "import/no-cycle": ["error", { maxDepth: 6, ignoreExternal: true }] },
  },
];

export default cycleConfig;
