// Exercise the real Actions decision script against isolated Git histories.
// This ensures a direct HTML/JS push is published without being regenerated.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { test } = require("node:test");

const root = path.resolve(__dirname, "..");
const workflow = fs.readFileSync(path.join(root, ".github/workflows/deploy.yml"), "utf8");
const step = workflow.split("      - name: 判断是否需要生成看板\n")[1]?.split("\n      - name:")[0];
assert(step, "Missing render decision step.");
const script = step.split("        run: |\n")[1].split("\n")
  .map((line) => line.replace(/^          /, "")).join("\n");
const archiveStep = workflow.split("      - name: 回写当日数据与看板到仓库（归档）\n")[1]
  .split("\n      - name:")[0];
const archiveScript = archiveStep.split("        run: |\n")[1].split("\n")
  .map((line) => line.replace(/^          /, "")).join("\n");
const tempRoot = path.join(root, ".validation", "deploy-workflow-tests");
fs.mkdirSync(tempRoot, { recursive: true });

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(tempRoot, "repo-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const git = (...args) => execFileSync("git", args, { cwd: dir, encoding: "utf8" }).trim();
  const write = (file, content) => {
    fs.mkdirSync(path.dirname(path.join(dir, file)), { recursive: true });
    fs.writeFileSync(path.join(dir, file), content);
  };
  const commit = () => {
    git("add", ".");
    git("-c", "user.name=Workflow Test", "-c", "user.email=test@example.invalid",
      "-c", "commit.gpgsign=false", "commit", "-qm", "test fixture");
    return git("rev-parse", "HEAD");
  };
  git("init", "-q");
  // Fixture histories must be self-contained; use this disposable repo's hooks.
  // A developer's global hooks may write logs outside the test directory.
  git("config", "core.hooksPath", path.join(dir, ".git", "hooks"));
  git("config", "commit.gpgsign", "false");
  write("site/index.html", "<html>existing page</html>");
  write("site/app.js", "// website script");
  write("site/vercel.json", "{}");
  write("render_dashboard.py", "# renderer");
  write("output/aigc_data.json", "{}");
  write("output/aigc_brief.md", "existing brief");
  const before = commit();
  function needsRender(event = "push", previous = before) {
    const output = path.join(dir, "decision-output");
    fs.writeFileSync(output, "");
    execFileSync("bash", ["-e", "-o", "pipefail", "-c", script], {
      cwd: dir,
      env: { ...process.env, WORKFLOW_EVENT: event, PUSH_BEFORE_SHA: previous, GITHUB_OUTPUT: output },
      encoding: "utf8",
    });
    return fs.readFileSync(output, "utf8").trim();
  }
  return { dir, git, write, commit, needsRender };
}

test("publishes direct HTML, browser JS, and Vercel config changes without overwriting them", (t) => {
  const f = fixture(t);
  f.write("site/index.html", "<html>new directly edited page</html>");
  f.write("site/app.js", "// new browser behavior");
  f.write("site/vercel.json", '{"headers":[]}');
  f.commit();
  assert.equal(f.needsRender(), "needed=false");
});

test("renders a changed Python template even when HTML changes in the same push", (t) => {
  const f = fixture(t);
  f.write("render_dashboard.py", "# new template");
  f.write("site/index.html", "<html>new entry</html>");
  f.commit();
  assert.equal(f.needsRender(), "needed=true");
});

test("renders changed source data", (t) => {
  const f = fixture(t);
  f.write("output/aigc_data.json", '{"updated":true}');
  f.commit();
  assert.equal(f.needsRender(), "needed=true");
});

test("publishes documentation-only pushes without invoking data services", (t) => {
  const f = fixture(t);
  f.write("README.md", "Updated deployment instructions");
  f.commit();
  assert.equal(f.needsRender(), "needed=false");
});

test("scheduled and manual runs still refresh the dashboard", (t) => {
  const f = fixture(t);
  assert.equal(f.needsRender("schedule", ""), "needed=true");
  assert.equal(f.needsRender("workflow_dispatch", ""), "needed=true");
});

test("new history or a missing output causes a safe rebuild", (t) => {
  const f = fixture(t);
  assert.equal(f.needsRender("push", "0".repeat(40)), "needed=true");
  fs.unlinkSync(path.join(f.dir, "site/index.html"));
  assert.equal(f.needsRender(), "needed=true");
});

function archiveFixture(t, changedFile, changedContent) {
  const f = fixture(t);
  const remote = fs.mkdtempSync(path.join(tempRoot, "remote-"));
  t.after(() => fs.rmSync(remote, { recursive: true, force: true }));
  f.git("init", "--bare", "-q", remote);
  f.git("--git-dir=" + remote, "config", "core.hooksPath", path.join(remote, "hooks"));
  f.git("branch", "-M", "main");
  f.git("remote", "add", "origin", remote);
  f.git("push", "-q", "-u", "origin", "main");
  const source = f.git("rev-parse", "HEAD");
  f.write(changedFile, changedContent);
  f.commit();
  f.git("push", "-q", "origin", "main");
  f.git("checkout", "-q", "--detach", source);
  f.write("site/index.html", "<html>new generated page</html>");
  const output = path.join(f.dir, "archive-output");
  execFileSync("bash", ["-e", "-o", "pipefail", "-c", archiveScript], {
    cwd: f.dir,
    env: { ...process.env, GITHUB_OUTPUT: output },
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  return { ...f, result: fs.readFileSync(output, "utf8").trim() };
}

test("a concurrent config push is retained while new HTML is archived and published", (t) => {
  const f = archiveFixture(t, "site/vercel.json", '{"updatedRoute":true}');
  assert.equal(f.result, "publish=true");
  assert.equal(f.git("show", "origin/main:site/vercel.json"), '{"updatedRoute":true}');
  assert.equal(f.git("show", "origin/main:site/index.html"), "<html>new generated page</html>");
});

test("newer source code prevents publishing a stale generated page", (t) => {
  const f = archiveFixture(t, "render_dashboard.py", "# newer source code");
  assert.equal(f.result, "publish=false");
  assert.equal(f.git("show", "origin/main:render_dashboard.py"), "# newer source code");
  assert.equal(f.git("show", "origin/main:site/index.html"), "<html>existing page</html>");
});

test("a user's newer HTML edit is never overwritten by an older running build", (t) => {
  const f = archiveFixture(t, "site/index.html", "<html>new user edit</html>");
  assert.equal(f.result, "publish=false");
  assert.equal(f.git("show", "origin/main:site/index.html"), "<html>new user edit</html>");
});
