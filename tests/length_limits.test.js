// Run: node tests/length_limits.test.js   (also run by tests/test_extension_js.py)
// Checks how the extension reads a form's length limit and cuts an over-long answer to fit it.
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const src = fs.readFileSync(path.join(__dirname, "../extension/content.js"), "utf8");
const block = src.slice(src.indexOf("  function statedMax"), src.indexOf("  async function collectQuestions"));
const { limitsOf, fitTo } = new Function(block + "; return { limitsOf, fitTo };")();

let n = 0;
const el = (maxLength = -1) => ({ maxLength });
function lim(text, want, field = el()) {
  assert.deepStrictEqual(limitsOf(field, text), want, `limits of ${JSON.stringify(text)}`);
  n++;
}

lim("Why Stripe?", { max_length: undefined, max_words: undefined });
lim("Why Stripe?", { max_length: 500, max_words: undefined }, el(500));
lim("Why Stripe? (max 1,000 characters)", { max_length: 1000, max_words: undefined });
lim("Tell us about a project. 500 character limit", { max_length: 500, max_words: undefined }, el(2000));
lim("Answer in 150 words or less", { max_length: undefined, max_words: 150 });
lim("Please write 200-300 words", { max_length: undefined, max_words: 300 });
lim("Please write 200 to 300 words", { max_length: undefined, max_words: 300 });
lim("Minimum 100 characters", { max_length: undefined, max_words: undefined });
lim("At least 50 words, at most 250 words", { max_length: undefined, max_words: 250 });
lim("Describe your experience 0/750", { max_length: 750, max_words: undefined });
lim("Cover note (up to 400 chars)", { max_length: 400, max_words: undefined });

const essay = "I built a retrieval system over SEC filings. It cites every sentence. It refuses instead of guessing when " +
  "the evidence is missing, which matters for finance.";
let [t, cut] = fitTo(essay, {});
assert.strictEqual(cut, false); assert.strictEqual(t, essay); n++;
[t, cut] = fitTo(essay, { max_length: 80 });
assert.strictEqual(cut, true); assert.strictEqual(t, "I built a retrieval system over SEC filings. It cites every sentence."); n++;
[t, cut] = fitTo(essay, { max_words: 10 });
assert.strictEqual(cut, true); assert.strictEqual(t, "I built a retrieval system over SEC filings."); n++;
[t, cut] = fitTo("one two three four five six seven eight nine ten", { max_length: 20 });
assert.strictEqual(cut, true); assert.ok(t.length <= 20 && !/\s$/.test(t) && t === "one two three four"); n++;
[t, cut] = fitTo(essay, { max_length: 500, max_words: 500 });
assert.strictEqual(cut, false); n++;

console.log(`length limits: ${n} cases passed`);
