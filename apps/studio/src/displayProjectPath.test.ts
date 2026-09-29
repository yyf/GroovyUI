import { describe, expect, it } from "vitest";
import { displayProjectPath } from "./displayProjectPath";

describe("displayProjectPath", () => {
  const project = "/Users/yyf/Code/GroovyUI/workspace";

  it("relativizes paths under the project root", () => {
    expect(displayProjectPath(`${project}/.groovy/models`, project)).toBe(
      ".groovy/models",
    );
    expect(
      displayProjectPath(`${project}/.groovy/cache/renders`, project),
    ).toBe(".groovy/cache/renders");
  });

  it("returns '.' for the project root itself", () => {
    expect(displayProjectPath(project, project)).toBe(".");
    expect(displayProjectPath(`${project}/`, project)).toBe(".");
  });

  it("keeps paths outside the project unchanged", () => {
    expect(displayProjectPath("/tmp/elsewhere", project)).toBe("/tmp/elsewhere");
  });

  it("handles Windows-style separators", () => {
    expect(
      displayProjectPath("C:\\proj\\workspace\\.groovy\\models", "C:\\proj\\workspace"),
    ).toBe(".groovy/models");
  });
});
