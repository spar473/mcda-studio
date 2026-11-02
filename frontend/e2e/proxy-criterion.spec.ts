import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ProxyInputs, ProxyComparisonBundle } from "../src/api/types";
import { openTab, REPO, storedFile } from "./helpers";

test("proxy comparison: exact API pair, both exports, questions and unchanged baseline",async({page,request},testInfo)=>{
  const source=resolve(REPO,"frontend/tests/fixtures/proxy-inputs.json");
  const inputs=JSON.parse(readFileSync(source,"utf8")) as ProxyInputs;
  const imported=await request.post("/api/projects/import",{data:inputs.project});expect([201,409]).toContain(imported.status());
  const before=await storedFile(request,inputs.project.id);
  await page.goto(`/#/p/${inputs.project.id}`);await openTab(page,"Compare");
  const panel=page.getByRole("region",{name:"Disclosed model proxy comparison",exact:true});
  await expect(panel.getByRole("checkbox",{name:"Enable separate proxy preview"})).toHaveCount(0);
  await panel.getByLabel("Open proxy inputs",{exact:true}).setInputFiles(source);
  await panel.getByRole("button",{name:"Inspect both proxy copies",exact:true}).click();
  await expect(panel.getByText("Before and after normalized weight shares",{exact:true})).toBeVisible();
  await panel.getByLabel("Proxy reviewer",{exact:true}).fill("Local reviewer");
  await panel.getByLabel("Proxy review reason",{exact:true}).fill("Review both disclosed copies with stated tradeoffs");
  const run=panel.getByRole("button",{name:"Run with and without disclosed proxy",exact:true});
  await expect(run).toBeDisabled();
  for(const name of ["I acknowledge card","I acknowledge overlap","I acknowledge weight changes"]){await panel.getByLabel(name,{exact:true}).check();}
  await run.click();
  const pair=panel.getByRole("region",{name:"Complete proxy pair",exact:true});await expect(pair).toBeVisible();
  await expect(pair.getByRole("heading",{name:"Without disclosed proxy",exact:true})).toBeVisible();
  await expect(pair.getByRole("heading",{name:"With disclosed proxy",exact:true})).toBeVisible();
  const event=page.waitForEvent("download");await pair.getByRole("button",{name:"Export complete proxy pair",exact:true}).click();
  const file=await(await event).path();if(!file)throw Error("No paired export");
  const bundle=JSON.parse(readFileSync(file,"utf8")) as ProxyComparisonBundle;
  const same=await request.post("/api/proxy/run-pair",{data:bundle.request});expect(same.status()).toBe(200);expect(await same.json()).toEqual(bundle);
  expect(bundle.without_proxy.project).toEqual(inputs.project);expect(bundle.without_proxy.result?.ranking.map(r=>r.value)).toEqual([.5,.5]);
  expect(bundle.with_proxy.result?.ranking.map(r=>r.value)).toEqual([.625,.375]);
  expect((await storedFile(request,inputs.project.id)).equals(before)).toBe(true);
  const reopen=await request.post("/api/proxy/verify",{data:{document:bundle}});expect(reopen.status()).toBe(200);expect(await reopen.json()).toEqual(bundle);
  await page.screenshot({path:testInfo.outputPath("proxy-pair.png")});
  await openTab(page,"Open Questions");await expect(page.getByRole("region",{name:"Open Questions",exact:true})).toContainText("Optional disclosed proxy card");
  await openTab(page,"Compare");await expect(pair).toBeVisible();
});

test("proxy declaration starts disabled and requires explicit profile swing judgements",async({page,request})=>{
  const inputs=JSON.parse(readFileSync(resolve(REPO,"frontend/tests/fixtures/proxy-inputs.json"),"utf8")) as ProxyInputs;
  await request.post("/api/projects/import",{data:inputs.project});
  await page.goto(`/#/p/${inputs.project.id}`);await openTab(page,"Compare");
  const panel=page.getByRole("region",{name:"Disclosed model proxy comparison",exact:true});
  await panel.getByRole("button",{name:"Prepare an optional proxy declaration",exact:true}).click();
  const state=JSON.parse(await panel.getByLabel("Proxy declaration JSON").inputValue()) as {enabled:boolean;swing_ratings:Record<string,number|null>};
  expect(state.enabled).toBe(false);expect(Object.values(state.swing_ratings)).toEqual([null,null]);
  await panel.getByRole("button",{name:"Create disabled proxy plan",exact:true}).click();
  await panel.getByRole("button",{name:"Inspect both proxy copies",exact:true}).click();
  await expect(panel).toContainText("explicitly rate every compared profile");
  await expect(panel.getByRole("button",{name:"Run with and without disclosed proxy",exact:true})).toBeDisabled();
  await expect(page.getByText("● Unsaved changes",{exact:true})).toBeVisible();
});

test("proxy preference cannot hide failed feasibility and its browser export fully replays",async({page,request},testInfo)=>{
  const source=resolve(REPO,"frontend/tests/fixtures/proxy-feasibility-inputs.json");
  const inputs=JSON.parse(readFileSync(source,"utf8")) as ProxyInputs;
  const imported=await request.post("/api/projects/import",{data:inputs.project});expect([201,409]).toContain(imported.status());
  const before=await storedFile(request,inputs.project.id);
  await page.goto(`/#/p/${inputs.project.id}`);await openTab(page,"Compare");
  const panel=page.getByRole("region",{name:"Disclosed model proxy comparison",exact:true});
  await panel.getByLabel("Open proxy inputs",{exact:true}).setInputFiles(source);
  await panel.getByRole("button",{name:"Inspect both proxy copies",exact:true}).click();
  await expect(panel.getByText("Before and after normalized weight shares",{exact:true})).toBeVisible();
  await panel.getByLabel("Proxy reviewer",{exact:true}).fill("Local reviewer");
  await panel.getByLabel("Proxy review reason",{exact:true}).fill("Preference cannot offset a mandatory failed requirement");
  for(const name of ["I acknowledge card","I acknowledge overlap","I acknowledge weight changes"]){await panel.getByLabel(name,{exact:true}).check();}
  await panel.getByRole("button",{name:"Run with and without disclosed proxy",exact:true}).click();
  const pair=panel.getByRole("region",{name:"Complete proxy pair",exact:true});await expect(pair).toBeVisible();
  for(const title of ["Without disclosed proxy ranking","With disclosed proxy ranking"]){
    const table=pair.getByRole("table",{name:title,exact:true});
    await expect(table.locator('[data-feasibility="fail"]')).toBeVisible();
    await expect(table.locator('[data-feasibility="pass"]')).toBeVisible();
  }
  await expect(pair.getByRole("table",{name:"With disclosed proxy ranking",exact:true}).getByRole("row").nth(2)).toContainText("Option B");
  const event=page.waitForEvent("download");await pair.getByRole("button",{name:"Export complete proxy pair",exact:true}).click();
  const file=await(await event).path();if(!file)throw Error("No feasibility pair export");
  const bundle=JSON.parse(readFileSync(file,"utf8")) as ProxyComparisonBundle;
  expect(bundle.with_proxy.result?.ranking[0]?.alternative_id).toBe("b");
  const verified=await request.post("/api/proxy/verify",{data:{document:bundle}});expect(verified.status()).toBe(200);expect(await verified.json()).toEqual(bundle);
  expect((await storedFile(request,inputs.project.id)).equals(before)).toBe(true);
  await page.screenshot({path:testInfo.outputPath("proxy-feasibility.png")});
});
