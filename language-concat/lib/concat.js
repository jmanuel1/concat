const { execFile: nodeExecFile } = require("child_process");
const { exists: nodeExists } = require("fs");
const { join } = require("path");
const { promisify } = require("util");

const execFile = promisify(nodeExecFile);
const exists = promisify(nodeExists);

module.exports = class Concat {
  async * tokenize(line, editor) {
    const promise = execFile(await this.findPython(editor), ["-m", "concat", "--tokenize"], {
      encoding: "utf-8",
      windowsHide: true
    });
    const process = promise.child;
    process.stdin.write(line);
    process.stdin.end();
    const { stdout } = await promise;
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

    for (const token of remainingTokens) {
      yield token;
    }
  }

  async findPython(editor) {
    const virtualEnvPaths = ["env/Scripts/python.exe", "env/bin/python"];
    if (!editor) throw new Error("You need a text editor to find the path to Python.");
    const editorPath = editor.getPath();
    const [projectPath, _] = atom.project.relativizePath(editorPath);
    if (!projectPath) return "python";
    for (let path of virtualEnvPaths) {
      path = join(projectPath, path);
      if (await exists(path)) {
        return path;
      }
    }
    return "python";
  }
};
