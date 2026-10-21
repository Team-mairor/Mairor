import type { NextConfig } from "next";

// cacheComponents·partialPrefetching은 정적 내보내기와 호환되지 않아 쓰지 않는다.
const nextConfig: NextConfig = {
  output: "export",
  images: {
    unoptimized: true,
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
