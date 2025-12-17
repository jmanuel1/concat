const { default: concatLanguageClient } = require("../lib/lsp-client");

describe("The LSP client", () => {
  concatLanguageClient.activate();

  it("can start the language server when multiple Python paths have to be tried", async () => {
    // path must exist, or else we'll think python doesn't exist
    await concatLanguageClient.startServerProcess(".");
  });

  it("fails to start the language server when Python is not found", async () => {
    const mockProcess = {
      on(event, cb) {
        switch (event) {
          case "error": {
            const error = Error("fake");
            error.code = "ENOENT";
            cb(error);
          }
        }
      },
    };
    spyOn(concatLanguageClient, "spawn").andReturn(mockProcess);

    try {
      await concatLanguageClient.startServerProcess(".");
    } catch (error) {
      expect(error.message).toEqual("Could not find Python executable");
      return;
    }
    throw Error("Expected error to be thrown");
  });
});
