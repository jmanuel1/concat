import { AutoLanguageClient } from "atom-languageclient";
import Concat from "./concat";

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
    atom.config.set("core.debugLSP", true);
    return super.spawn(
      Concat.collectPossiblePythonPaths(projectPath)[0],
      ["-m", "concat.lsp"],
      { cwd: projectPath, windowsHide: true }
    );
  }

  public override restartAllServers() {
    this.logger.debug("restarting Concat server");
    return super.restartAllServers();
  };
}

export default new ConcatLanguageClient();
