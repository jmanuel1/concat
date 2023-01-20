// Concat Highlighting Package for Atom
// Copyright (c) 2022-2023 Jason Manuel <jama.indo@hotmail.com>
//
// Based on JavaScript Semantic Highlighting Package for Atom
// Copyright (c) 2014-2015 Philipp Emanuel Weidmann <pew@worldwidemann.com>
//
// Released under the terms of the MIT License (http://opensource.org/licenses/MIT)
import {
  Disposable,
  Grammar,
  GrammarRegistry,
  DisplayMarker,
  TextBuffer,
  TextEditor,
  RangeCompatible,
} from "atom";
// TODO: Use a dummy textmate grammar instead.
const GrammarClass = Object.getPrototypeOf(
  Object.getPrototypeOf(atom.grammars.getGrammars()[0])
).constructor as new (registry: GrammarRegistry, options: unknown) => Grammar;
import Concat, { Token } from "./concat";

// QUESTION: Can I just implement the Grammar interface instead?
export default class ConcatGrammar extends GrammarClass {
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

  static async acornTokenize(line: string, editor: TextEditor) {
    const tokens: Token[] = [];

    const tokenizer = Concat.tokenize(line, editor);
    for await (const token of tokenizer) {
      if (token.type.type === "eof") {
        break;
      }
      tokens.push(token);
    }
    return { tokens };
  }

  static tokenScopes(token) {
    if (token.type.type === "NAME") {
      if (
        ["None", "True", "False", "Ellipsis", "...", "NotImplemented"].includes(
          token.value
        )
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

  // override tokenizeLine(line, ruleStack, firstLine) {
  //   const tags = [];
  //   const tokens = [];
  //   return { line, tags, tokens, ruleStack: [] };
  // }

  startMarkingTokens() {
    const concatTextEditors = new Map();
    this.textEditorsObserver = atom.workspace.observeTextEditors((editor) => {
      const grammarObserver = editor.observeGrammar((grammar) => {
        if (grammar === this) {
          const state: {
            markers: DisplayMarker[];
            buffer: TextBuffer;
            editor: TextEditor;
            changeObserver?: Disposable;
          } = { markers: [], buffer: editor.getBuffer(), editor };
          // initial highlight
          ConcatGrammar.markTokens(null, state);
          state.changeObserver = editor
            .getBuffer()
            .onDidStopChanging((event) => {
              // Note: Not fast enough to use editor.onDidChange
              ConcatGrammar.markTokens(event.changes, state);
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
      const destroyObserver = editor.onDidDestroy(() => {
        grammarObserver.dispose();
        destroyObserver.dispose();
      });
    });
  }

  static markTokens(changes, state) {
    return ConcatGrammar.markTokensForChange(changes, state);
  }

  static destroyMarkers(markers: DisplayMarker[]): void {
    markers.forEach((marker) => marker.destroy());
    markers.splice(0, markers.length);
  }

  static async markTokensForChange(change, state) {
    let range;
    let text = state.editor.getText();

    const tokens: {
      value: string;
      scopes: string[] | null;
      range: RangeCompatible;
    }[] = [];

    const tokenizeResult = await ConcatGrammar.acornTokenize(
      text,
      state.editor
    );
    const acornTokens = tokenizeResult.tokens;

    for (const token of acornTokens) {
      text = token.value;
      const tokenScopes = ConcatGrammar.tokenScopes(token);
      range = [
        [token.start[0] - 1, token.start[1]],
        [token.end[0] - 1, token.end[1]],
      ];
      if (tokenScopes) {
        tokens.push({ value: text, scopes: tokenScopes, range });
      }
    }

    // Destroy the markers as late as possible to prevent a flash of unhighlighted text.
    ConcatGrammar.destroyMarkers(state.markers);

    for (const processedToken of tokens) {
      // we destroy the markers ourselves
      const marker = state.buffer.markRange(processedToken.range, {
        invalidate: "never",
      });
      state.markers.push(marker);
      processedToken.scopes?.forEach((scope) => {
        const cssClass = "syntax--" + scope;
        state.editor.decorateMarker(marker, {
          type: "text",
          class: cssClass,
        });
      });
    }
  }
}
