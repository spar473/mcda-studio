// Editing behaviour that is easy to get wrong: unsaved-change protection, validation feedback that
// leads to the problem, destructive tree operations (always confirmed, always undoable), project
// deletion and duplication, and the "someone else saved first" conflict.
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { at, VC_FILE, openTab, readJson, saveState, selectNode, STORE, storedFile, tab, treeItem } from "./helpers";

interface Raw {
  id: string;
  title: string;
  alternatives: { id: string; name: string }[];
}
const original = readJson(VC_FILE) as Raw;
const FIRST_ALT = at(original.alternatives, 0).name;
const VC_NODES = 12; // 4 objectives + 8 criteria

let counter = 0;
/** A private copy of the VC project under its own id, so tests never share state. */
async function freshProject(request: APIRequestContext): Promise<{ id: string; title: string }> {
  counter += 1;
  const id = `edit-test-${String(Date.now())}-${String(counter)}`;
  const title = `Edit test ${String(counter)}`;
  const r = await request.post("/api/projects/import", { data: { ...original, id, title } });
  expect(r.status()).toBe(201);
  return { id, title };
}

const open = async (page: Page, id: string): Promise<void> => {
  await page.goto(`/#/p/${id}`);
  await expect(saveState(page)).toHaveText("All changes saved");
};

const items = (page: Page) => page.getByRole("treeitem");
const dialog = (page: Page, name: string) => page.getByRole("dialog", { name });

async function renameFirstAlternative(page: Page, to: string): Promise<void> {
  await openTab(page, "Alternatives");
  const field = page.getByLabel(`Name of alternative ${FIRST_ALT}`);
  await field.fill(to);
  await field.press("Enter");
  await expect(saveState(page)).toHaveText("● Unsaved changes");
}

test.describe("unsaved changes", () => {
  test("leaving is guarded: keep editing, discard, or save and leave", async ({ page, request }) => {
    const { id, title } = await freshProject(request);
    const bytes = await storedFile(request, id);
    await open(page, id);
    await renameFirstAlternative(page, "Renamed once");

    // keep editing
    await page.getByRole("button", { name: "← Projects" }).click();
    await expect(dialog(page, "Unsaved changes")).toBeVisible();
    await dialog(page, "Unsaved changes").getByRole("button", { name: "Keep editing" }).click();
    await expect(dialog(page, "Unsaved changes")).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(saveState(page)).toHaveText("● Unsaved changes");

    // discard: nothing is written
    await page.getByRole("button", { name: "← Projects" }).click();
    await dialog(page, "Unsaved changes").getByRole("button", { name: "Discard changes" }).click();
    await expect(page.getByRole("heading", { name: "Projects", exact: true })).toBeVisible();
    expect((await storedFile(request, id)).equals(bytes)).toBe(true);

    // save and leave: it is written, and the reopened project shows it
    await open(page, id);
    await renameFirstAlternative(page, "Renamed twice");
    await page.getByRole("button", { name: "← Projects" }).click();
    await dialog(page, "Unsaved changes").getByRole("button", { name: "Save and leave" }).click();
    await expect(page.getByRole("heading", { name: "Projects", exact: true })).toBeVisible();
    expect((await storedFile(request, id)).toString()).toContain("Renamed twice");
    await open(page, id);
    await openTab(page, "Alternatives");
    await expect(page.getByLabel("Name of alternative Renamed twice")).toBeVisible();
  });

  test("closing the tab with unsaved changes asks the browser to confirm", async ({ page, request }) => {
    // Headless Chromium does not surface the real beforeunload prompt to the test, so this checks
    // the application's side of the contract: the handler cancels the event exactly when the
    // project has unsaved changes. (The browser's own prompt was not observed.)
    const wouldPrompt = (): Promise<boolean> =>
      page.evaluate(() => {
        const e = new Event("beforeunload", { cancelable: true });
        window.dispatchEvent(e);
        return e.defaultPrevented;
      });
    const { id } = await freshProject(request);
    await open(page, id);
    expect(await wouldPrompt()).toBe(false);
    await renameFirstAlternative(page, "Not saved");
    expect(await wouldPrompt()).toBe(true);
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(saveState(page)).toHaveText("All changes saved");
    expect(await wouldPrompt()).toBe(false);
  });

  test("a clean project does not prompt when closed", async ({ page, request }) => {
    const { id } = await freshProject(request);
    await open(page, id);
    let seen = false;
    page.on("dialog", (d) => {
      seen = true;
      void d.dismiss();
    });
    await page.getByRole("button", { name: "← Projects" }).click();
    await expect(page.getByRole("heading", { name: "Projects", exact: true })).toBeVisible();
    expect(seen).toBe(false);
  });
});

