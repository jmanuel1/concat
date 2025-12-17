import { AutoLanguageClient, LanguageServerProcess } from "atom-languageclient";
import Concat from "./concat";
import { execFile as nodeExecFile, ExecFileOptions } from "child_process";
import { isErrnoException } from "./error";
import { promisify } from "util";

/**
 * A Language Server Protocol client for Concat.
 */
class ConcatLanguageClient extends AutoLanguageClient {
  private readonly grammarScopes = ["source.concat"];
  private readonly languageName = "Concat";
  private readonly serverName = "Concat LSP";

  override getGrammarScopes() {
    return this.grammarScopes;
  }

  override getLanguageName() {
    return this.languageName;
  }

  override getServerName() {
    return this.serverName;
  }

  override startServerProcess(projectPath: string) {
    const possiblePythonPaths = Concat.collectPossiblePythonPaths(projectPath);
    return this.startServerProcessUsingFoundPython(
      possiblePythonPaths,
      projectPath,
    );
  }

  private startServerProcessUsingFoundPython(
    pythonPaths: string[],
    projectPath: string,
  ) {
    if (pythonPaths.length === 0) {
      throw Error("Could not find Python executable");
    }

    const process = super.spawn(pythonPaths[0], ["-m", "concat.lsp"], {
      cwd: projectPath,
      windowsHide: true,
    });
    return new Promise<LanguageServerProcess>((resolve, reject) => {
      let alreadyResolved = false;
      process.on("error", (error) => {
        if (alreadyResolved) {
          console.error(error);
          return;
        }

        if (isErrnoException(error) && error.code === "ENOENT") {
          resolve(
            this.startServerProcessUsingFoundPython(
              pythonPaths.slice(1),
              projectPath,
            ),
          );
        } else {
          reject(error);
        }
        alreadyResolved = true;
      });
      /* https://nodejs.org/docs/latest-v14.x/api/child_process.html#child_process_subprocess_pid */
      if (process.pid !== undefined) {
        resolve(process);
        alreadyResolved = true;
      }
    });
  }

  public override restartAllServers() {
    this.logger.debug("restarting Concat server");
    return super.restartAllServers();
  }
}

export default new ConcatLanguageClient();
