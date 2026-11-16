// Run: node tests/answer_matching.test.js   (also run by tests/test_extension_js.py)
// Loads the answer-matching block from extension/content.js and checks that every way of writing an answer in
// profile.yaml picks the right option among the wordings real application forms use.
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const src = fs.readFileSync(path.join(__dirname, "../extension/content.js"), "utf8");
const block = src.slice(src.indexOf("// ── answer matching"), src.indexOf("// ── end answer matching"));
const { meaning, pick, asText } = new Function(block + "; return { meaning, pick, asText };")();

const opts = (...texts) => texts.map((text) => ({ text }));
let n = 0;
function expect(kind, answers, options, want) {
  for (const a of answers) {
    const got = pick(opts(...options), a, kind);
    assert.strictEqual(got && got.text, want, `${kind}: answer "${a}" picked ${JSON.stringify(got && got.text)}, want "${want}"`);
    n++;
  }
}

const YES_ANSWERS = ["Yes", "yes", "Y", "y", "YES", "True", "yes I am", "Yes, I will", "I am", "I will"];
const NO_ANSWERS = ["No", "no", "N", "NO", "false", "No, I won't", "I am not", "I will not", "I don't", "not", "None"];
const YESNO_FORMS = [
  ["Select...", "Yes", "No"],
  ["Yes, I am authorized to work in the U.S.", "No, I am not authorized to work in the U.S."],
  ["I will require sponsorship", "I will not require sponsorship"],
  ["Yes - I will need sponsorship now or in the future", "No - I will not need sponsorship"],
  ["Y", "N"],
  ["True", "False"],
];
for (const form of YESNO_FORMS) {
  const [yes, no] = form.filter((t) => t !== "Select...");
  expect("yesno", YES_ANSWERS, form, yes);
  expect("yesno", NO_ANSWERS, form, no);
}
expect("yesno", ["Decline to answer", "prefer not to say"], ["Yes", "No", "I prefer not to answer"], "I prefer not to answer");
assert.strictEqual(pick(opts("Yes", "No"), "maybe", "yesno"), undefined, "unclear answers must not guess");

// Visa / work authorization status
const VISA_FORMS = [
  ["U.S. Citizen", "Green Card Holder / Permanent Resident", "F-1 Student Visa (OPT/CPT)", "H-1B", "Other"],
  ["US Citizen", "Permanent Resident", "F1", "H1B", "TN", "Other"],
  ["Citizen", "Green card", "F-1 Visa", "H-1B Visa", "J-1 Visa"],
  ["Student visa (F-1)", "Work visa (H-1B)", "US citizen or permanent resident"],
];
for (const form of VISA_FORMS) {
  const f1 = form.find((t) => /f-?1|student/i.test(t));
  expect("visa", ["F1", "F-1", "f-1", "F-1 Student", "F1 student visa", "F-1 student (CPT/OPT eligible)", "STEM OPT",
                  "F-1 OPT", "OPT", "CPT", "Student Visa"], form, f1);
  const h = form.find((t) => /h-?1-?b/i.test(t));
  expect("visa", ["H1B", "H-1B", "h1-b"], form, h);
}

// Veterans: every common wording of "not a veteran", on every common option set.
const VET_FORMS = [
  ["I am not a protected veteran", "I identify as one or more of the classifications of protected veteran",
   "I don't wish to answer"],
  ["No", "Yes", "Decline to self-identify"],
  ["I am not a veteran", "I am a veteran", "Prefer not to say"],
  ["Not a Veteran", "Protected Veteran", "Decline to Answer"],
];
const NOT_VET = ["No", "no", "N", "Not a veteran", "not veteran", "I am not a protected veteran", "I'm not a veteran",
                 "Non-veteran", "Never served", "None"];
for (const form of VET_FORMS) expect("veteran", NOT_VET, form, form[0]);
for (const form of VET_FORMS) expect("veteran", ["Decline", "I don't wish to answer", "Prefer not to say"], form, form[2]);

