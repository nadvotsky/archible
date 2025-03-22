import js from "@eslint/js";
import ts from "typescript-eslint";
import vitest from "@vitest/eslint-plugin";

function jsConfigs() {
  return [
    {
      ...js.configs.all,
      files: ["src/**/*.js"],
      ignores: ["src/**/*.test.js"],
      linterOptions: {
        reportUnusedDisableDirectives: true,
      },
    },
  ];
}

function tsConfigs() {
  const eachConfig = (config) => ({
    ...config,
    files: ["src/**/*.ts"],
    ignores: ["src/**/*.test.ts"],
    linterOptions: {
      reportUnusedDisableDirectives: true,
    },
  });

  return [
    ...ts.configs.strictTypeChecked.map(eachConfig),
    ...ts.configs.stylisticTypeChecked.map(eachConfig),
    {
      languageOptions: {
        parserOptions: {
          projectService: true,
          tsconfigRootDir: import.meta.dirname,
        },
      },
    },
  ];
}

function testsConfigs() {
  return [
    {
      ...vitest.configs.all,
      files: ["src/**/*.test.js", "src/**.test.ts"],
      linterOptions: {
        reportUnusedDisableDirectives: true,
      },
      settings: {
        vitest: {
          typecheck: true,
        },
      },
    },
  ];
}

export default [...jsConfigs(), ...tsConfigs(), ...testsConfigs()];
