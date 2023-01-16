// Concat Highlighting Package for Atom
// Copyright (c) 2022-2023 Jason Manuel <jama.indo@hotmail.com>
//
// Based on JavaScript Semantic Highlighting Package for Atom
// Copyright (c) 2014-2015 Philipp Emanuel Weidmann <pew@worldwidemann.com>
//
// Released under the terms of the MIT License (http://opensource.org/licenses/MIT)

const JavaScriptSemanticGrammar = require("./javascript-semantic-grammar");

let grammar = null;

module.exports = {
  activate(state) {
    atom.grammars.addGrammar(
      (grammar = new JavaScriptSemanticGrammar(atom.grammars))
    );
  },

  deactivate() {
    grammar?.destroy();
  },
};
