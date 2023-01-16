// Concat Highlighting Package for Atom
// Copyright (c) 2022-2023 Jason Manuel <jama.indo@hotmail.com>
//
// Based on JavaScript Semantic Highlighting Package for Atom
// Copyright (c) 2014-2015 Philipp Emanuel Weidmann <pew@worldwidemann.com>
//
// Released under the terms of the MIT License (http://opensource.org/licenses/MIT)
let JavaScriptSemanticGrammar;
const $ = require("jquery");
import {
  Disposable,
  Grammar,
  GrammarRegistry,
  DisplayMarker,
  TextBuffer,
  TextEditor,
} from "atom";
// TODO: Use a dummy textmate grammar instead.
const Grammar = Object.getPrototypeOf(
  Object.getPrototypeOf(atom.grammars.getGrammars()[0])
).constructor as new (registry: GrammarRegistry, options: any) => Grammar;
import Concat from "./concat";

module.exports =
  // QUESTION: Can I just implement the Grammar interface instead?
  JavaScriptSemanticGrammar = class JavaScriptSemanticGrammar extends Grammar {
    private concat: Concat;
    private registry: GrammarRegistry;
    private textEditorsObserver?: Disposable;

    constructor(registry) {
      const name = "Concat";
      const scopeName = "source.concat";
      super(registry, { name, scopeName, fileTypes: ["cat"] });
      this.concat = new Concat();
      this.registry = registry.textmateRegistry;
      this.startMarkingTokens();
    }

    destroy() {
      this.textEditorsObserver?.dispose();
    }

    async acornTokenize(line: string, editor: TextEditor) {
      const tokens = [];

      const tokenizer = this.concat.tokenize(line, editor);
      for await (let token of tokenizer) {
        if (token.type.type === "eof") {
          break;
        }
        tokens.push(token);
      }
      return { tokens };
    }

    tokenScopes(token, text) {
      if (token.type.type === "NAME") {
        if (
          [
            "None",
            "True",
            "False",
            "Ellipsis",
            "...",
            "NotImplemented",
          ].includes(token.value)
        ) {
          return ["identifier", "constant"];
        }
        return ["identifier"];
      } else if (token.type.type === "COMMENT") {
        return ["comment"];
      } else if (token.isKeyword) {
        return ["keyword"];
      } else if (token.type.type === "NUMBER") {
        return ["constant", "numeric"];
      } else if (token.type.type === "STRING") {
        const singleQuoteIndex = token.value.indexOf("'");
        const doubleQuoteIndex = token.value.indexOf('"');
        let firstQuoteIndex: number;
        if (singleQuoteIndex < 0) firstQuoteIndex = doubleQuoteIndex;
        else if (doubleQuoteIndex < 0) {
          firstQuoteIndex = singleQuoteIndex;
        } else {
          firstQuoteIndex = Math.min(singleQuoteIndex, doubleQuoteIndex);
        }
        if (/r/i.test(token.value.slice(0, firstQuoteIndex))) {
          return ["string", "regexp"];
        }
        return ["string"];
      }
      return null;
    }

    tokenizeLine(line, ruleStack, firstLine) {
      if (firstLine == null) {
        firstLine = false;
      }
      const tags = [];
      const tokens = [];
      return { line, tags, tokens, ruleStack: [] };
    }

    startMarkingTokens() {
      const concatTextEditors = new Map();
      this.textEditorsObserver = atom.workspace.observeTextEditors((editor) => {
        let destroyObserver;
        const grammarObserver = editor.observeGrammar((grammar) => {
          if (grammar === this) {
            const state: {
              markers: DisplayMarker[];
              buffer: TextBuffer;
              editor: TextEditor;
              changeObserver?: Disposable;
            } = { markers: [], buffer: editor.getBuffer(), editor };
            // initial highlight
            this.markTokens(null, state);
            state.changeObserver = editor
              .getBuffer()
              .onDidStopChanging((event) => {
                // Note: Not fast enough to use editor.onDidChange
                this.markTokens(event.changes, state);
              });
            concatTextEditors.set(editor, state);
          } else {
            concatTextEditors.get(editor)?.changeObserver?.dispose();
            concatTextEditors
              .get(editor)
              ?.markers?.forEach((marker) => marker.destroy());
            concatTextEditors.delete(editor);
          }
        });
        destroyObserver = editor.onDidDestroy(function () {
          grammarObserver.dispose();
          destroyObserver.dispose();
        });
      });
    }

    markTokens(changes, state) {
      return this.markTokensForChange(changes, state);
    }

    destroyMarkers(markers: DisplayMarker[]): void {
      markers.forEach((marker) => marker.destroy());
      markers.splice(0, markers.length);
    }

    async markTokensForChange(change, state) {
      let range;
      let text = state.editor.getText();

      const tokens = [];

      const addToken = (text, range, scopes = null) =>
        tokens.push({ value: text, scopes, range });

      const tokenizeResult = await this.acornTokenize(text, state.editor);
      const acornTokens = tokenizeResult.tokens;

      let tokenPos = 0;
      for (let token of acornTokens) {
        console.log(token);
        text = token.value;
        const tokenScopes = this.tokenScopes(token, text);
        console.log(tokenScopes);
        range = [
          [token.start[0] - 1, token.start[1]],
          [token.end[0] - 1, token.end[1]],
        ];
        console.log(token.start, token.end, range);
        if (tokenScopes != null) {
          addToken(text, range, tokenScopes);
          tokenPos = token.end;
        }
      }

      // Destroy the markers as late as possible to prevent a flash of unhighlighted text.
      this.destroyMarkers(state.markers);

      for (let processedToken of tokens) {
        // we destroy the markers ourselves
        var marker = state.buffer.markRange(processedToken.range, {
          invalidate: "never",
        });
        state.markers.push(marker);
        processedToken.scopes.forEach(function (scope) {
          const cssClass = "syntax--" + scope;
          state.editor.decorateMarker(marker, {
            type: "text",
            class: cssClass,
          });
        });
      }
    }
  };
