// Concat Highlighting Package for Atom
// Copyright (c) 2022-2023 Jason Manuel <jama.indo@hotmail.com>
//
// Based on JavaScript Semantic Highlighting Package for Atom
// Copyright (c) 2014-2015 Philipp Emanuel Weidmann <pew@worldwidemann.com>
//
// Released under the terms of the MIT License (http://opensource.org/licenses/MIT)

import ConcatGrammar from "./concat-grammar";

let grammar: ConcatGrammar | null = null;

module.exports = {
  activate() {
    atom.grammars.addGrammar((grammar = new ConcatGrammar(atom.grammars)));
  },

  deactivate() {
    grammar?.destroy();
  },
};
