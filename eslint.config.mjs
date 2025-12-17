import globals from "globals";
import { defineConfig } from "eslint/config";

export default defineConfig([
  {
    basePath: "language-concat/spec",
    languageOptions: {
      globals: {
        ...globals.atomtest,
        ...globals.browser,
        ...globals.commonjs,
        ...globals.jasmine,
        ...globals.node,
      },
    },
  },
]);
