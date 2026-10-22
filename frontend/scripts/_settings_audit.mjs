import { chromium } from "playwright";
const B="http://127.0.0.1:8799"; const OUT="../out/setaudit";
const b = await chromium.launch();
const p = await (await b.newContext({viewport:{width:1440,height:900}, locale:"zh-CN"})).newPage();
const errs=[];
p.on("pageerror",e=>errs.push("pageerror: "+String(e).slice(0,160)));
p.on("console", m=>{ if(m.type()==="error" && !m.text().includes("404")) errs.push("console: "+m.text().slice(0,160)); });
p.on("response", r=>{ if(r.status()>=400) errs.push(`HTTP ${r.status()} ${r.url()}`); });
await p.addInitScript(()=>localStorage.setItem("wo.onboarded","1"));
await p.goto(B,{waitUntil:"networkidle"});
await p.waitForTimeout(600);
await p.getByRole("button",{name:"设置"}).first().click();
await p.waitForTimeout(1200);

const sections = ["偏好","账本规则","预算","AI 回答","Agent 与技能","每日晨报","长期记忆","数据与状态","访问口令","日志","审计日志","溯源链","家庭账本"];
for (const s of sections) {
  await p.getByText(s,{exact:true}).first().click();
  await p.waitForTimeout(900);
  await p.screenshot({path:`${OUT}/${s}.png`});
}
console.log("ISSUES", JSON.stringify([...new Set(errs)], null, 1));
await b.close();
