const { execFileSync } = require("child_process");
const { existsSync } = require("fs");
const { join } = require("path");

module.exports = class Concat {
  constructor() {
    this._remainingTokens = [];
  }

  tokenize(line) {
    const stdout = execFileSync(this.findPython(), ["-m", "concat", "--tokenize"], {
      encoding: "utf-8",
      input: line,
      windowsHide: true
    });
    const tokens = JSON.parse(stdout);
    const remainingTokens = tokens.map(token => {
      return {
        start: token.start,
        end: token.end,
        value: token.value,
        type: { type: token.type },
        isKeyword: token.is_keyword
      };
    });

    let finished = false;

    return () => {
      if (remainingTokens.length > 0) {
        const token = remainingTokens.shift();
        if (remainingTokens.length === 0) {
          finished = true;
        }
        return token;
      }
      if (finished) {
        throw new Error('no more tokens');
      }
    };
  }

  findPython() {
    const virtualEnvPaths = ["env/Scripts/python.exe", "env/bin/python"];
    const editor = atom.workspace.getActiveTextEditor();
    if (!editor) return "python";
    const editorPath = editor.getPath();
    const [projectPath, _] = atom.project.relativizePath(editorPath);
    if (!projectPath) return "python";
    for (let path of virtualEnvPaths) {
      path = join(projectPath, path);
      if (existsSync(path)) {
        return path;
      }
    }
    return "python";
  }
};
