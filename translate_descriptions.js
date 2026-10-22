const fs = require("node:fs");
const { translate } = require("bing-translate-api");

const MAX_BATCH_CHARS = 2600;
const REQUEST_DELAY_MS = 900;
const REQUEST_TIMEOUT_MS = 20000;

const marker = (index) => `[[AIGC_${String(index).padStart(6, "0")}]]`;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const withTimeout = (promise) => Promise.race([
  promise,
  new Promise((_, reject) => {
    setTimeout(() => reject(new Error("request timed out")), REQUEST_TIMEOUT_MS);
  }),
]);

function makeBatches(texts) {
  const batches = [];
  let batch = [];
  let length = 0;

  texts.forEach((text, index) => {
    const item = `${marker(index)} ${text}`;
    if (batch.length && length + item.length + 1 > MAX_BATCH_CHARS) {
      batches.push(batch);
      batch = [];
      length = 0;
    }
    batch.push({ index, item, text });
    length += item.length + 1;
  });
  if (batch.length) batches.push(batch);
  return batches;
}

function parseBatch(text) {
  const parsed = new Map();
  const pattern = /\[\[AIGC_(\d{6})\]\]\s*([\s\S]*?)(?=\n?\[\[AIGC_\d{6}\]\]|$)/g;
  for (const match of text.matchAll(pattern)) {
    parsed.set(Number(match[1]), match[2].trim());
  }
  return parsed;
}

async function main() {
  const texts = JSON.parse(fs.readFileSync(0, "utf8"));
  if (!Array.isArray(texts) || texts.some((text) => typeof text !== "string")) {
    throw new Error("stdin must be a JSON string array");
  }

  const results = Array(texts.length).fill("");
  const batches = makeBatches(texts);
  for (let index = 0; index < batches.length; index += 1) {
    const batch = batches[index];
    try {
      const response = await withTimeout(translate(
        batch.length === 1
          ? batch[0].text
          : batch.map((item) => item.item).join("\n"),
        null,
        "zh-Hans",
      ));
      if (batch.length === 1) {
        results[batch[0].index] = (response.translation || "").trim();
      } else {
        const parsed = parseBatch(response.translation || "");
        batch.forEach((item) => {
          results[item.index] = parsed.get(item.index) || "";
        });
      }
    } catch (error) {
      console.error(`batch ${index + 1}/${batches.length}: ${error.message}`);
      break;
    }
    if (index + 1 < batches.length) await sleep(REQUEST_DELAY_MS);
  }
  fs.writeFileSync(1, JSON.stringify(results));
  process.exit(0);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
