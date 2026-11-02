import { expect, test } from "@playwright/test";

test("Projects restores deleted models, offers copies on ID conflicts and preserves recovery entries", async ({ page, request }) => {
  const doc = await (await request.post("/api/projects", { data: { title: "C1 recovery decision" } })).json() as { project: { id: string }; fingerprint: string };
  const id = doc.project.id;
  await request.delete(`/api/projects/${id}`);
  await page.goto("/");
  await page.getByText(/^Recently deleted/).click();
  await page.getByRole("button", { name: "Restore C1 recovery decision", exact: true }).click();
  await expect(page.getByRole("button", { name: "Open C1 recovery decision", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Recently deleted" })).toContainText("recovery entry is retained");
  const reopened = await (await request.get(`/api/projects/${id}`)).json() as { fingerprint: string };
  expect(reopened.fingerprint).toBe(doc.fingerprint);
  await page.getByRole("button", { name: "Restore as copy C1 recovery decision", exact: true }).click();
  await expect(page.getByRole("button", { name: "Open C1 recovery decision", exact: true })).toHaveCount(2);
  await page.getByRole("button", { name: "Open C1 recovery decision", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "C1 recovery decision", exact: true })).toBeVisible();
});
