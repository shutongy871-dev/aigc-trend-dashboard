// Browser contract checks; API writes are intercepted and use synthetic credentials only.
// npm install --prefix .validation --no-save playwright
// NODE_PATH=.validation/node_modules node tests/settings.cjs
const assert = require("node:assert/strict");
const { spawn, execFileSync } = require("node:child_process");
const { once } = require("node:events");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const temp = path.join(root, ".validation");
fs.mkdirSync(temp, { recursive: true });
execFileSync("python3", ["render_dashboard.py", "--out", path.join(temp, "index.html")], { cwd: root });
const server = spawn("python3", ["-u", "-m", "http.server", "0", "--bind", "127.0.0.1", "--directory", temp]);

(async () => {
  let browser;
  try {
    const [line] = await once(server.stdout, "data");
    const port = String(line).match(/port (\d+)/)[1];
    const launch = { headless: true };
    if (process.env.CHROME_PATH) launch.executablePath = process.env.CHROME_PATH;
    browser = await chromium.launch(launch);
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    const writes = [];
    let failPath = "";
    let failCode = 403;
    let publicKey;
    await page.route("https://api.github.com/**", async route => {
      const request = route.request();
      const url = new URL(request.url());
      assert.equal(url.search, "");
      assert.equal(request.headers().authorization, "Bearer github_pat_test_only");
      assert(!request.headers().referer);
      const body = request.postData();
      if (body) {
        assert(!body.includes("synthetic-llm-key"));
        assert(!body.includes("github_pat_test_only"));
      }
      if (url.pathname.endsWith(failPath) && failPath) {
        return route.fulfill({ status: failCode, json: { message: "synthetic-llm-key should never appear in UI" } });
      }
      if (request.method() === "GET") {
        assert(url.pathname.endsWith("/actions/secrets/public-key"));
        return route.fulfill({ json: { key: publicKey, key_id: "test-key-id" } });
      }
      writes.push({ path: url.pathname, method: request.method(), body: JSON.parse(body) });
      return route.fulfill({ status: request.method() === "PUT" ? 201 : 204, body: "" });
    });
    await page.goto(`http://127.0.0.1:${port}/`);
    await page.waitForFunction(() => !!window.sodium?.crypto_box_seal);
    publicKey = await page.evaluate(() => {
      window.testKeys = sodium.crypto_box_keypair();
      return sodium.to_base64(testKeys.publicKey, sodium.base64_variants.ORIGINAL);
    });
    const fill = async () => {
      await page.getByRole("button", { name: "设置", exact: true }).click();
      await page.getByLabel("LLM API Key", { exact: true }).fill("synthetic-llm-key");
      await page.getByLabel("GitHub 授权令牌", { exact: true }).fill("github_pat_test_only");
    };
    const submit = async () => {
      await page.getByRole("button", { name: "保存到每日任务", exact: true }).click();
      await page.waitForFunction(() => !document.querySelector("#settingsFields").disabled);
    };
    const close = () => page.getByRole("button", { name: "关闭设置", exact: true }).click();
    const noCredentials = async () => {
      assert.equal(await page.locator("#llmKey").inputValue(), "");
      assert.equal(await page.locator("#githubToken").inputValue(), "");
      const storage = await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]));
      assert(!storage.includes("synthetic-llm-key"));
      assert(!storage.includes("github_pat_test_only"));
      assert(!(await page.locator("#settingsStatus").innerText()).includes("synthetic-llm-key"));
    };

    // All three settings must be decryptable sealed boxes for this repository public key.
    await fill();
    await page.getByText("模型与接口地址（可选）", { exact: true }).click();
    await page.getByLabel("模型名称 / 接入点 ID", { exact: true }).fill("test-model");
    await page.getByLabel("OpenAI 兼容接口 Base URL", { exact: true }).fill("https://example.org/v1");
    await submit();
    assert.equal(writes.length, 4);
    for (const write of writes.slice(0, 3)) {
      assert.equal(write.method, "PUT");
      assert.equal(write.body.key_id, "test-key-id");
      const plaintext = await page.evaluate(ciphertext => sodium.to_string(
        sodium.crypto_box_seal_open(
          sodium.from_base64(ciphertext, sodium.base64_variants.ORIGINAL),
          testKeys.publicKey, testKeys.privateKey
        )
      ), write.body.encrypted_value);
      const expected = {
        LLM_API_KEY: "synthetic-llm-key",
        LLM_MODEL: "test-model",
        LLM_BASE_URL: "https://example.org/v1"
      };
      assert.equal(plaintext, expected[write.path.split("/").pop()]);
    }
    assert.deepEqual(writes[3].body, { ref: "main", inputs: { days: "30" } });
    assert((await page.locator("#settingsStatus").innerText()).includes("云端更新已启动"));
    await noCredentials();
    await close();

    // Saving just a key must neither erase custom model settings nor dispatch a run.
    writes.length = 0;
    await fill();
    await page.locator("#updateNow").uncheck();
    await submit();
    assert.equal(writes.length, 1);
    assert(writes[0].path.endsWith("/LLM_API_KEY"));
    assert((await page.locator("#settingsStatus").innerText()).includes("下次运行"));
    await noCredentials();
    await close();

    // No permission / expired credentials: no writes, no reflected raw API errors.
    for (const code of [401, 403, 404]) {
      writes.length = 0;
      failPath = "/public-key"; failCode = code;
      await fill(); await submit();
      assert.equal(writes.length, 0);
      assert.equal(await page.locator("#settingsStatus").getAttribute("data-state"), "error");
      await noCredentials(); await close();
    }

    // A workflow permission failure must not be presented as a failed secret save.
    failPath = "/dispatches"; failCode = 403;
    writes.length = 0;
    await fill(); await submit();
    assert.equal(writes.length, 1);
    assert((await page.locator("#settingsStatus").innerText()).includes("配置已保存"));
    assert.equal(await page.locator("#settingsStatus").getAttribute("data-state"), "warning");
    await noCredentials(); await close();

    // Partial settings writes are possible in GitHub; report them without triggering a run.
    failPath = "/LLM_MODEL"; writes.length = 0;
    await fill();
    await page.getByText("模型与接口地址（可选）", { exact: true }).click();
    await page.getByLabel("模型名称 / 接入点 ID", { exact: true }).fill("test-model");
    await submit();
    assert.equal(writes.length, 1);
    assert((await page.locator("#settingsStatus").innerText()).includes("已保存 LLM_API_KEY"));
    await noCredentials(); await close();

    // Unsafe endpoint input is rejected locally, even with otherwise valid form fields.
    failPath = ""; writes.length = 0;
    await fill();
    await page.getByText("模型与接口地址（可选）", { exact: true }).click();
    await page.getByLabel("OpenAI 兼容接口 Base URL", { exact: true }).fill("http://example.org/v1");
    await submit();
    assert.equal(writes.length, 0);
    assert((await page.locator("#settingsStatus").innerText()).includes("HTTPS"));
    await page.keyboard.press("Escape");
    await noCredentials();
    assert.equal(await page.locator("#settingsDialog").evaluate(e => e.open), false);

    // A small screen can still reach all controls without horizontal scrolling.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: "设置", exact: true }).click();
    const box = await page.locator("#settingsDialog").boundingBox();
    assert(box.x >= 0 && box.x + box.width <= 390);
    assert(await page.locator("#settingsDialog").evaluate(e => e.scrollWidth <= e.clientWidth));
    await page.screenshot({ path: path.join(temp, "settings-mobile.png") });
    await close();
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await page.screenshot({ path: path.join(temp, "settings-desktop.png") });
    await close();
    // Existing search remains usable after dialog interactions.
    await page.locator("#search").fill("definitely-no-such-project-924813");
    assert.equal(await page.locator(".card").count(), 0);
    await page.locator("#search").fill("");
    assert((await page.locator(".card").count()) > 0);
    assert.deepEqual(errors, []);
    console.log("PASS: encrypted settings, save/dispatch outcomes, permissions, credential lifecycle, mobile layout, dashboard search");
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