test.describe("validation leads to the problem", () => {
  test("a missing measurement: the issue opens the cell and focuses it", async ({ page, request }) => {
    const { id } = await freshProject(request);
    await open(page, id);
    await openTab(page, "Measurements");
    const cell = page.getByLabel(`${FIRST_ALT} on Founder Expertise`, { exact: true });
    await cell.selectOption("");
    await expect(page.getByLabel("1 errors")).toBeVisible();
    await openTab(page, "Model");
    await page.locator(".issue-list button", { hasText: "MISSING_MEASUREMENT" }).click();
    await expect(tab(page, "Measurements")).toHaveAttribute("aria-selected", "true");
    await expect(cell).toBeFocused();
    await expect(page.locator("td.cell-error")).toHaveCount(1);
    // fixing it clears the error
    await cell.selectOption("High");
    await expect(page.getByLabel("0 errors")).toBeVisible();
  });

  test("a criterion without a scale: the issue selects it in the tree", async ({ page, request }) => {
    const { id } = await freshProject(request);
    await open(page, id);
    await openTab(page, "Model");
    await page.getByRole("button", { name: "Add top-level objective" }).click();
    await expect(page.getByLabel("Name", { exact: true })).toHaveValue("New criterion");
    // a criterion with no scale has no measurement type and no swing rating
    await expect(page.getByLabel("2 errors")).toBeVisible();
    await selectNode(page, "Team"); // move the selection and the tab elsewhere
    await openTab(page, "Alternatives");
    await page.locator(".issue-list button", { hasText: "MISSING_SCALE" }).first().click();
    await expect(tab(page, "Model")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByLabel("Name", { exact: true })).toHaveValue("New criterion");
  });

  test("an incomplete model can still be saved as a draft", async ({ page, request }) => {
    const { id } = await freshProject(request);
    await open(page, id);
    await openTab(page, "Measurements");
    await page.getByLabel(`${FIRST_ALT} on Founder Expertise`, { exact: true }).selectOption("");
    await expect(page.getByLabel("1 errors")).toBeVisible();
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(saveState(page)).toHaveText("All changes saved");
    const saved = JSON.parse((await storedFile(request, id)).toString()) as { performances: unknown[] };
    expect(saved.performances).toHaveLength(31); // 4 alternatives x 8 criteria = 32, one removed
  });
});

test.describe("destructive tree operations are confirmed and undoable", () => {
  test("adding a child to a measured criterion", async ({ page, request }) => {
    const { id } = await freshProject(request);
    await open(page, id);
    await selectNode(page, "Market Size");
    await expect(items(page)).toHaveCount(VC_NODES);

    // cancel: nothing changes
    await page.getByRole("button", { name: "Add child" }).click();
    await expect(dialog(page, "Turn a measured criterion into a group?")).toBeVisible();
    await dialog(page, "Turn a measured criterion into a group?").getByRole("button", { name: "Cancel" }).click();
    await expect(items(page)).toHaveCount(VC_NODES);
    await expect(saveState(page)).toHaveText("All changes saved");

    // confirm: it becomes a group, its measurements are gone
    await page.getByRole("button", { name: "Add child" }).click();
    await dialog(page, "Turn a measured criterion into a group?")
      .getByRole("button", { name: "Discard its data and add the child" })
      .click();
    await expect(items(page)).toHaveCount(VC_NODES + 1);
    await expect(saveState(page)).toHaveText("● Unsaved changes");
    await expect(page.getByRole("treeitem", { name: /Market Size/ }).first()).toHaveAttribute("aria-expanded", "true");
    await openTab(page, "Measurements");
    await expect(page.getByLabel(`${FIRST_ALT} on Market Size`, { exact: true })).toHaveCount(0);

    // undo brings everything back, and the project is clean again
    await page.getByRole("button", { name: "Undo" }).click();
    await expect(saveState(page)).toHaveText("All changes saved");
    await expect(page.getByLabel(`${FIRST_ALT} on Market Size`, { exact: true })).toBeVisible();
    await openTab(page, "Model");
    await expect(items(page)).toHaveCount(VC_NODES);
  });

  test("removing a group removes its sub-items after confirmation", async ({ page, request }) => {
    const { id } = await freshProject(request);
    await open(page, id);
    await selectNode(page, "Team");
    await page.getByRole("button", { name: "Remove", exact: true }).click();
    const d = dialog(page, "Remove criterion");
    await expect(d).toContainText("Team");
    await expect(d).toContainText("2 sub-item(s)");
    await expect(d).toContainText("entered measurement(s)");
    await d.getByRole("button", { name: "Cancel" }).click();
    await expect(items(page)).toHaveCount(VC_NODES);

    await page.getByRole("button", { name: "Remove", exact: true }).click();
    await dialog(page, "Remove criterion").getByRole("button", { name: "Remove", exact: true }).click();
    await expect(items(page)).toHaveCount(VC_NODES - 3);
    await expect(treeItem(page, "Team")).toHaveCount(0);
    await expect(saveState(page)).toHaveText("● Unsaved changes");

    await page.getByRole("button", { name: "Undo" }).click();
    await expect(items(page)).toHaveCount(VC_NODES);
    await expect(saveState(page)).toHaveText("All changes saved");
    await page.getByRole("button", { name: "Redo" }).click();
    await expect(items(page)).toHaveCount(VC_NODES - 3);
  });

  test("removing an alternative removes its measurements and can be undone", async ({ page, request }) => {
    const { id } = await freshProject(request);
    await open(page, id);
    await openTab(page, "Alternatives");
    await page.getByRole("button", { name: `Remove ${FIRST_ALT}` }).click();
    await expect(dialog(page, "Remove alternative")).toContainText("8 entered measurement(s)");
    await dialog(page, "Remove alternative").getByRole("button", { name: "Remove", exact: true }).click();
    await expect(page.getByRole("table", { name: "Alternatives" }).locator("tbody tr")).toHaveCount(3);
    await page.getByRole("button", { name: "Undo" }).click();
    await expect(page.getByRole("table", { name: "Alternatives" }).locator("tbody tr")).toHaveCount(4);
    await expect(saveState(page)).toHaveText("All changes saved");
  });
});