// Disability
const DIS_FORMS = [
  ["Yes, I have a disability (or previously had a disability)",
   "No, I do not have a disability and have not had one in the past", "I do not want to answer"],
  ["Yes", "No", "Decline to self-identify"],
  ["I have a disability", "I don't have a disability", "Prefer not to answer"],
];
for (const form of DIS_FORMS) {
  expect("disability", ["No", "no", "N", "No disability", "I do not have a disability", "I don't have a disability", "None"], form, form[1]);
  expect("disability", ["Decline", "Prefer not to say"], form, form[2]);
}

// Gender
const GENDER_FORMS = [["Male", "Female", "Non-binary", "Decline To Self Identify"],
                      ["Man", "Woman", "Non-binary / third gender", "Prefer not to say"],
                      ["Female", "Male", "I don't wish to answer"]];
for (const form of GENDER_FORMS) {
  const male = form.find((t) => /^(male|man)$/i.test(t));
  expect("gender", ["Male", "male", "M", "Man", "he/him male"], form, male);
}

// Race / ethnicity
const RACE_FORMS = [
  ["Hispanic or Latino", "White (Not Hispanic or Latino)", "Black or African American (Not Hispanic or Latino)",
   "Asian (Not Hispanic or Latino)", "Native Hawaiian or Other Pacific Islander (Not Hispanic or Latino)",
   "Two or More Races (Not Hispanic or Latino)", "Decline To Self Identify"],
  ["Asian", "Black", "White", "Hispanic/Latino", "Prefer not to say"],
  ["East Asian", "South Asian", "White", "Decline"],
];
for (const form of RACE_FORMS) {
  const asian = form.find((t) => /asian/i.test(t) && !/east/i.test(t)) || form.find((t) => /asian/i.test(t));
  if (form !== RACE_FORMS[2]) expect("race", ["Asian", "asian", "South Asian", "Asian (Indian)", "Indian"], form, asian);
}
// Split Asian options: a specific answer picks its option; plain "Asian" is ambiguous and is left for you.
expect("race", ["South Asian", "Asian (Indian)", "Indian", "south asian"], RACE_FORMS[2], "South Asian");
assert.strictEqual(pick(opts(...RACE_FORMS[2]), "Asian", "race"), undefined);

// Hispanic / Latino yes-no
expect("yesno", ["No", "Not Hispanic or Latino"], ["Yes", "No", "Decline To Self Identify"], "No");

// Months and degrees (education sections)
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
expect("month", ["12", "Dec", "December", "december"], ["Select...", ...MONTHS], "December");
expect("month", ["1", "01", "Jan"], ["Select...", ...MONTHS.map((m) => m.slice(0, 3))], "Jan");
expect("degree", ["Master of Science", "MS", "M.S.", "Masters", "Master's"],
       ["Bachelor's Degree", "Master's Degree", "Master of Business Administration (M.B.A.)", "Doctor of Philosophy (Ph.D.)"], "Master's Degree");
expect("degree", ["Master of Science"], ["Associate's", "Bachelor of Science (B.S.)", "Master of Science (M.S.)", "PhD"], "Master of Science (M.S.)");

// Free-text boxes get a clean Yes / No whatever the profile says.
assert.strictEqual(asText("yesno", "y"), "Yes");
assert.strictEqual(asText("yesno", "I will not"), "No");
assert.strictEqual(asText("visa", "F-1 student"), "F-1 student");
assert.strictEqual(meaning("yesno", "Select..."), null);

// Country lists write the US many ways (Stripe's list just says "US").
const STRIPE_COUNTRIES = ["Australia", "Canada", "India", "The Netherlands", "UAE", "UK", "US", "Other"];
expect("country", ["United States", "USA", "US", "U.S.", "United States of America"], STRIPE_COUNTRIES, "US");
expect("country", ["United States"], ["Canada", "United States", "United States Minor Outlying Islands"], "United States");
expect("country", ["United States"], ["Canada", "United States of America", "Mexico"], "United States of America");
expect("country", ["United States"], ["Canada +1", "United States +1"], "United States +1");
expect("country", ["India"], STRIPE_COUNTRIES, "India");
expect("country", ["Netherlands"], STRIPE_COUNTRIES, "The Netherlands");
expect("country", ["United Kingdom"], STRIPE_COUNTRIES, "UK");

console.log(`answer matching: ${n} cases passed`);
