import { expect, test, type Page, type Request } from "@playwright/test";
import { openTab, storedFile } from "./helpers";

const projectId = "nz_venture_screening_study";
const analystTabs = ["Results", "Sensitivity", "Compare", "Reference cases", "Evidence", "Open Questions", "Decision"];
const pendingWords = /^(Checking|Calculating|Preparing|Finding|Running|Resolving|Loading|Deriving|Probing|Evaluating|Inspecting)\b/i;

/** Includes rendered SVG/text and painted form values. Native ranges paint no numeric value; their visible labels and aria-valuetext are checked instead. */
async function primaryState(page: Page) {
  return page.evaluate(() => {
    const rendered = (element: Element) => {
      if (element.closest("script,style,metadata,defs,title,desc,[hidden],[inert]")) return false;
      for (let parent: Element | null = element; parent; parent = parent.parentElement) {
        const style = getComputedStyle(parent);
        if (style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse") return false;
        if (parent instanceof HTMLDetailsElement && !parent.open && !parent.querySelector(":scope > summary")?.contains(element)) return false;
      }
      return element.getClientRects().length > 0;
    };
    const text: string[] = [], walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node: Node | null;
    while ((node = walker.nextNode())) {
      if (node.parentElement && node.nodeValue?.trim() && rendered(node.parentElement)) text.push(node.nodeValue.trim());
    }
    for (const element of document.querySelectorAll("input,textarea,select")) {
      if (!rendered(element)) continue;
      if (element instanceof HTMLInputElement && !["file", "hidden", "checkbox", "radio", "range"].includes(element.type)) text.push(element.value);
      else if (element instanceof HTMLInputElement && element.type === "range" && element.getAttribute("aria-valuetext")) text.push(element.getAttribute("aria-valuetext") ?? "");
      else if (element instanceof HTMLTextAreaElement) text.push(element.value);
      else if (element instanceof HTMLSelectElement) text.push([...element.selectedOptions].map(option => option.text).join(" "));
    }
    const main = document.querySelector(".tabpanel");
    const alerts = [...document.querySelectorAll(".banner.warning,.banner.error,[role=alert]")].filter(rendered).map(element => element.textContent.trim());
    return { text: text.join("\n"), overflow: main ? main.scrollWidth - main.clientWidth : 0, alerts };
  });
}

async function settled(page: Page, pending: Set<Request>, tab?: string) {
  // Requests are debounced; a quiet network before that timer starts is not a completed view.
  await page.waitForTimeout(200);
  await expect.poll(() => pending.size, { timeout: 30_000 }).toBe(0);
  await expect.poll(async () => page.getByRole("status").evaluateAll((nodes, source) => {
    const pattern = new RegExp(source, "i");
    return nodes.filter(node => node.getClientRects().length && !node.closest("[hidden],[inert]")).some(node => pattern.test(node.textContent.trim()));
  }, pendingWords.source), { timeout: 30_000 }).toBe(false);
  if (tab === "Sensitivity") {
    await expect(page.locator(".selected-weight-path")).toBeVisible();
    await expect(page.getByRole("table", { name: "Sensitivity values", exact: true })).toBeVisible();
  } else if (tab === "Compare") await expect(page.getByRole("table", { name: "Methods side by side", exact: true })).toBeVisible();
  else if (tab === "Open Questions") await expect(page.getByRole("heading", { name: "Upstock", exact: true })).toBeVisible();
  else if (tab === "Results") await expect(page.getByRole("table", { name: "Screening summary", exact: true })).toBeVisible();
}

test("rendered-text walker includes painted diagnostics and SVG while excluding only non-rendered content", async ({ page }) => {
  await page.setContent(`<main class="tabpanel"><p>VISIBLE_CODE</p><p hidden>HIDDEN_CODE</p><div inert>INERT_CODE</div>
    <div style="display:none">DISPLAY_CODE</div><div style="visibility:hidden">VISIBILITY_CODE</div>
    <details><summary>Closed caption</summary><p>CLOSED_CODE</p></details>
    <details open><summary>Open caption</summary><p>OPEN_CODE</p></details><div role="tooltip">POPOVER_CODE</div>
    <svg width="200" height="40"><defs><text>DEFS_CODE</text></defs><metadata>METADATA_CODE</metadata><text y="20">SVG_CODE</text></svg>
    <input value="INPUT_CODE"><textarea>TEXTAREA_CODE</textarea><select><option>SELECTED_CODE</option><option>OTHER_CODE</option></select>
    <input type="range" value="0.123456789" aria-valuetext="Rounded range label"></main>`);
  const state = await primaryState(page);
  for (const value of ["VISIBLE_CODE", "OPEN_CODE", "POPOVER_CODE", "SVG_CODE", "INPUT_CODE", "TEXTAREA_CODE", "SELECTED_CODE", "Rounded range label", "Closed caption"])
    expect(state.text).toContain(value);
  for (const value of ["HIDDEN_CODE", "INERT_CODE", "DISPLAY_CODE", "VISIBILITY_CODE", "CLOSED_CODE", "DEFS_CODE", "METADATA_CODE", "OTHER_CODE", "0.123456789"])
    expect(state.text).not.toContain(value);
});

test("clean worked study: every workspace view stays readable and read-only", async ({ page, request }) => {
  test.setTimeout(180_000); await page.setViewportSize({ width: 1440, height: 900 });
  expect(await page.evaluate(() => window.devicePixelRatio)).toBe(1);
  const messages: string[] = [], failedHttp: string[] = [], pending = new Set<Request>();
  page.on("console", message => { if (["warning", "error"].includes(message.type())) messages.push(message.text()); });
  page.on("pageerror", error => messages.push(error.message));
  page.on("response", response => { if (response.status() >= 400) failedHttp.push(`${response.status()} ${response.url()}`); });
  page.on("request", value => { if (value.url().includes("/api/")) pending.add(value); });
  page.on("requestfinished", value => pending.delete(value)); page.on("requestfailed", value => pending.delete(value));
  await page.addInitScript(id => sessionStorage.setItem(`mcda:editor-view:${id}`, "builder"), projectId);
  await page.goto("/");
  await page.getByRole("button", { name: "Start from Venture screening", exact: true }).click();
  await page.getByRole("button", { name: "Open worked example — Venture screening", exact: true }).click();
  await expect(page.getByRole("button", { name: "Analyst view", exact: true })).toHaveAttribute("aria-pressed", "true");
  expect(await page.getByRole("tab").allTextContents()).toEqual(analystTabs);
  const before = await request.get(`/api/projects/${projectId}`), beforeBody: unknown = await before.json(), file = await storedFile(request, projectId);
  const writes: string[] = [];
  page.on("request", value => {
    if (value.url().endsWith("/api/edit") || ["PUT", "DELETE"].includes(value.method()) && value.url().includes(`/api/projects/${projectId}`)) writes.push(value.url());
  });

  async function check(label: string) {
    await settled(page, pending);
    const state = await primaryState(page);
    const patterns = {
      codes: /\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b/g,
      decimals: /\b\d\.\d{7,}\b/g,
      hashes: /\b[0-9a-f]{24,}\b/g,
      lists: /\[['"][^\]]*['"]\]/g,
      claims: /\b[a-z]+__[a-z_]+\b/g,
      scientific: /\b\d(?:\.\d+)?e[+-]?\d+\b/gi,
      validation: /\bvalidation errors?\b/gi,
    };
    for (const [kind, expression] of Object.entries(patterns)) {
      expect([...state.text.matchAll(expression)].map(match => match[0]), `CLEAN_DEMO primary text: ${label}, ${kind}`).toEqual([]);
    }
    expect(state.overflow, `CLEAN_DEMO main overflow: ${label}`).toBeLessThanOrEqual(1);
    expect(state.alerts, `CLEAN_DEMO visible warnings or errors: ${label}`).toEqual([]);
    expect(state.text, `CLEAN_DEMO unexpected swing review: ${label}`).not.toContain("Preference ranges changed");
    expect(messages, `CLEAN_DEMO browser messages: ${label}`).toEqual([]);
    expect(failedHttp, `CLEAN_DEMO failed HTTP: ${label}`).toEqual([]);
  }

  for (const tab of analystTabs) { await openTab(page, tab); await settled(page, pending, tab); await check(`Analyst ${tab}`); }
  await page.getByRole("button", { name: "Builder view", exact: true }).click();
  const builderTabs = await page.getByRole("tab").allTextContents();
  for (const tab of builderTabs) { await openTab(page, tab); await settled(page, pending, tab); await check(`Builder ${tab}`); }
  await page.getByRole("button", { name: "Analyst view", exact: true }).click(); await openTab(page, "Results");
  for (const profile of ["commercial_traction", "technical_ip"]) {
    await page.getByLabel("Weight profile", { exact: true }).selectOption(profile);
    for (const tab of ["Results", "Sensitivity", "Compare", "Open Questions"]) {
      await openTab(page, tab); await settled(page, pending, tab); await check(`Profile ${profile}: ${tab}`);
    }
  }
  for (const scenario of ["linear_market_size", ""]) {
    await page.getByLabel("Scenario", { exact: true }).selectOption(scenario);
    for (const tab of ["Results", "Sensitivity", "Compare", "Open Questions"]) {
      await openTab(page, tab); await settled(page, pending, tab); await check(`Scenario ${scenario || "Base"}: ${tab}`);
    }
  }
  await openTab(page, "Results");
  for (const method of ["mavt", "mavt_sorting", "smaa2", "promethee2"]) {
    await page.getByLabel("Method", { exact: true }).selectOption(method);
    const label = method === "smaa2" ? "Rank acceptability" : method === "promethee2" ? "Outranking flows" : "Screening summary";
    await expect(page.getByRole("table", { name: label, exact: true })).toBeVisible(); await check(`Results ${method}`);
    if (method === "mavt" || method === "mavt_sorting") {
      await page.getByLabel("Results precision", { exact: true }).selectOption("full"); await check(`Full SVG precision ${method}`);
    }
  }
  const ahp = page.getByRole("option", { name: "AHP (pairwise priorities): not set up for this study", exact: true });
  await expect(ahp).toHaveAttribute("disabled", "");
  expect(await ahp.evaluate(option => (option as HTMLOptionElement).disabled)).toBe(true);
  await page.getByLabel("Method", { exact: true }).selectOption("mavt_sorting"); await settled(page, pending, "Results");
  for (const company of ["Upstock", "Hnry"]) {
    const opener = page.getByRole("table", { name: "Screening summary", exact: true }).getByRole("button", { name: company, exact: true });
    await opener.focus(); await page.keyboard.press("Space");
    const drawer = page.getByRole("dialog", { name: company, exact: true });
    await expect(drawer.getByRole("region", { name: "Alternative contributions", exact: true }).locator("li")).toHaveCount(16);
    if (company === "Upstock") {
      await drawer.getByRole("button", { name: "Load the study's evidence", exact: true }).click();
      await expect(drawer.getByRole("region", { name: "Alternative ratings and sources", exact: true }).getByText("No verified evidence dossier is loaded.")).toHaveCount(0);
    } else await expect(drawer.getByRole("region", { name: "Alternative requirements", exact: true })).toContainText("Series B or later");
    await check(`Drawer ${company}`); await page.keyboard.press("Escape"); await expect(drawer).toHaveCount(0);
    // Loading a dossier replaces the summary request and removes its original opener.
    // The modal's documented fallback is the selected tab; stable openers regain focus.
    if (company === "Upstock") await expect(page.getByRole("tab", { name: "Results", exact: true })).toBeFocused();
    else await expect(opener).toBeFocused();
  }
  await openTab(page, "Evidence");
  await expect(page.getByLabel("Evidence claims", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Disputed", exact: true }).click(); await check("Disputed evidence");
  const claims = page.getByLabel("Evidence claims", { exact: true });
  for (const name of ["Kea Aerospace", "Scentian Bio"]) {
    const company = claims.locator(":scope > section").filter({ has: page.getByRole("heading", { name, exact: true }) });
    const disclosure = company.locator(":scope > details");
    if (await disclosure.getAttribute("open") === null) await disclosure.locator(":scope > summary").click();
    await expect(company.locator("li[data-claim-id]")).toHaveCount(2); await check(`Disputed ${name}`);
  }
  await openTab(page, "Results"); await settled(page, pending, "Results");
  const partnerHeaderProfile = await page.getByLabel("Weight profile", { exact: true }).inputValue();
  await page.getByRole("checkbox", { name: "Compare profiles", exact: true }).check();
  const partners = page.getByRole("region", { name: "Profile comparison", exact: true });
  await expect(partners.getByRole("table", { name: "Profile rankings and movements", exact: true }).locator("tbody tr")).toHaveCount(8);
  await check("Profile comparison");
  const rightEndpoint = partners.locator('g[data-company-id="hnry"] > g[role="button"]').last();
  await rightEndpoint.focus(); await page.keyboard.press("Space");
  const partnerDrawer = page.getByRole("dialog", { name: "Hnry", exact: true });
  await expect(partnerDrawer.getByRole("region", { name: "Alternative contributions", exact: true }).locator("li")).toHaveCount(16);
  await expect(partnerDrawer).toContainText("Commercial/traction-led");
  await expect(page.getByLabel("Weight profile", { exact: true })).toHaveValue(partnerHeaderProfile);
  await check("Partner endpoint drawer"); await page.keyboard.press("Escape"); await expect(partnerDrawer).toHaveCount(0);
  await partners.getByRole("button", { name: "Swap profiles", exact: true }).click();
  await expect(partners.getByLabel("Left profile", { exact: true })).toHaveValue("commercial_traction");
  await expect(partners.getByRole("table").getByRole("columnheader").nth(1)).toContainText("Commercial/traction-led");
  await check("Swapped partner profiles");
  await page.getByRole("checkbox", { name: "Compare profiles", exact: true }).uncheck();
  await page.getByText("What-if weights", { exact: true }).click();
  const teamTrial = page.getByRole("slider", { name: "What-if Team", exact: true }); await expect(teamTrial).toBeVisible();
  await teamTrial.focus(); await page.keyboard.press("Home");
  await settled(page, pending, "Results");
  await expect(page.getByText("Open-question counts reflect the saved weights", { exact: true })).toBeVisible();
  const trialSummary = page.getByRole("table", { name: "Screening summary", exact: true });
  await expect(trialSummary.getByRole("columnheader", { name: "Open questions", exact: true })).toHaveCount(0);
  await expect(trialSummary.getByRole("button", { name: "Upstock", exact: true })).toBeDisabled();
  await expect(page.getByRole("region", { name: "Profile comparison", exact: true })).toHaveCount(0);
  await expect(page.getByText("Compare profiles: Reset what-if to use this", { exact: true })).toBeVisible();
  for (const button of await page.getByRole("button", { name: /^Download / }).all()) if (await button.isVisible()) await expect(button).toBeDisabled();
  await check("What-if screening and blocked controls");
  await openTab(page, "Sensitivity");
  await expect(page.getByText("Reset what-if to use this", { exact: true })).toBeVisible(); await expect(page.locator(".selected-weight-path")).toHaveCount(0);
  await check("What-if blocks Sensitivity");
  await openTab(page, "Results"); await settled(page, pending, "Results");
  await page.getByRole("button", { name: "Reset", exact: true }).click(); await settled(page, pending, "Results");
  await expect(trialSummary.getByRole("columnheader", { name: "Open questions", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download ranking SVG", exact: true })).toBeEnabled();
  await check("Reset saved screening"); await page.getByText("What-if weights", { exact: true }).click();
  await openTab(page, "Sensitivity"); await settled(page, pending, "Sensitivity");
  await page.getByRole("list", { name: "Exact crossovers", exact: true }).getByRole("button").first().click();
  await settled(page, pending, "Sensitivity");
  await expect(page.getByText(/tied/i).first()).toBeVisible(); await check("Exact tied probe");

  const after = await request.get(`/api/projects/${projectId}`);
  expect(await after.json(), "CLEAN_DEMO stored project").toEqual(beforeBody);
  expect(after.headers().etag, "CLEAN_DEMO ETag").toBe(before.headers().etag);
  expect((await storedFile(request, projectId)).equals(file), "CLEAN_DEMO stored bytes").toBe(true);
  await expect(page.getByTestId("save-state")).toHaveText("All changes saved");
  await expect(page.getByRole("button", { name: "Undo", exact: true })).toBeDisabled();
  expect(writes, "CLEAN_DEMO write requests").toEqual([]);
  expect(messages, "CLEAN_DEMO browser messages").toEqual([]); expect(failedHttp, "CLEAN_DEMO failed HTTP").toEqual([]);
});
