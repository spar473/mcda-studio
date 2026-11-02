import { expect, test, type Page, type APIRequestContext } from "@playwright/test";
import { resolve } from "node:path";
import type { Project } from "../src/api/types";
import { VC_FILE, REPO, openTab, readJson, saveState, storedFile } from "./helpers";

async function load(page:Page,request:APIRequestContext,id:string,infra=false){
  const p=readJson(infra?resolve(REPO,"examples/infrastructure_procurement/project.json"):VC_FILE) as Project;p.id=id;
  expect((await request.post("/api/projects/import",{data:p})).status()).toBe(201);
  await page.goto(`/#/p/${id}`);await openTab(page,"Scenarios");return p;
}
async function named(page:Page,action:string,name:string){
  await page.getByRole("button",{name:action,exact:true}).click();await page.getByLabel("Scenario name",{exact:true}).fill(name);
  await page.getByRole("button",{name:"Confirm scenario change"}).click();await expect(page.getByRole("dialog")).toHaveCount(0);
}
async function apply(page:Page){const d=page.getByRole("dialog");await expect(d.getByText("Function ready",{exact:true})).toBeVisible();await d.getByLabel("Acknowledge candidate range change").check();await d.getByRole("button",{name:"Apply candidate"}).click();await expect(d).toHaveCount(0);}
async function save(page:Page){await page.getByRole("button",{name:"Save",exact:true}).click();await expect(saveState(page)).toHaveText("All changes saved");}
const comparison=(page:Page)=>page.getByRole("table",{name:"Scenario comparison",exact:true});

test("VC scenario GUI: linear override, independent duplicate, profile, reset, undo, save and reference repair",async({page,request},info)=>{
  const p=await load(page,request,"b5-vc");await named(page,"Create scenario","B5 linear");
  const id=await page.getByLabel("Scenario to manage").inputValue();expect(id).not.toBe("linear_market_size");
  await page.getByRole("button",{name:"Edit override for Market Size",exact:true}).click();
  const d=page.getByRole("dialog");await expect(d.getByText("Function ready",{exact:true})).toBeVisible();
  await expect(d.getByLabel("Candidate unit")).toBeDisabled();await d.getByLabel("Candidate representation").selectOption("linear");
  await expect(d.getByText(/source: local/)).toBeVisible();await apply(page);
  const table=comparison(page);await expect(table).toContainText("0.556120");await expect(table).toContainText("0.652290");
  await expect(page.getByText(/Winner set unchanged · Competition ranking changed/)).toBeVisible();
  await table.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath("b5-vc-comparison.png"),fullPage:true});
  await page.getByRole("button",{name:"Undo",exact:true}).click();await expect(table).toContainText("0.598565");
  await page.getByRole("button",{name:"Redo",exact:true}).click();await expect(table).toContainText("0.556120");
  await named(page,"Duplicate scenario","B5 independent copy");const copy=await page.getByLabel("Scenario to manage").inputValue();expect(copy).not.toBe(id);
  await page.getByRole("button",{name:"Reset Market Size to base",exact:true}).click();await expect(table).toContainText("0.598565");
  // A second independent profile is created through the established operation API; scenario assignment is graphical.
  await save(page);let stored=JSON.parse((await storedFile(request,p.id)).toString()) as Project;
  const edits=await request.post("/api/edit",{data:{project:stored,operations:[{op:"duplicate_weight_profile",profile_id:stored.weight_profiles[0]?.id,name:"B5 emphasis",new_profile_id:"b5_emphasis"}]}});
  expect(edits.ok()).toBeTruthy();const edited=await edits.json() as {project:Project};
  const current=await request.get(`/api/projects/${p.id}`);expect((await request.put(`/api/projects/${p.id}`,{data:edited.project,headers:{"If-Match":current.headers().etag??""}})).ok()).toBeTruthy();
  await page.reload();await openTab(page,"Scenarios");await page.getByLabel("Scenario to manage").selectOption(copy);
  await page.getByLabel("Scenario profile",{exact:true}).selectOption("b5_emphasis");await expect(page.getByLabel("Comparison profiles")).toContainText("B5 emphasis");
  await named(page,"Rename scenario","B5 renamed copy");await save(page);await page.reload();await openTab(page,"Scenarios");await page.getByLabel("Scenario to manage").selectOption(id);
  await expect(comparison(page)).toContainText("0.556120");stored=JSON.parse((await storedFile(request,p.id)).toString()) as Project;
  expect(stored.criteria).toEqual(p.criteria);expect(stored.performances).toEqual(p.performances);expect(stored.analysis).toEqual(p.analysis);
  expect(stored.scenarios.find(s=>s.id===copy)).toMatchObject({name:"B5 renamed copy",weight_profile_id:"b5_emphasis",value_function_overrides:{}});
  expect(stored.scenarios.find(s=>s.id===id)?.value_function_overrides.market_size).toMatchObject({kind:"linear"});
  await page.getByRole("button",{name:"Use viewed scenario as saved default"}).click();await page.getByRole("button",{name:"Confirm scenario change"}).click();
  await page.getByRole("button",{name:"Delete scenario",exact:true}).click();await expect(page.getByRole("button",{name:"Confirm scenario change"})).toBeDisabled();
  await page.getByLabel("Scenario default replacement").selectOption("__base__");await page.getByRole("button",{name:"Confirm scenario change"}).click();
  await expect(page.getByLabel("Scenario to manage")).toHaveValue("");await page.getByRole("button",{name:"Undo",exact:true}).click();
  await expect(page.getByText(/Saved scenario default: B5 linear/)).toBeVisible();await page.getByRole("button",{name:"Redo",exact:true}).click();await save(page);
  stored=JSON.parse((await storedFile(request,p.id)).toString()) as Project;expect(stored.analysis.scenario_id).toBeNull();expect(stored.scenarios.some(s=>s.id===id)).toBe(false);
  await request.delete(`/api/projects/${p.id}`);
});

