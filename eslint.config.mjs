import globals from "globals";

export default [
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
];
