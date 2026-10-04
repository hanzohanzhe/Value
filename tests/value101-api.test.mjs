import assert from "node:assert/strict";
import test from "node:test";

test("VALUE 101 client requests target the loopback model API in a production build", async () => {
  let value101ApiUrl;
  try {
    ({ value101ApiUrl } = await import("../app/features/learn/value101-api.mjs"));
  } catch {
    value101ApiUrl = undefined;
  }

  assert.equal(
    value101ApiUrl?.("/tutorials/value-101/completion-report"),
    "http://127.0.0.1:8766/api/tutorials/value-101/completion-report",
  );
});

test("VALUE 101 client requests honour an explicitly supplied API origin", async () => {
  let value101ApiUrl;
  try {
    ({ value101ApiUrl } = await import("../app/features/learn/value101-api.mjs"));
  } catch {
    value101ApiUrl = undefined;
  }

  assert.equal(
    value101ApiUrl?.("tutorials/value-101", "http://127.0.0.1:9901/"),
    "http://127.0.0.1:9901/api/tutorials/value-101",
  );
});
