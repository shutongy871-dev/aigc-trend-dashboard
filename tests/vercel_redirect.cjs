// Run with: node --test tests/vercel_redirect.cjs
// Exercise the actual inline script without navigating to an external website.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "site/index.html"), "utf8");
const match = html.match(/<script id="github-pages-vercel-redirect">([\s\S]*?)<\/script>/);
assert(match, "The redirect must be present in the published HTML.");
const script = match[1];
const destinationOrigin = new URL(script.match(/var VERCEL_URL = "([^"]+)";/)[1]).origin;

test("redirect uses the live production domain, not a placeholder or deployment snapshot", () => {
  assert.equal(destinationOrigin, "https://aigc-trend-dashboard-site.vercel.app");
});

function execute(url, { readyState = "loading", navigationThrows = false } = {}) {
  const current = new URL(url);
  const appended = [];
  const calls = [];
  const events = [];
  const nodes = new Map();

  const document = {
    readyState,
    body: {
      prepend(node) {
        appended.unshift(node);
        nodes.set(node.id, node);
      },
    },
    createTextNode: (text) => ({ textContent: text }),
    createElement: (tagName) => ({
      tagName, style: {}, children: [],
      setAttribute(name, value) { this[name] = value; },
      appendChild(node) { this.children.push(node); },
    }),
    getElementById: (id) => nodes.get(id),
    addEventListener: (event, callback) => events.push({ event, callback }),
  };
  const location = {
    hostname: current.hostname,
    pathname: current.pathname,
    search: current.search,
    hash: current.hash,
    replace(destination) {
      calls.push(destination);
      if (navigationThrows) throw new Error("Navigation blocked");
    },
  };
  vm.runInNewContext(script, { URL, window: { location }, document });
  return { calls, appended, events, finishParsing() { events.forEach((e) => e.callback()); } };
}

test("HTML and generator contain the identical head script", () => {
  assert(html.indexOf(match[0]) < html.indexOf("</head>"));
  const template = fs.readFileSync(path.join(root, "render_dashboard.py"), "utf8");
  assert(template.includes(match[0]), "Daily rendering must retain the redirect.");
  assert.equal(html.split('id="github-pages-vercel-redirect"').length - 1, 1);
});

test("GitHub Pages preserves path, encoded parameters, repeated keys, and hash", () => {
  const suffix = "/aigc-trend-dashboard/index.html?q=%E4%B8%AD%E6%96%87&x=1&x=2#details";
  const result = execute(`https://shutongy871-dev.github.io${suffix}`);
  assert.deepEqual(result.calls, [`${destinationOrigin}${suffix}`]);
  assert.equal(result.appended.length, 0, "Do not access body before parsing finishes.");
  result.finishParsing();
  const notice = result.appended[0];
  assert.equal(notice.id, "vercel-redirect-fallback");
  assert.equal(notice.role, "status");
  const link = notice.children.find((node) => node.tagName === "a");
  assert.equal(link.href, result.calls[0]);
  assert.equal(link.textContent, "请点击此处访问 Vercel 网站");
});

test("root path and uppercase GitHub hostname work", () => {
  assert.deepEqual(execute("https://USER.GITHUB.IO/?from=old").calls, [
    `${destinationOrigin}/?from=old`,
  ]);
});

test("Vercel, local, custom, and misleading domains have no side effects", () => {
  for (const url of [
    `${destinationOrigin}/aigc-trend-dashboard/?q=test`,
    "https://preview-abc.vercel.app/",
    "http://localhost:8080/",
    "http://127.0.0.1:8080/",
    "https://portfolio.example.com/",
    "https://user.github.io.example.com/",
    "https://fakegithub.io/",
    "https://github.io/",
  ]) {
    const result = execute(url);
    assert.equal(result.calls.length, 0, url);
    assert.equal(result.events.length, 0, url);
    assert.equal(result.appended.length, 0, url);
  }
});

test("blocked navigation leaves a usable link and does not crash the page", () => {
  for (const readyState of ["loading", "interactive", "complete"]) {
    const result = execute("https://user.github.io/aigc-trend-dashboard/?a=1#top", {
      readyState, navigationThrows: true,
    });
    result.finishParsing();
    result.finishParsing();
    assert.equal(result.appended.length, 1);
    assert.equal(
      result.appended[0].children.find((node) => node.tagName === "a").href,
      `${destinationOrigin}/aigc-trend-dashboard/?a=1#top`,
    );
  }
});

test("a path beginning with // cannot change the configured destination origin", () => {
  const result = execute("https://user.github.io//outside.example/test");
  assert.equal(new URL(result.calls[0]).origin, destinationOrigin);
  assert.equal(new URL(result.calls[0]).pathname, "//outside.example/test");
});

test("the actual old homepage path resolves explicitly to index.html on Vercel", () => {
  const config = JSON.parse(fs.readFileSync(path.join(root, "site/vercel.json"), "utf8"));
  const destination = new URL(execute("https://shutongy871-dev.github.io/aigc-trend-dashboard/").calls[0]);
  const route = config.rewrites.find((rule) => rule.source === destination.pathname);
  assert.equal(route?.destination, "/index.html",
    "Rewriting an empty wildcard to / does not serve index.html on Vercel.");
});
