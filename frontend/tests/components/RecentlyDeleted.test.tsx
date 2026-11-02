import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { api, ApiError } from "../../src/api/client";
import type { ProjectDocument, TrashEntry } from "../../src/api/types";
import { RecentlyDeleted } from "../../src/components/RecentlyDeleted";

const entry: TrashEntry = { entry: "p.20261026T000000000000Z.json", project_id: "p", title: "My decision",
  deleted_at: "2026-10-26T00:00:00Z", readable: true, conflict: false, error: null };
afterEach(() => vi.restoreAllMocks());

it("restores through the API and refreshes active projects, while explaining retained recovery", async () => {
  vi.spyOn(api, "listTrash").mockResolvedValue([entry]);
  const restore = vi.spyOn(api, "restoreProject").mockResolvedValue({ project: { title: "My decision" } } as ProjectDocument);
  const refresh = vi.fn(); const user = userEvent.setup();
  render(<RecentlyDeleted reloadKey={0} onRestored={refresh} />);
  await user.click(screen.getByText(/Recently deleted/));
  await user.click(await screen.findByRole("button", { name: "Restore My decision" }));
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  expect(restore).toHaveBeenCalledExactlyOnceWith(entry.entry, false);
  expect(await screen.findByRole("status")).toHaveTextContent("recovery entry is retained");
});

it("offers copy for a conflicting ID and keeps unreadable entries visible", async () => {
  vi.spyOn(api, "listTrash").mockResolvedValue([{ ...entry, conflict: true },
    { ...entry, entry: "broken.json", title: null, readable: false, error: "Malformed JSON" }]);
  const restore = vi.spyOn(api, "restoreProject").mockResolvedValue({ project: { title: "My decision" } } as ProjectDocument);
  const user = userEvent.setup(); render(<RecentlyDeleted reloadKey={0} onRestored={vi.fn()} />);
  await user.click(screen.getByText(/Recently deleted/));
  expect(await screen.findByText("Unreadable: Malformed JSON")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Restore broken.json" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Restore as copy My decision" }));
  await waitFor(() => expect(restore).toHaveBeenCalledWith(entry.entry, true));
});

it("shows a raced ID conflict and refreshes the available copy action without dropping recovery data", async () => {
  vi.spyOn(api, "listTrash").mockResolvedValueOnce([entry]).mockResolvedValue([{ ...entry, conflict: true }]);
  vi.spyOn(api, "restoreProject").mockRejectedValue(new ApiError(409, "PROJECT_EXISTS", "ID exists; restore as copy"));
  const refresh = vi.fn(); const user = userEvent.setup();
  render(<RecentlyDeleted reloadKey={0} onRestored={refresh} />);
  await user.click(screen.getByText(/Recently deleted/));
  await user.click(await screen.findByRole("button", { name: "Restore My decision" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("ID exists; restore as copy");
  expect(await screen.findByRole("button", { name: "Restore as copy My decision" })).toBeVisible();
  expect(refresh).not.toHaveBeenCalled();
});