test.describe("project list", () => {
  test("duplicate gives an independent copy; delete moves the file to the trash", async ({ page, request }) => {
    const { id, title } = await freshProject(request);
    await page.goto("/");
    await page.getByRole("button", { name: `Duplicate ${title}` }).click();
    const copyTitle = `${title} (copy)`;
    await expect(page.getByRole("button", { name: `Open ${copyTitle}` })).toBeVisible();

    // the original is untouched
    expect(JSON.parse((await storedFile(request, id)).toString()) as Raw).toMatchObject({ title });

    await page.getByRole("button", { name: `Delete ${copyTitle}` }).click();
    await expect(dialog(page, "Delete project")).toContainText(copyTitle);
    await dialog(page, "Delete project").getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.getByRole("button", { name: `Open ${copyTitle}` })).toHaveCount(0);
    await expect(page.getByRole("button", { name: `Open ${title}` })).toBeVisible();

    const trash = resolve(STORE, ".trash");
    expect(existsSync(trash)).toBe(true);
    const trashed = readdirSync(trash).filter((f) => readFileSync(resolve(trash, f), "utf8").includes(copyTitle));
    expect(trashed).toHaveLength(1);
  });
});

test.describe("saved elsewhere first", () => {
  /** Another program saves a different version of the project while the editor has it open. */
  async function saveElsewhere(request: APIRequestContext, id: string, title: string): Promise<void> {
    const current = JSON.parse((await storedFile(request, id)).toString()) as Raw;
    const r = await request.put(`/api/projects/${id}`, { data: { ...current, title } });
    expect(r.ok()).toBeTruthy();
  }

  test("saving is refused, nothing is overwritten, and the editor keeps the user's work", async ({ page, request }) => {
    const { id } = await freshProject(request);
    await open(page, id);
    await renameFirstAlternative(page, "My edit");
    await saveElsewhere(request, id, "Changed by someone else");
    const theirs = await storedFile(request, id);

    await page.getByRole("button", { name: "Save", exact: true }).click();
    const d = dialog(page, "This project was changed elsewhere");
    await expect(d).toBeVisible();
    expect((await storedFile(request, id)).equals(theirs)).toBe(true);

    await d.getByRole("button", { name: "Keep editing" }).click();
    await expect(saveState(page)).toHaveText("● Unsaved changes");
    await openTab(page, "Alternatives");
    await expect(page.getByLabel("Name of alternative My edit")).toBeVisible();
  });

  test("'save mine as a copy' keeps both versions", async ({ page, request }) => {
    const { id } = await freshProject(request);
    await open(page, id);
    await renameFirstAlternative(page, "My edit");
    await saveElsewhere(request, id, "Changed by someone else");
    const theirs = await storedFile(request, id);

    await page.getByRole("button", { name: "Save", exact: true }).click();
    await dialog(page, "This project was changed elsewhere")
      .getByRole("button", { name: "Save mine as a separate copy" })
      .click();
    await expect.poll(() => page.url()).not.toContain(id);
    await expect(saveState(page)).toHaveText("All changes saved");
    await openTab(page, "Alternatives");
    await expect(page.getByLabel("Name of alternative My edit")).toBeVisible();
    expect((await storedFile(request, id)).equals(theirs)).toBe(true);
  });

  test("'reload' discards the user's draft and shows the other version", async ({ page, request }) => {
    const { id } = await freshProject(request);
    await open(page, id);
    await renameFirstAlternative(page, "My edit");
    await saveElsewhere(request, id, "Changed by someone else");

    await page.getByRole("button", { name: "Save", exact: true }).click();
    await dialog(page, "This project was changed elsewhere")
      .getByRole("button", { name: "Reload and discard my changes" })
      .click();
    await expect(page.getByRole("heading", { level: 1, name: "Changed by someone else" })).toBeVisible();
    await expect(saveState(page)).toHaveText("All changes saved");
    await openTab(page, "Alternatives");
    await expect(page.getByLabel(`Name of alternative ${FIRST_ALT}`)).toBeVisible();
  });
});
