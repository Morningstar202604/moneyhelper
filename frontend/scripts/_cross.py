import pathlib
p = pathlib.Path("scripts/_cross.mjs")
p.write_text('''import { chromium } from "playwright";
const b = await chromium.launch();
const p = await (await b.newContext({viewport:{width:1440,height:900}, locale:"zh-CN"})).newPage();
await p.addInitScript(()=>localStorage.setItem("wo.onboarded","1"));
await p.goto("http://127.0.0.1:8799",{waitUntil:"networkidle"});
await p.waitForTimeout(600);
await p.getByRole("button",{name:"设置"}).first().click();
await p.waitForTimeout(1000);
await p.getByText("账本规则",{exact:true}).first().click();
await p.waitForTimeout(700);
await p.locator('input[type="number"]').first().fill("31000");
await p.waitForTimeout(500);
console.log("dirty bar on rules:", await p.getByText("有未保存的修改").count());
await p.getByText("AI 回答",{exact:true}).first().click();
await p.waitForTimeout(900);
console.log("dirty bar on AI page:", await p.getByText("有未保存的修改").count());
await p.screenshot({path:"../out/setaudit/cross-dirty.png"});
// 顶部关闭：是否提示丢失
await p.getByRole("button",{name:"关闭"}).first().click();
await p.waitForTimeout(800);
console.log("after close, settings still open:", await p.getByText("AI 回答",{exact:true}).count());
await p.screenshot({path:"../out/setaudit/after-close.png"});
await b.close();
''')
