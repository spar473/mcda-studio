// Starts the real backend for the browser tests on a throw-away project folder.
import { spawn } from "node:child_process";
import { rmSync } from "node:fs";
import { resolve } from "node:path";

const port = process.env.MCDA_E2E_PORT ?? "8799";
const store = resolve(".e2e-store");
const python = process.env.MCDA_PYTHON ?? (process.platform === "win32" ? "python" : "python3");

rmSync(store, { recursive: true, force: true });
const child = spawn(
  python,
  ["-m", "mcda_studio", "serve", "--store", store, "--port", port, "--frontend", resolve("dist")],
  { stdio: "inherit" },
);
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
child.on("exit", (code) => process.exit(code ?? 0));
