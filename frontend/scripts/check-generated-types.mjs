// Fails if src/api/schema.ts is not exactly what openapi-typescript generates from the
// committed OpenAPI document (docs/api/openapi.json) - i.e. the TypeScript types can never
// drift from the Python models.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "mcda-types-"));
const out = join(dir, "schema.ts");
try {
  execFileSync("npx", ["openapi-typescript", "../docs/api/openapi.json", "-o", out], {
    stdio: "ignore",
    shell: process.platform === "win32",
  });
  const fresh = readFileSync(out, "utf8");
  const committed = readFileSync("src/api/schema.ts", "utf8");
  if (fresh !== committed) {
    console.error("src/api/schema.ts is out of date: run `npm run gen:types`");
    process.exit(1);
  }
  console.log("src/api/schema.ts is up to date with docs/api/openapi.json");
} finally {
  rmSync(dir, { recursive: true, force: true });
}
