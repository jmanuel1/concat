import { execFile as nodeExecFile, ExecFileOptions } from "child_process";
import { ObjectEncodingOptions } from "fs";
import { join } from "path";
import { promisify } from "util";
import { TextEditor } from "atom";

const execFile = promisify(nodeExecFile);

export interface Token {
  start: [number, number];
  end: [number, number];
  value: string;
  type: { type: string };
  isKeyword: boolean;
}

/**
 * Functions to interact with the Concat executable.
 */
const Concat = {
  async *tokenize(line: string, editor: TextEditor): AsyncIterable<Token> {
    const { stdout } = await Concat.execFoundPython(
      editor,
      ["-m", "concat", "--tokenize"],
      {
        encoding: "utf-8",
        windowsHide: true,
        env: {
          PYTHONIOENCODING: "utf-8",
        },
      },
      line
    );
    const tokens = JSON.parse(stdout);
    const remainingTokens = tokens.map((token) => {
      return {
        start: token.start,
        end: token.end,
        value: token.value,
        type: { type: token.type },
        isKeyword: token.is_keyword,
      };
    });

    for (const token of remainingTokens) {
      yield token;
    }
  },

  collectPossiblePythonPaths(editor: TextEditor | string): string[] {
    const virtualEnvPaths = ["env/Scripts/python.exe", "env/bin/python"];
    function getProjectPath() {
      let projectPath: string | null;
      if (typeof editor === "string") {
        projectPath = editor;
      } else {
        if (!editor) return null;
        const editorPath = editor.getPath();
        if (!editorPath) {
          return null;
        }
        [projectPath] = atom.project.relativizePath(editorPath);
      }
      return projectPath;
    }
    const projectPath = getProjectPath();
    if (projectPath === null) return ["python"];
    return virtualEnvPaths
      .map((path) => join(projectPath, path))
      .concat(["python"]);
  },

  async execFoundPython(
    editor: TextEditor,
    args: string[],
    options: ExecFileOptions & ObjectEncodingOptions,
    input: string
  ): Promise<{ stdout: string }> {
    for (const pythonPath of Concat.collectPossiblePythonPaths(editor)) {
      const promise = execFile(pythonPath, args, options);
      const process = promise.child;

      const notFoundPromise = new Promise<{ stdout: string }>((_, reject) =>
        process.on("error", (error) => {
          reject(error);
        })
      );
      process.stdin?.write(input);
      process.stdin?.end();
      try {
        return await Promise.race([promise, notFoundPromise]);
      } catch (error) {
        if (isErrnoException(error) && error.code === "ENOENT") {
          continue;
        }
        throw error;
      }
    }
    throw new Error("No Python installation found.");
  },
};

type Concat = typeof Concat;

export default Concat;

function isErrnoException(error: Error): error is NodeJS.ErrnoException {
  return Boolean((error as NodeJS.ErrnoException).code);
}
