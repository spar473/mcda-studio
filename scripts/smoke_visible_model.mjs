// Focused D1 workflow against the installed app. Only cleanup/verification use HTTP directly.
import { writeFileSync } from "node:fs";

export async function exerciseVisibleModel(page, url, output) {
  const evaluations = [];
  const observe = request => { if (/\/api\/(evaluate|analysis\/record|sensitivity)/.test(request.url())) evaluations.push(request.url()); };
  page.on("request", observe);
  try {
    await page.goto(url);
    await page.getByRole("button", { name: "New project…" }).click();
    await page.getByLabel("Title", { exact: true }).fill("Installed visible model");
    await page.getByRole("button", { name: "Create", exact: true }).click();
    await page.getByRole("button", { name: "Canvas", exact: true }).waitFor();
    const id = /#\/p\/(.+)$/.exec(page.url())?.[1];
    if (!id) throw Error("Missing installed visible-model ID");
    await page.getByRole("button", { name: "Add top-level objective" }).click();
    await page.getByLabel("Name", { exact: true }).fill("Research access");
    await page.getByLabel("Name", { exact: true }).press("Enter");
    await page.locator(".tree-name", { hasText: "Research access" }).waitFor();
    await page.getByRole("button", { name: "Add child", exact: true }).click();
    await page.getByLabel("Name", { exact: true }).fill("Laboratory availability");
    await page.getByLabel("Name", { exact: true }).press("Enter");
    await page.locator(".tree-name", { hasText: "Laboratory availability" }).waitFor();
    await page.getByRole("button", { name: "Edit selected item", exact: true }).click();
    await page.getByLabel("Name", { exact: true }).fill("Shared equipment");
    await page.getByLabel("Name", { exact: true }).press("Enter");
    await page.locator(".tree-name", { hasText: "Shared equipment" }).waitFor();
    await page.getByRole("button", { name: "Undo", exact: true }).click();
    await page.locator(".tree-name", { hasText: "Laboratory availability" }).waitFor();
    await page.getByRole("button", { name: "Redo", exact: true }).click();
    await page.locator(".tree-name", { hasText: "Shared equipment" }).waitFor();
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await page.getByTestId("save-state").filter({ hasText: "All changes saved" }).waitFor();
    const before = await (await page.request.get(`${url}/api/projects/${id}`)).json();
    await page.getByRole("button", { name: "Outline", exact: true }).click();
    await page.getByRole("button", { name: "Canvas", exact: true }).click();
    await page.getByRole("button", { name: "Collapse Research access", exact: true }).click();
    await page.getByRole("button", { name: "Expand Research access", exact: true }).click();
    await page.locator(".model-card").evaluateAll(async nodes => { await Promise.all(nodes.flatMap(n => n.getAnimations().map(a => a.finished))); });
    await page.screenshot({ path: `${output}/installed-visible-model.png`, fullPage: true });
    await page.reload();
    await page.locator(".tree-name", { hasText: "Shared equipment" }).waitFor();
    const after = await (await page.request.get(`${url}/api/projects/${id}`)).json();
    if (after.fingerprint !== before.fingerprint || after.project.criteria.length !== 2) throw Error("Visible-model save/reopen mismatch");
    if (evaluations.length) throw Error("Structural workflow requested full numerical analysis");
    writeFileSync(`${output}/installed-visible-model.json`, JSON.stringify({
      status: "passed", id, fingerprint: after.fingerprint, project: after.project,
      actions: "create, add, edit, undo/redo, presentation, save and reopen", evaluations,
    }, null, 2));
    await page.request.delete(`${url}/api/projects/${id}`);
  } finally {
    page.off("request", observe);
  }
}
