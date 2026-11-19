import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { resolve } from "node:path";
import type { Project } from "../src/api/types";
import { VC_FILE, REPO, at, readJson, saveState, selectNode, storedFile } from "./helpers";
async function openEditor(page:Page,name:string) {
  await selectNode(page,name);await page.getByRole("button",{name:"Open graphical value-function editor"}).click();
  const dialog=page.getByRole("dialog");await expect(dialog.getByText("Function ready",{exact:true})).toBeVisible();return dialog;
}
async function imported(request:APIRequestContext,id:string,supplier=false) {
  const p=readJson(supplier?resolve(REPO,"examples/supplier_selection/project.json"):VC_FILE) as Project;p.id=id;
  expect((await request.post("/api/projects/import",{data:p})).status()).toBe(201);return p;
}
async function applyCandidate(page:Page) {
  const dialog=page.getByRole("dialog");await expect(dialog.getByText("Function ready",{exact:true})).toBeVisible();
  await dialog.getByLabel("Acknowledge candidate range change").check();await dialog.getByRole("button",{name:"Apply candidate"}).click();
  await expect(dialog).toHaveCount(0);
}
test("VC printed points, read-only preview, atomic undo/redo and save/reopen",async({page,request},info)=>{
  const p=await imported(request,"b2-vc");const before=await storedFile(request,p.id);await page.goto(`/#/p/${p.id}`);
  let dialog=await openEditor(page,"Market Size");const xs=[1.380,2.552,5.077,10.037,26.450],ys=[0,.252,.5,.748,1];
  for(let i=0;i<5;i++){await expect(dialog.getByLabel(`Point ${i+1} measurement`,{exact:true})).toHaveValue(String(xs[i]));await expect(dialog.getByLabel(`Point ${i+1} preference`,{exact:true})).toHaveValue(String(ys[i]));}
  await expect(dialog.getByText(/source: control_points/)).toBeVisible();await expect(dialog.getByTestId("preference-curve")).toBeVisible();
  await page.screenshot({path:info.outputPath("b2-vc-printed-function.png")});
  await dialog.getByLabel("Point 2 preference",{exact:true}).fill(".3");await dialog.getByLabel("Candidate unit").fill("US$ bn (reviewed)");
  await expect(saveState(page)).toContainText("Pending candidate");expect((await storedFile(request,p.id)).equals(before)).toBe(true);
  await applyCandidate(page);await page.getByRole("button",{name:"Undo",exact:true}).click();
  dialog=await openEditor(page,"Market Size");await expect(dialog.getByLabel("Point 2 preference",{exact:true})).toHaveValue("0.252");
  await expect(dialog.getByLabel("Candidate unit")).toHaveValue("US$ bn");await dialog.getByRole("button",{name:"Cancel candidate"}).click();
  await expect(saveState(page)).toHaveText("All changes saved");await page.getByRole("button",{name:"Redo",exact:true}).click();
  await page.getByRole("button",{name:"Save",exact:true}).click();await expect(saveState(page)).toHaveText("All changes saved");
  await page.reload();dialog=await openEditor(page,"Market Size");await expect(dialog.getByLabel("Point 2 preference",{exact:true})).toHaveValue("0.3");
  const saved=JSON.parse((await storedFile(request,p.id)).toString()) as Project;const vf=at(saved.criteria.filter(c=>c.id==="market_size"),0).value_function;
  expect(vf).toMatchObject({kind:"piecewise_linear",points:[{x:1.38,value:0},{x:2.552,value:.3},{x:5.077,value:.5},{x:10.037,value:.748},{x:26.45,value:1}]});
  await dialog.getByRole("button",{name:"Cancel candidate"}).click();await request.delete(`/api/projects/${p.id}`);
});
test("invalid points and endpoint range edits expose backend diagnostics without mutation",async({page,request},info)=>{
  const p=await imported(request,"b2-invalid",true);const before=await storedFile(request,p.id);await page.goto(`/#/p/${p.id}`);const d=await openEditor(page,"Defect rate");
  await d.getByLabel("Point 2 measurement",{exact:true}).fill("0");await expect(d.getByText("Function invalid",{exact:true})).toBeVisible();
  await expect(d.getByTestId("preference-curve")).toHaveCount(0);await expect(d.getByRole("button",{name:"Apply candidate"})).toBeDisabled();
  await d.getByLabel("Point 2 measurement",{exact:true}).fill("1");await d.getByLabel("Point 4 measurement",{exact:true}).fill("4");
  await expect(d.getByText("Function ready",{exact:true})).toBeVisible();await expect(d.getByText(/Measurements invalid/)).toBeVisible();
  await expect(d.getByRole("table",{name:"Candidate alternative values"})).toContainText("Unavailable");
  await d.getByLabel("Candidate outside domain").selectOption("clamp");await expect(d.getByRole("table",{name:"Candidate alternative values"})).toContainText("Clamped to endpoint");
  await d.getByRole("button",{name:"Fit current domain to chart"}).click();await page.screenshot({path:info.outputPath("b2-endpoint-clamp-warning.png")});await page.keyboard.press("Escape");
  await expect(d).toHaveCount(0);expect((await storedFile(request,p.id)).equals(before)).toBe(true);await expect(saveState(page)).toHaveText("All changes saved");await request.delete(`/api/projects/${p.id}`);
});
test("real pointer edits, interrupted gestures and keyboard cancellation share candidate validation",async({page,request})=>{
  const p=await imported(request,"b2-pointer");await page.goto(`/#/p/${p.id}`);const d=await openEditor(page,"Market Size");const h=d.getByRole("slider",{name:"Control point 3",exact:true});
  const box=await h.boundingBox();if(!box)throw Error("missing handle");const old=await d.getByLabel("Point 3 preference",{exact:true}).inputValue();
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+15,box.y-15,{steps:4});
  await expect(d.getByLabel("Point 3 preference",{exact:true})).not.toHaveValue(old);await page.keyboard.press("Escape");await page.mouse.up();
  await expect(d).toBeVisible();await expect(d.getByLabel("Point 3 preference",{exact:true})).toHaveValue(old);
  const b=await h.boundingBox();if(!b)throw Error("missing handle");await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await page.mouse.move(b.x+15,b.y-15,{steps:3});
  await h.dispatchEvent("pointercancel",{pointerId:1});await page.mouse.up();await expect(d.getByLabel("Point 3 preference",{exact:true})).toHaveValue(old);
  const lost=await h.boundingBox();if(!lost)throw Error("missing handle");await page.mouse.move(lost.x+lost.width/2,lost.y+lost.height/2);await page.mouse.down();await page.mouse.move(lost.x+15,lost.y-15,{steps:3});
  await h.dispatchEvent("lostpointercapture",{pointerId:1});await page.mouse.up();await expect(d.getByLabel("Point 3 preference",{exact:true})).toHaveValue(old);
  await h.focus();await h.press("ArrowUp");await expect(d.getByLabel("Point 3 preference",{exact:true})).toHaveValue("0.51");
  await expect(d.getByText("Function ready",{exact:true})).toBeVisible();await page.keyboard.press("Escape");await expect(d).toHaveCount(0);
  await expect(saveState(page)).toHaveText("All changes saved");await request.delete(`/api/projects/${p.id}`);
});
test("missing local data cannot invent anchors; explicit fixed preview ignores missing weights",async({page,request},info)=>{
  const p=readJson(VC_FILE) as Project;p.id="b2-local";p.weight_profiles=[];p.performances=p.performances.filter(m=>!(m.criterion_id==="market_growth"&&m.alternative_id==="hyades"));
  expect((await request.post("/api/projects/import",{data:p})).status()).toBe(201);const before=await storedFile(request,p.id);await page.goto(`/#/p/${p.id}`);await selectNode(page,"Market Growth");
  await page.getByRole("button",{name:"Open graphical value-function editor"}).click();const d=page.getByRole("dialog");await expect(d.getByText("Function incomplete",{exact:true})).toBeVisible();
  await expect(d.getByText(/Effective domain:/)).toHaveCount(0);await expect(d.getByRole("slider")).toHaveCount(0);await expect(d.getByRole("button",{name:"Apply candidate"})).toBeDisabled();
  await page.screenshot({path:info.outputPath("b2-missing-local-anchors.png")});await d.getByLabel("Candidate anchors").selectOption("fixed");
  await d.getByLabel("Candidate lower",{exact:true}).fill("0");await d.getByLabel("Candidate upper",{exact:true}).fill("50");
  await expect(d.getByText("Function ready",{exact:true})).toBeVisible();await expect(d.getByText(/Measurements incomplete/)).toBeVisible();
  expect((await storedFile(request,p.id)).equals(before)).toBe(true);await d.getByRole("button",{name:"Cancel candidate"}).click();await request.delete(`/api/projects/${p.id}`);
});
test("unrelated model supports decreasing/increasing, qualitative dots and direct ratings",async({page,request},info)=>{
  const p=await imported(request,"b2-supplier",true);await page.goto(`/#/p/${p.id}`);let d=await openEditor(page,"Unit price");
  await expect(d.getByText("Preference direction: Lower measurements are preferred")).toBeVisible();await d.getByLabel("Candidate direction").selectOption("increasing");
  await expect(d.getByText("Function ready",{exact:true})).toBeVisible();await expect(d.getByText("Preference direction: Higher measurements are preferred")).toBeVisible();await d.getByRole("button",{name:"Cancel candidate"}).click();
  d=await openEditor(page,"Certification");await expect(d.getByTestId("preference-curve")).toHaveCount(0);await expect(d.locator(".label-value")).toHaveCount(3);
  await d.getByLabel("Preference for iso9001",{exact:true}).fill(".65");await expect(d.getByText("Function ready",{exact:true})).toBeVisible();await page.screenshot({path:info.outputPath("b2-qualitative-judgements.png")});
  await d.getByRole("button",{name:"Cancel candidate"}).click();d=await openEditor(page,"Sourcing region");
  await expect(d.getByText("Preference direction: Explicit category judgements (no intrinsic order)")).toBeVisible();await expect(d.getByTestId("preference-curve")).toHaveCount(0);
  await d.getByRole("button",{name:"Cancel candidate"}).click();d=await openEditor(page,"Financial stability");await d.getByLabel("Candidate rating maximum").fill("120");
  await expect(d.getByText(/source: rating_range/)).toContainText("120");await d.getByRole("button",{name:"Fit current domain to chart"}).click();await page.screenshot({path:info.outputPath("b2-direct-rating.png")});await applyCandidate(page);
  await page.getByRole("button",{name:"Save",exact:true}).click();await expect(saveState(page)).toHaveText("All changes saved");await request.delete(`/api/projects/${p.id}`);
});
test("obsolete candidate responses cannot paint a current curve; Ctrl+S applies once before save",async({page,request})=>{
  const p=await imported(request,"b2-stale");await page.goto(`/#/p/${p.id}`);const d=await openEditor(page,"Market Size");
  let release:()=>void=()=>undefined;const held=new Promise<void>(resolve=>{release=resolve;});let started=false;
  await page.route("**/api/value-functions/preview",async route=>{
    const data=route.request().postDataJSON() as {candidate?:{value_function?:{points?:{value:number}[]}}};
    if(data.candidate?.value_function?.points?.[1]?.value===.3){started=true;const response=await route.fetch();await held;await route.fulfill({response});}else await route.continue();
  });
  await d.getByLabel("Point 2 preference",{exact:true}).fill(".3");await expect.poll(()=>started).toBe(true);
  await d.getByLabel("Point 2 preference",{exact:true}).fill(".35");await expect(d.getByText("Function ready",{exact:true})).toBeVisible();
  const path=await d.getByTestId("preference-curve").getAttribute("d");release();await page.waitForLoadState("networkidle");expect(await d.getByTestId("preference-curve").getAttribute("d")).toBe(path);
  await d.getByLabel("Acknowledge candidate range change").check();await page.keyboard.press("ControlOrMeta+s");await expect(d).toHaveCount(0);await expect(saveState(page)).toHaveText("All changes saved");
  const saved=JSON.parse((await storedFile(request,p.id)).toString()) as Project;expect(at(saved.criteria.filter(c=>c.id==="market_size"),0).value_function).toMatchObject({points:[{x:1.38,value:0},{x:2.552,value:.35},{x:5.077,value:.5},{x:10.037,value:.748},{x:26.45,value:1}]});await request.delete(`/api/projects/${p.id}`);
});
test("pending invalid candidates participate in the navigation save/discard/stay guard",async({page,request})=>{
  const p=await imported(request,"b2-leave");await page.goto(`/#/p/${p.id}`);const d=await openEditor(page,"Market Size");await d.getByLabel("Point 2 preference",{exact:true}).fill("-");
  await page.evaluate(()=>{window.location.hash="#/";});await expect(page.getByRole("dialog",{name:/Unsaved changes/})).toBeVisible();
  await page.getByRole("button",{name:"Keep editing",exact:true}).click();await expect(d.getByLabel("Point 2 preference",{exact:true})).toHaveValue("-");
  await page.evaluate(()=>{window.location.hash="#/";});await page.getByRole("button",{name:"Discard changes",exact:true}).click();await expect(page.getByRole("heading",{name:"Projects",exact:true})).toBeVisible();await request.delete(`/api/projects/${p.id}`);
});

