import { defineConfig } from "vitest/config";

// tsconfig keeps "jsx": "preserve" for Next.js; tests need JSX compiled, so set it here.
export default defineConfig({
  oxc: { jsx: { runtime: "automatic" } },
});
