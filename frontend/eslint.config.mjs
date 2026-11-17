import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier/flat";

/**
 * 핵심 계층은 app → features → domain → vision · lib 순서다.
 * components는 공용 UI와 앱 지원 컴포넌트를 두는 별도 계층이며 app·features를 가져오지 않는다.
 * 테스트 파일에도 같은 규칙을 적용한다.
 */
const forbid = (...layers) => ({
  rules: {
    "no-restricted-imports": [
      "error",
      {
        patterns: layers.flatMap((layer) => {
          const message = `이 폴더는 ${layer}를 가져올 수 없다. 핵심 의존은 app → features → domain → vision·lib 순서다.`;
          return [
            { group: [`@/${layer}`, `@/${layer}/**`], message },
            // 상대 경로로 돌아 가져오는 것도 막는다
            { regex: String.raw`^\.{1,2}/(?:.*/)?${layer}(?:/|$)`, message },
          ];
        }),
      },
    ],
  },
});

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  prettier,
  {
    rules: {
      // import는 패키지 / @/ / 상대 경로 순으로 묶고, 묶음 사이는 빈 줄, 묶음 안은 경로 알파벳순
      "import/order": [
        "error",
        {
          groups: ["builtin", "external", "internal", ["parent", "sibling", "index"]],
          pathGroups: [{ pattern: "@/**", group: "internal" }],
          pathGroupsExcludedImportTypes: ["builtin"],
          "newlines-between": "always",
          alphabetize: { order: "asc", caseInsensitive: true },
        },
      ],
    },
  },
  { files: ["src/vision/**"], ...forbid("domain", "features", "app", "mocks") },
  { files: ["src/domain/**"], ...forbid("features", "app", "components", "mocks") },
  { files: ["src/features/**"], ...forbid("app") },
  { files: ["src/lib/**"], ...forbid("vision", "domain", "features", "app", "components") },
  { files: ["src/components/**"], ...forbid("features", "app") },
  {
    // page가 키 · 주소를 읽어 화면을 고르는 통합 동작을 검증하는 테스트는 page를 직접 올린다
    files: [
      "src/features/loading/loading-preparation.test.tsx",
      "src/features/guide/run-guide-provider.test.tsx",
    ],
    rules: { "no-restricted-imports": "off" },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // copied by scripts/sync-mediapipe-assets.mjs
    "public/mediapipe/**",
    // copied by scripts/sync-brow-assets.mjs
    "public/brow-runtime/**",
    // copied by scripts/sync-mediapipe-assets.mjs
    "public/occlusion-runtime/**",
  ]),
]);

export default eslintConfig;
