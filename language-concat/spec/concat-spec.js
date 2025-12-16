const { default: Concat } = require("../lib/concat");

describe("execFoundPython", () => {
  it("does not throw when python is not in the first place it looks", async () => {
    expect(() => Concat.execFoundPython(atom.workspace.getActiveTextEditor(), [], {}, "")).not.toThrow();
  });
});
