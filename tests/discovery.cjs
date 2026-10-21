// Real browser checks. Synthetic fixtures stay under ignored .validation/.
const assert = require("node:assert/strict");
const { spawn, execFileSync } = require("node:child_process");
const { once } = require("node:events");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const temp = path.join(root, ".validation", "discovery");
fs.mkdirSync(temp, { recursive: true });
execFileSync("python3", ["render_dashboard.py", "--out", path.join(temp, "index.html")], { cwd: root });
execFileSync("python3", ["-c", `
import copy,json
from pathlib import Path
from project_discovery import enrich_learning,build_discovery
from render_dashboard import build_html
d=json.load(open("output/aigc_data.json"))
for p in d["github_projects"]:
    p.pop("learning",None)
    p.pop("learning_cache_key",None)
a=enrich_learning(d["github_projects"],model="test",log=lambda _:None)
d["discovery"]=build_discovery(d["github_projects"],d["window"],a)
Path(".validation/discovery/no-model.html").write_text(build_html(d))
p=next(p for p in d["github_projects"] if p["full_name"] in d["discovery"]["skills_tools"])
p["description"]='<img src=x onerror="window.INJECTED=true"> Literal README text'
p["evidence"][0]["text"]='</script><img src=x onerror="window.INJECTED=true">'
Path(".validation/discovery/escaping.html").write_text(build_html(d))
`], { cwd: root });
const server = spawn("python3", ["-u", "-m", "http.server", "0", "--bind", "127.0.0.1", "--directory", temp]);

