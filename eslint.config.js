const globals = require("globals");
const { defineConfig } = require("eslint/config");

module.exports = defineConfig([
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
