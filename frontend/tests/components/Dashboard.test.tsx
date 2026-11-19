import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { StarterTemplate } from "../../src/api/types";
import { Dashboard } from "../../src/components/Dashboard";
import catalogJSON from "../fixtures/starter-catalog.json";

const catalog = catalogJSON as StarterTemplate[];
afterEach(() => vi.restoreAllMocks());

function mocks(starters: StarterTemplate[] = catalog) {
  vi.spyOn(api, "listProjects").mockResolvedValue({ projects: [], unreadable: [] });
  vi.spyOn(api, "starterTemplates").mockResolvedValue(starters);
  vi.spyOn(api, "listTrash").mockResolvedValue([]);
}
const cards = () => screen.getAllByRole("button", { name: /^Start from / }).map(card => card.getAttribute("aria-label"));

it("leads with a blank model, then the general examples, and puts the venture studies last", async () => {
  mocks(); render(<Dashboard onOpen={vi.fn()} />);
  await screen.findByRole("button", { name: "Start from Blank" });
  expect(cards()).toEqual([
    "Start from Blank",
    "Start from Supplier selection",
    "Start from Infrastructure procurement",
    "Start from Clinic site selection",
    "Start from Flood defence options",
    "Start from Engineering trade study",
    "Start from Venture screening",
    "Start from Venture screening: evidence and model workflows (invented data)",
  ]);
});

it("puts a starter the gallery does not list after every listed one, in the gallery's own order", async () => {
  const blank = catalog.find(t => t.id === "blank");
  if (!blank) throw Error("Blank starter missing from the fixture");
  mocks([{ ...blank, id: "zz_unlisted", title: "Unlisted" }, ...catalog, { ...blank, id: "aa_unlisted", title: "Another unlisted" }]);
  render(<Dashboard onOpen={vi.fn()} />);
  await waitFor(() => expect(cards()).toHaveLength(catalog.length + 2));
  expect(cards().slice(0, 2)).toEqual(["Start from Blank", "Start from Supplier selection"]);
  expect(cards().slice(-2)).toEqual(["Start from Unlisted", "Start from Another unlisted"]);
});

it("gives each new example its own icon and tagline, never the blank starter's plus sign", async () => {
  mocks(); render(<Dashboard onOpen={vi.fn()} />);
  await screen.findByRole("button", { name: "Start from Blank" });
  const path = (title: string) => screen.getByRole("button", { name: `Start from ${title}` }).querySelector("svg path")?.getAttribute("d");
  const blank = path("Blank"), icons = new Set([blank]);
  for (const title of ["Clinic site selection", "Flood defence options", "Engineering trade study"]) {
    const icon = path(title); expect(icon).toBeTruthy(); expect(icon).not.toBe(blank); icons.add(icon);
  }
  expect(icons.size).toBe(4);
  expect(screen.getByRole("button", { name: "Start from Clinic site selection" })).toHaveTextContent("Pairwise judgements and swing weights");
  expect(screen.getByRole("button", { name: "Start from Flood defence options" })).toHaveTextContent("A hard requirement and outranking flows");
  expect(screen.getByRole("button", { name: "Start from Engineering trade study" })).toHaveTextContent("Every method on one model");
});
