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
    super(registry, {name, scopeName, fileTypes: ["cat"],
      # contentRegex: /\bdef\s+\w+\(.*--.*\):|\$\.|\bcast\s*\(\w+\)/
    })
    @registry = registry.textmateRegistry
    # @fileTypes = [".cat"]
    # @contentRegex = /\bdef\s+\w+\(.*--.*\):|\$\.|\bcast\s*\(\w+\)/

  # Ensures that grammar takes precedence over standard JavaScript grammar
  getScore: ->
    return 0


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
      colorIndexScope = "color-index-" + @colorIndex(text)
      return "identifier." + colorIndexScope
    else if token.type.type is "COMMENT"
      return "comment"
    else if ["DEF", "IMPORT", "FROM", "AS", "CLASS", "CAST"].includes(token.type.type)
      return "keyword"
    else if token.type.type is "NUMBER"
      return "number"
    else if token.type.type is "STRING"
      return "string"
    return null

  tokenizeLine: (line, ruleStack, firstLine = false) ->
    tags = []
    tokens = []

    outerRegistry = @registry
    console.log outerRegistry
    addToken = (text, scopes = null) ->
      fullScopes = "source.concat" + (if scopes? then ("." + scopes) else "")
      tags.push outerRegistry.startIdForScope(fullScopes)
      tags.push text.length
      tags.push outerRegistry.endIdForScope(fullScopes)
      tokens.push { value: text, scopes: [fullScopes] }

    acornStartOffset = 0
    if ruleStack? and "unterminated_comment" in ruleStack
      # Help Acorn tokenize multi-line comments correctly
      commentEnd = line.indexOf("*/")
      if commentEnd is -1
        # Multi-line comment continues
        addToken line, "comment"
        return { line: line, tags: tags, tokens: tokens, ruleStack: ruleStack }
      else
        # Make Acorn skip over partial comment
        acornStartOffset = commentEnd + 2
        addToken line.substring(0, acornStartOffset), "comment"

    acornLine = line.substring(acornStartOffset)

    tokenizeResult = @acornTokenize(acornLine)
    acornTokens = tokenizeResult.tokens
    # Comment tokens might have been inserted in the wrong place
    acornTokens.sort((a, b) -> a.start - b.start)

    tokenPos = 0
    for token in acornTokens
      console.log token
      text = token.value
      tokenScopes = @tokenScopes(token, text)
      console.log tokenScopes
      if tokenScopes?
        if token.start > tokenPos
          addToken acornLine.substring(tokenPos, token.start)
        addToken text, tokenScopes
        tokenPos = token.end

    if tokenPos < acornLine.length
      addToken acornLine.substring(tokenPos)

    if tokens.length is 0
      addToken ""

    console.log tokens

    return { line: line, tags: tags, tokens: tokens, ruleStack: tokenizeResult.rules }
