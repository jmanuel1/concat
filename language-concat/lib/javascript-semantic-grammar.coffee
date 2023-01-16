# JavaScript Semantic Highlighting Package for Atom
#
# Copyright (c) 2014-2015 Philipp Emanuel Weidmann <pew@worldwidemann.com>
#
# Nemo vir est qui mundum non reddat meliorem.
#
# Released under the terms of the MIT License (http://opensource.org/licenses/MIT)
# https://raw.githubusercontent.com/atom/flight-manual.atom.io/master/data/apis-by-version/v1.57.0.json
$ = require "jquery"
# stupid
Grammar = atom.grammars.getGrammars()[0].constructor.__super__.constructor
Concat = require "./concat.js"

numberOfColors = 8

module.exports =
class JavaScriptSemanticGrammar extends Grammar
  constructor: (registry) ->
    name = "Concat"
    scopeName = "source.concat"
    @concat = new Concat()
    super(registry, {name, scopeName, fileTypes: ["cat"]})
    @registry = registry.textmateRegistry
    @startMarkingTokens()

  destroy: ->
    @textEditorsObserver?.destroy()

  acornTokenize: (line) ->
    tokens = []
    rules = []

    try
      tokenizer = @concat.tokenize(line)
    catch error
      # Error in initTokenState
      console.log error
      return { tokens: tokens, rules: rules }

    while true
      try
        token = tokenizer()
      catch error
        console.log error
        return { tokens: tokens, rules: rules }
      # Object is mutable, therefore it must be cloned
      token = $.extend(true, {}, token)
      if token.type.type is "eof"
        return { tokens: tokens, rules: rules }
      tokens.push token

  # Converted from http://stackoverflow.com/a/7616484
  # with the help of http://js2coffee.org/
  hash: (string) ->
    hash = 0
    return hash if string.length is 0
    i = 0
    len = string.length
    while i < len
      chr = string.charCodeAt(i)
      hash = ((hash << 5) - hash) + chr
      hash |= 0
      i++
    return hash

  colorIndex: (string) ->
    (Math.abs(@hash(string)) % numberOfColors) + 1

  tokenScopes: (token, text) ->
    if token.type.type is "NAME"
      if ["None", "True", "False", "Ellipsis", "...", "NotImplemented"].includes(token.value)
        return ["identifier", "constant"]
      return ["identifier"]
    else if token.type.type is "COMMENT"
      return ["comment"]
    else if token.isKeyword
      return ["keyword"]
    else if token.type.type is "NUMBER"
      return ["constant", "numeric"]
    else if token.type.type is "STRING"
      firstQuoteIndex = Math.min(token.value.indexOf("'"), token.value.indexOf('"'))
      if /r/i.test(token.value.slice(0, firstQuoteIndex))
        return ["string", "regexp"]
      return ["string"]
    return null

  tokenizeLine: (line, ruleStack, firstLine = false) ->
    tags = []
    tokens = []
    return { line, tags, tokens, ruleStack: [] }

  startMarkingTokens: ->
    concatTextEditors = new Map()
    @textEditorsObserver = atom.workspace.observeTextEditors((editor) =>
      grammarObserver = editor.observeGrammar((grammar) =>
        if grammar is @
          state = {markers: [], buffer: editor.getBuffer(), editor}
          # initial highlight
          @markTokens(null, state)
          state.changeObserver = editor.getBuffer().onDidStopChanging((event) =>
            @markTokens(event.changes, state))
          concatTextEditors.set(
            editor,
            state
          )
        else
          concatTextEditors.get(editor)?.changeObserver?.dispose()
          concatTextEditors.get(editor)?.markers?.forEach((marker) -> marker.destroy())
          concatTextEditors.delete(editor)
      )
      destroyObserver = editor.onDidDestroy(->
        grammarObserver.dispose()
        destroyObserver.dispose()
      )
    )

  markTokens: (changes, state) ->
    @markTokensForChange(changes, state)

  markTokensForChange: (change, state) ->
    state.markers.forEach((marker) -> marker.destroy())
    state.markers = []
    text = state.editor.getText()

    tokens = []

    addToken = (text, range, scopes = null) ->
      tokens.push { value: text, scopes, range }

    tokenizeResult = @acornTokenize(text)
    acornTokens = tokenizeResult.tokens
    # Comment tokens might have been inserted in the wrong place
    acornTokens.sort((a, b) ->
      cmp = a.start[0] - b.start[0]
      if cmp != 0
        return cmp
      return a.start[1] - b.start[1]
    )

    tokenPos = 0
    for token in acornTokens
      console.log token
      text = token.value
      tokenScopes = @tokenScopes(token, text)
      console.log tokenScopes
      range = [[token.start[0] - 1, token.start[1]], [token.end[0] - 1, token.end[1]]]
      console.log token.start, token.end, range
      if tokenScopes?
        addToken text, range, tokenScopes
        tokenPos = token.end

    for processedToken in tokens
      # we destroy the markers ourselves
      marker = state.buffer.markRange(processedToken.range, {invalidate: "never"})
      state.markers.push(marker)
      processedToken.scopes.forEach((scope) ->
        cssClass = "syntax--" + scope
        state.editor.decorateMarker(marker, {type: "text", class: cssClass})
      )
