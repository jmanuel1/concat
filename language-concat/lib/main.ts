// Concat Highlighting Package for Atom
// Copyright (c) 2022-2023 Jason Manuel <jama.indo@hotmail.com>
//
// Based on JavaScript Semantic Highlighting Package for Atom
// Copyright (c) 2014-2015 Philipp Emanuel Weidmann <pew@worldwidemann.com>
//
// Released under the terms of the MIT License (http://opensource.org/licenses/MIT)

import ConcatGrammar from "./concat-grammar";
import concatLanguageClient from "./lsp-client";
import { Disposable } from "atom";

let grammar: ConcatGrammar | null = null;
let commandsDisposable: Disposable;

module.exports = {
  activate() {
    atom.grammars.addGrammar((grammar = new ConcatGrammar(atom.grammars)));
    concatLanguageClient.activate();
    commandsDisposable = atom.commands.add("atom-workspace", {
      "concat:restart-all-servers": () =>
        concatLanguageClient.restartAllServers(),
    });
  },

  deactivate() {
    grammar?.destroy();
    concatLanguageClient.deactivate();
    commandsDisposable.dispose();
  },

  consumeLinterV2: concatLanguageClient.consumeLinterV2.bind(
    concatLanguageClient
  ),

  consumeDatatip: concatLanguageClient.consumeDatatip.bind(
    concatLanguageClient
  ),
};