test("point addition, selection, pointer commit and hidden local anchors survive kind switches",async({page,request})=>{
  const p=await imported(request,"b2-point-operations");await page.goto(`/#/p/${p.id}`);let d=await openEditor(page,"Market Size");
  await d.getByLabel("New point measurement").fill("15");await d.getByLabel("New point preference").fill(".85");await d.getByRole("button",{name:"Add control point",exact:true}).click();
  await expect(d.getByText("Function ready",{exact:true})).toBeVisible();await expect(d.getByRole("slider")).toHaveCount(6);
  const h=d.getByRole("slider",{name:"Control point 5",exact:true});await h.focus();await h.press("Delete");await expect(d.getByRole("slider")).toHaveCount(5);
  await expect(d.getByText("Function ready",{exact:true})).toBeVisible();
  const interior=d.getByRole("slider",{name:"Control point 3",exact:true});await interior.scrollIntoViewIfNeeded();const box=await interior.boundingBox();if(!box)throw Error("missing handle");
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+12,box.y+box.height/2-15,{steps:4});await page.mouse.up();
  await expect(d.getByText("Function ready",{exact:true})).toBeVisible();const edited=await d.getByLabel("Point 3 preference",{exact:true}).inputValue();expect(Number(edited)).toBeGreaterThan(.5);
  await applyCandidate(page);await page.getByRole("button",{name:"Save",exact:true}).click();await expect(saveState(page)).toHaveText("All changes saved");
  d=await openEditor(page,"Market Size");await expect(d.getByLabel("Point 3 preference",{exact:true})).toHaveValue(edited);
  await d.getByLabel("Candidate representation").selectOption("linear");await expect(d.getByLabel("Candidate anchors")).toHaveValue("local");await expect(d.getByText(/source: local/)).toBeVisible();
  await d.getByLabel("Candidate representation").selectOption("piecewise_linear");await expect(d.getByText(/Stored scale anchor mode remains local/)).toBeVisible();await d.getByRole("button",{name:"Cancel candidate"}).click();
  const saved=JSON.parse((await storedFile(request,p.id)).toString()) as Project;expect(at(saved.criteria.filter(c=>c.id==="market_size"),0).scale?.anchor_mode).toBe("local");await request.delete(`/api/projects/${p.id}`);
});
test("scenario candidates stay separate from base commits and range acknowledgements reset",async({page,request})=>{
  const p=await imported(request,"b2-scenario");await page.goto(`/#/p/${p.id}`);await page.getByLabel("Scenario",{exact:true}).selectOption("linear_market_size");
  const d=await openEditor(page,"Market Size");await expect(d.getByText(/Scenario overrides can be inspected/)).toBeVisible();
  await d.getByLabel("Candidate direction").selectOption("decreasing");await expect(d.getByText("Function ready",{exact:true})).toBeVisible();await d.getByLabel("Acknowledge candidate range change").check();
  await expect(d.getByRole("button",{name:"Apply candidate"})).toBeDisabled();await d.getByLabel("Candidate unit").fill("different unit");
  await expect(d.getByLabel("Acknowledge candidate range change")).not.toBeChecked();await d.getByRole("button",{name:"Cancel candidate"}).click();await expect(saveState(page)).toHaveText("All changes saved");await request.delete(`/api/projects/${p.id}`);
});

test("plot double-click supplies explicit point inputs and the editor stacks on narrow screens",async({page,request},info)=>{
  const p=await imported(request,"b2-plot-add");await page.goto(`/#/p/${p.id}`);const d=await openEditor(page,"Market Size");
  const chart=d.getByRole("group",{name:"Value-function chart"});const box=await chart.boundingBox();if(!box)throw Error("missing chart");
  // Coordinates are presentation geometry only; the engine validates the explicit judgement.
  const lower=1.38-(26.45-1.38)*.15,upper=26.45+(26.45-1.38)*.15;
  await page.mouse.dblclick(box.x+(65+(20-lower)/(upper-lower)*500)/640*box.width,box.y+(28+(1-.9)*235)/325*box.height);
  await expect(d.getByRole("slider")).toHaveCount(6);await expect(d.getByText("Function ready",{exact:true})).toBeVisible();
  expect(Number(await d.getByLabel("Point 5 measurement",{exact:true}).inputValue())).toBeCloseTo(20,0);
  await page.setViewportSize({width:700,height:950});await chart.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath("b2-narrow-layout.png")});
  await d.getByRole("button",{name:"Cancel candidate"}).click();await request.delete(`/api/projects/${p.id}`);
});
