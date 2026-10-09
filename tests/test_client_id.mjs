import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

const require = createRequire(new URL("../web/package.json", import.meta.url));
const ts = require("typescript");
const sources = {
  react: ts.transpileModule(readFileSync(new URL("../web/src/clientId.ts", import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText,
  legacy: readFileSync(new URL("../quest_rag/static/app.js", import.meta.url), "utf8").split("const STORAGE_KEY")[0] + "exports.createClientId = createClientId;",
};

for (const [name, source] of Object.entries(sources)) {
  test(`${name}: LAN HTTP without randomUUID creates unique UUID v4 IDs`, () => {
    const context = { exports: {}, crypto: { getRandomValues: webcrypto.getRandomValues.bind(webcrypto) } };
    runInNewContext(source, context);
    const ids = Array.from({ length: 1000 }, () => context.exports.createClientId());
    assert.equal(new Set(ids).size, ids.length);
    for (const id of ids) assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });
  test(`${name}: native randomUUID preserves Crypto receiver`, () => {
    const crypto = { randomUUID() { assert.equal(this, crypto); return "native-id"; } };
    const context = { exports: {}, crypto };
    runInNewContext(source, context);
    assert.equal(context.exports.createClientId(), "native-id");
  });
}