test("infrastructure scenario, profile isolation, pending context switches and read-only sensitivity",async({page,request},info)=>{
  const p=await load(page,request,"b5-infrastructure",true);await named(page,"Create scenario","Outage linear");const id=await page.getByLabel("Scenario to manage").inputValue();
  await page.getByRole("button",{name:/^Edit override for .*outage/i}).click();await page.getByRole("dialog").getByLabel("Candidate representation").selectOption("linear");await apply(page);
  await page.getByLabel("Scenario profile",{exact:true}).selectOption("consent_led");await expect(page.getByLabel("Comparison profiles")).toContainText("Consent");await save(page);
  const before=await storedFile(request,p.id);const stored=JSON.parse(before.toString()) as Project;expect(stored.criteria).toEqual(p.criteria);expect(stored.performances).toEqual(p.performances);
  let release:()=>void=()=>undefined;const held=new Promise<void>(r=>{release=r;});let started=false;
  await page.route("**/api/scenarios/compare",async route=>{const body=route.request().postDataJSON() as {configuration:{weight_profile_id:string|null}};
    if(body.configuration.weight_profile_id==="default"){started=true;const response=await route.fetch();await held;await route.fulfill({response});}else await route.continue();});
  await page.getByLabel("Weight profile",{exact:true}).selectOption("default");await expect.poll(()=>started).toBe(true);
  await page.getByLabel("Weight profile",{exact:true}).selectOption("consent_led");await expect(page.getByLabel("Comparison profiles")).toContainText("Both outcomes use the same");
  release();await page.waitForLoadState("networkidle");await expect(page.getByLabel("Comparison profiles")).toContainText("Both outcomes use the same");
  await openTab(page,"Sensitivity");await page.getByLabel("Criterion to vary").selectOption("outage_hours");await expect(page.getByTestId("sensitivity-chart")).toBeVisible();
  const probe=page.waitForRequest(r=>r.url().endsWith("/api/sensitivity/probe")&&(r.postDataJSON() as {weight:number}).weight===.37);
  await page.getByLabel("Hypothetical local weight").fill("0.37");await page.getByLabel("Hypothetical local weight").press("Enter");
  expect((await probe).postDataJSON()).toMatchObject({configuration:{scenario_id:id,weight_profile_id:"consent_led"}});
  await expect(page.getByRole("table",{name:"Sensitivity values"})).toBeVisible();await expect(saveState(page)).toHaveText("All changes saved");expect((await storedFile(request,p.id)).equals(before)).toBe(true);
  await page.screenshot({path:info.outputPath("b5-infrastructure-sensitivity.png"),fullPage:true});await page.reload();await openTab(page,"Scenarios");await page.getByLabel("Scenario to manage").selectOption(id);await expect(comparison(page)).toBeVisible();
  await page.getByRole("button",{name:"Delete scenario",exact:true}).click();await page.getByRole("button",{name:"Confirm scenario change"}).click();await save(page);await request.delete(`/api/projects/${p.id}`);
});

