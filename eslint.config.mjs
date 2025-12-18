import globals from "globals";

export default [
  {
    files: ["language-concat/spec/**/*.js"],
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
