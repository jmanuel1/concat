import { AutoLanguageClient } from "atom-languageclient";
import Concat from "./concat";

class ConcatLanguageClient extends AutoLanguageClient {
  override getGrammarScopes() {
    return ["source.concat"];
  }

  override getLanguageName() {
    return "Concat";
  }

  override getServerName() {
    return "Concat LSP";
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