test("invalid unrelated scenario leaves base results available; selected invalid scenario never falls back",async({page,request})=>{
  const p=readJson(VC_FILE) as Project;p.id="b5-invalid";p.scenarios.push({id:"invalid",name:"Invalid configuration",weight_profile_id:"missing",value_function_overrides:{}});
  expect((await request.post("/api/projects/import",{data:p})).status()).toBe(201);await page.goto(`/#/p/${p.id}`);await openTab(page,"Results");await expect(page.getByRole("table",{name:"Ranking",exact:true})).toBeVisible();
  await openTab(page,"Sensitivity");await page.getByLabel("Criterion to vary").selectOption("team");await expect(page.getByTestId("sensitivity-chart")).toBeVisible();await openTab(page,"Scenarios");await page.getByLabel("Scenario to manage").selectOption("invalid");
  await expect(page.getByText(/No base result is substituted/)).toBeVisible();await expect(comparison(page)).toHaveCount(0);await openTab(page,"Results");await expect(page.getByRole("table",{name:"Ranking",exact:true})).toHaveCount(0);await request.delete(`/api/projects/${p.id}`);
});

test("scenario candidate Escape and transient viewing never write or create undo entries",async({page,request})=>{
  const p=await load(page,request,"b5-cancel");const before=await storedFile(request,p.id);
  await page.getByLabel("Scenario to manage").selectOption("linear_market_size");await expect(comparison(page)).toBeVisible();await page.getByRole("button",{name:"Edit override for Market Size",exact:true}).click();
  await page.getByRole("dialog").getByLabel("Candidate direction").selectOption("decreasing");await page.getByRole("dialog").getByLabel("Candidate direction").focus();await page.keyboard.press("Escape");await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByLabel("Scenario to manage").selectOption("");await expect(saveState(page)).toHaveText("All changes saved");await expect(page.getByRole("button",{name:"Undo",exact:true})).toBeDisabled();expect((await storedFile(request,p.id)).equals(before)).toBe(true);await request.delete(`/api/projects/${p.id}`);
});

test("scenario save conflict keeps the draft and can save a separate consistent copy",async({page,request})=>{
  const p=await load(page,request,"b5-conflict");await named(page,"Create scenario","My scenario");const scenarioId=await page.getByLabel("Scenario to manage").inputValue();
  expect((await request.put(`/api/projects/${p.id}`,{data:{...p,title:"External revision"}})).ok()).toBeTruthy();const theirs=await storedFile(request,p.id);
  await page.getByRole("button",{name:"Save",exact:true}).click();const d=page.getByRole("dialog",{name:"This project was changed elsewhere"});await expect(d).toBeVisible();
  expect((await storedFile(request,p.id)).equals(theirs)).toBe(true);await d.getByRole("button",{name:"Keep editing",exact:true}).click();
  await expect(page.getByLabel("Scenario to manage")).toHaveValue(scenarioId);await page.getByRole("button",{name:"Save",exact:true}).click();
  await page.getByRole("dialog").getByRole("button",{name:"Save mine as a separate copy"}).click();await expect(saveState(page)).toHaveText("All changes saved");
  const copyId=page.url().split("/p/")[1];if(!copyId)throw Error("missing copied project");const copy=JSON.parse((await storedFile(request,copyId)).toString()) as Project;
  expect(copy.scenarios.some(s=>s.id===scenarioId)).toBe(true);expect(copy.criteria).toEqual(p.criteria);expect((await storedFile(request,p.id)).equals(theirs)).toBe(true);
  await request.delete(`/api/projects/${p.id}`);await request.delete(`/api/projects/${copyId}`);
});

test("rapid scenario switching rejects the old linear comparison after an inherited scenario completes",async({page,request})=>{
  const p=await load(page,request,"b5-scenario-stale");await named(page,"Create scenario","Inherited");const id=await page.getByLabel("Scenario to manage").inputValue();await expect(comparison(page)).toContainText("0.598565");
  let release:()=>void=()=>undefined;const held=new Promise<void>(r=>{release=r;});let started=false;
  await page.route("**/api/scenarios/compare",async route=>{const data=route.request().postDataJSON() as {scenario_ids:string[]};if(data.scenario_ids[0]==="linear_market_size"){started=true;const response=await route.fetch();await held;await route.fulfill({response});}else await route.continue();});
  await page.getByLabel("Scenario to manage").selectOption("linear_market_size");await expect.poll(()=>started).toBe(true);await page.getByLabel("Scenario to manage").selectOption(id);
  await expect(page.getByText(/Competition ranking unchanged/)).toBeVisible();release();await page.waitForLoadState("networkidle");
  await expect(comparison(page)).not.toContainText("0.556120");await expect(page.getByText(/Competition ranking unchanged/)).toBeVisible();await request.delete(`/api/projects/${p.id}`);
});