(async () => {
  let browser;
  try {
    const [line] = await once(server.stdout, "data");
    const port = String(line).match(/port (\d+)/)[1];
    const launch = { headless: true };
    if (process.env.CHROME_PATH) launch.executablePath = process.env.CHROME_PATH;
    browser = await chromium.launch(launch);
    const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    await page.goto(`http://127.0.0.1:${port}/`);
    assert.equal(await page.getByRole("button", { name: "设置", exact: true }).count(), 0);
    assert.equal(await page.locator('input[type="password"], dialog').count(), 0);
    assert.equal(await page.evaluate(() => typeof window.sodium), "undefined");
    assert.equal(await page.locator(".tab.active").getAttribute("data-tab"), "skills");
    assert.equal(await page.locator(".tab").first().innerText(), "全部项目");
    assert.equal(await page.locator('.tab[data-tab="trends"]').count(), 0);
    assert.equal(await page.locator(".discovery-intro").count(), 0);
    assert.equal(await page.locator("#hint").isVisible(), false);
    assert.equal(await page.locator(".learning-card").count(), 12);
    assert.equal(await page.locator(".learning-card .badge-cat").first().innerText(), "🧩 Skill / 工具");
    const bilingual = page.locator(".learning-card").filter({ hasText: "Ebony-Vinyl/dsh-our-free-model" });
    assert.equal(await bilingual.locator(".source-status").count(), 0);
    assert.equal(await bilingual.locator(".card-desc p").count(), 2);
    assert.equal(await bilingual.locator(".card-desc p").nth(0).getAttribute("lang"), "zh-CN");
    assert.equal(await bilingual.locator(".card-desc p").nth(1).getAttribute("lang"), "en");
    const download = bilingual.getByRole("button", { name: "复制给 Agent 下载", exact: true });
    assert((await download.getAttribute("data-cmd")).includes("Ebony-Vinyl/dsh-our-free-model"));
    assert((await download.getAttribute("data-cmd")).includes("安全风险"));
    assert.equal(await page.locator(".expand-label").filter({ hasText: /怎么用|找灵感/ }).count(), 0);
    const card = page.locator(".learning-card").filter({ hasText: "wheresryan22/anatomy" });
    assert((await card.innerText()).includes("立体示意物"));
    await card.locator(".expand-toggle").click();
    assert.equal(await card.locator(".expand-toggle").getAttribute("aria-expanded"), "true");
    assert.equal(await card.locator(".expand-label").innerText(), "收起演示");
    assert(await card.locator(".detail").isVisible());
    assert(await card.locator(".demo-result").isVisible());
    assert.equal(await card.locator(".demo-run").count(), 0);
    assert.equal(await card.locator(".detail h4").first().innerText(), "使用演示");
    assert.equal(await card.locator(".detail").getByText("上手步骤", { exact: true }).count(), 0);
    assert.equal(await card.locator(".demo-stage-title").innerText(), "处理过程");
    assert((await card.locator(".demo-result").innerText()).includes("限流"));
    await card.locator(".evidence-list summary").click();
    assert(await card.locator("blockquote").first().isVisible());
    const otherCard = page.locator(".learning-card").first();
    assert(!(await otherCard.locator(".detail").isVisible()));
    // Search can find the principle and usage, not only names or raw descriptions.
    await page.locator("#search").fill("几何审计");
    assert((await page.locator(".learning-card").count()) >= 1);
    await page.locator("#search").fill("");
    await page.getByRole("button", { name: "软件 / 小程序", exact: true }).click();
    assert.equal(await page.locator(".learning-card").count(), 12);
    assert.equal(await page.locator(".learning-card .badge-cat").first().innerText(), "📱 软件 / 应用");
    assert((await page.locator("#content").innerText()).includes("yetone/magpie"));
    const app = page.locator(".learning-card").filter({ hasText: "ARahim3/DigUp" });
    await app.locator(".expand-toggle").click();
    assert((await app.locator(".detail").innerText()).includes("SQLite"));
    await page.getByRole("button", { name: /趋势总结.*机制与爆发观察/ }).click();
    const trendCount = await page.locator(".trend-card").count();
    assert(trendCount >= 1);
    assert.equal(await page.locator(".trend-bars").count(), trendCount);
    assert((await page.locator(".scope-note").last().innerText()).includes("不是 Star 增速"));
    await page.screenshot({ path: path.join(temp, "trends-desktop.png"), fullPage: true, animations: "disabled" });
    await page.getByRole("button", { name: "全部项目", exact: true }).click();
    assert((await page.locator(".card").count()) > 12);
    assert.equal(await page.getByRole("button", { name: "复制给 Agent 下载", exact: true }).count(),
      await page.locator(".learning-card").count());
    await page.locator("#sort").selectOption("stars");
    await page.locator(".chip").filter({ hasText: /^Agent\/智能体$/ }).click();
    assert.equal(await page.locator(".chip.active").innerText(), "Agent/智能体");
    await page.getByRole("button", { name: "HF 新模型", exact: true }).click();
    assert((await page.locator(".card").count()) > 0);
    await page.getByRole("button", { name: "HN 热议", exact: true }).click();
    assert((await page.locator(".row").count()) > 0);
    await page.getByRole("button", { name: "Skill / 工具", exact: true }).click();
    await page.screenshot({ path: path.join(temp, "skills-desktop.png"), fullPage: true, animations: "disabled" });
    await page.setViewportSize({ width: 390, height: 844 });
    const mobile = page.locator(".learning-card").filter({ hasText: "wheresryan22/anatomy" });
    await mobile.locator(".expand-toggle").click();
    assert(await mobile.locator(".demo-result").isVisible());
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: path.join(temp, "skills-mobile.png"), fullPage: true, animations: "disabled" });
    await page.goto(`http://127.0.0.1:${port}/no-model.html`);
    assert.equal(await page.locator(".analysis-notice").count(), 0);
    await page.getByRole("button", { name: /趋势总结.*机制与爆发观察/ }).click();
    assert((await page.locator("#content").innerText()).includes("尚未验证共同机制"));
    await page.goto(`http://127.0.0.1:${port}/escaping.html`);
    assert((await page.locator(".card-desc").first().innerText()).includes("<img"));
    assert.equal(await page.locator(".card img").count(), 0);
    assert.equal(await page.evaluate(() => !!window.INJECTED), false);
    await page.locator(".expand-toggle").first().click();
    await page.locator(".evidence-list summary").first().click();
    assert.equal(await page.evaluate(() => !!window.INJECTED), false);
    assert.deepEqual(errors, []);
    console.log("PASS: public dashboard has no settings/credentials, discovery views and interactions work");
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
