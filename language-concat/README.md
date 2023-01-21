# Atom Syntax Highlighting for Concat

This provides syntax highlighting for the Concat language in Atom by calling
upon the Concat lexer. The tokens from the lexer are used to create markers
which are decorated with Atom's syntax CSS classes.

This package has been tested with Atom (atom-community fork)
`1.57.0-dev-d97d175f6`.

This package is based on
[p-e-w/language-javascript-semantic](https://github.com/p-e-w/language-javascript-semantic).
That package instead sends grammar tokens to Atom using the same class used by
Textmate and Tree Sitter grammars.

This package also demonstrates some techniques that might serve other developers
when creating similar packages for other languages:

- **Syntax highlighting that is defined programmatically** rather than through a
  `.cson` grammar file or a Tree Sitter grammar
- Connecting an **external parser or lexer** (Concat's lexer in this case)

## Acknowledgments

### Prior Art

- [p-e-w/language-javascript-semantic](https://github.com/p-e-w/language-javascript-semantic)
- [idris-hackers/atom-language-idris#31](https://github.com/idris-hackers/atom-language-idris/pull/31):
  I didn't know about this PR until I wrote this README, but it takes the same
  approach that this package uses.

### Dependencies

You must have `python` in
your path or in a virtual environment named `env` in your project. The Concat
package must be installed in that Python environment.

This package uses TypeScript and Atom TS Transpiler.

## License

Copyright © 2022-2023 Jason Manuel (<jama.indo@hotmail.com>)

Copyright © 2014-2015 Philipp Emanuel Weidmann (<pew@worldwidemann.com>)

Released under the terms of the [MIT License](http://opensource.org/licenses/MIT)
