const fs = require("node:fs");
const { translate } = require("bing-translate-api");

const MAX_BATCH_CHARS = 2600;
const REQUEST_DELAY_MS = 900;

const marker = (index) => `[[AIGC_${String(index).padStart(6, "0")}]]`;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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
    batch.push({ index, item });
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
      const response = await translate(
        batch.map((item) => item.item).join("\n"),
        null,
        "zh-Hans",
      );
      const parsed = parseBatch(response.translation || "");
      batch.forEach((item) => {
        results[item.index] = parsed.get(item.index) || "";
      });
    } catch (error) {
      console.error(`batch ${index + 1}/${batches.length}: ${error.message}`);
    }
    if (index + 1 < batches.length) await sleep(REQUEST_DELAY_MS);
  }
  process.stdout.write(JSON.stringify(results));
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
