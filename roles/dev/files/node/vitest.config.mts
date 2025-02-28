import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["src/**/*.test.[jt]s"],
    typecheck: {
      enabled: true,
      include: ["src/**/*.test.[jt]s"],
    },
  },
});
