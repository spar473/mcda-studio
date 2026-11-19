// Drives an installed server, without the source-checkout Playwright webServer configuration.
import { exerciseVisibleModel } from "./smoke_visible_model.mjs";
import { chromium } from "../frontend/node_modules/playwright-core/index.mjs";
import { readFileSync, writeFileSync } from "node:fs";
const [url, output] = process.argv.slice(2);
const browser = await chromium.launch({
  ...(process.env.MCDA_CHROMIUM ? { executablePath: process.env.MCDA_CHROMIUM } : {}),
});
try {
  const page = await browser.newPage({ viewport: { width: 1360, height: 860 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await exerciseVisibleModel(page, url, output);
  await page.goto(url);
  await page.getByRole("button", { name: "Examples…" }).click();
  await page.getByRole("button", { name: "Add NZ deep-tech startups for VC due diligence" }).click();
  await page.getByRole("tab", { name: "Results", exact: true }).click();
  const ranking = page.getByRole("table", { name: "Ranking", exact: true });
  await ranking.waitFor();
  if (!(await ranking.textContent()).includes("0.7227")) throw Error("Installed GUI ranking mismatch");
  const event = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download analysis JSON", exact: true }).click();
  await (await event).saveAs(`${output}/browser-analysis.json`);
  const document = JSON.parse(readFileSync(`${output}/browser-analysis.json`, "utf8"));
  writeFileSync(`${output}/browser-project.json`, JSON.stringify(document.source_project));
  await page.screenshot({ path: `${output}/installed-gui.png`, fullPage: true });
  await page.reload();
  await page.getByRole("tab", { name: "Results", exact: true }).click();
  await ranking.waitFor();
  if (!(await ranking.textContent()).includes("0.7227")) throw Error("Reopened GUI ranking mismatch");
  const recovery = await (await page.request.post(`${url}/api/projects`, { data: { title: "Installed recovery check" } })).json();
  await page.request.delete(`${url}/api/projects/${recovery.project.id}`);
  await page.goto(url);
  await page.getByText(/^Recently deleted/).click();
  await page.getByRole("button", { name: "Restore Installed recovery check", exact: true }).click();
  await page.getByRole("button", { name: "Open Installed recovery check", exact: true }).waitFor();
  const restored = await (await page.request.get(`${url}/api/projects/${recovery.project.id}`)).json();
  if (restored.fingerprint !== recovery.fingerprint) throw Error("Installed GUI restore changed the project");
  await page.screenshot({ path: `${output}/installed-recovery.png`, fullPage: true });
  await page.request.delete(`${url}/api/projects/${recovery.project.id}`);
  if (errors.length) throw Error(errors.join("\n"));
} finally {
  await browser.close();
}
