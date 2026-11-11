// The caption settings page. Values are kept in chrome.storage.local; content.js reads them.
const DEFAULTS = { widthPercent: 85, fontSize: 26, holdFactor: 1, maxLines: 3 };
const SAMPLE = [
  "Good afternoon, how are you feeling today?",
  "The meeting will start tomorrow at 9 a.m., so please send me the contract before Friday so that our lawyers can review it.",
  "Can we discuss the payment schedule at the next meeting?",
];

const ids = Object.keys(DEFAULTS);
const input = (id) => document.getElementById(id);
const labels = {
  widthPercent: (v) => `${v}% of the screen`,
  fontSize: (v) => `${v} px`,
  holdFactor: (v) => (Number(v) === 1 ? "normal" : `${v} x normal`),
  maxLines: (v) => `${v}`,
};
const valueBox = { widthPercent: "widthValue", fontSize: "fontValue", holdFactor: "holdValue", maxLines: "linesValue" };

function show(values) {
  for (const id of ids) {
    input(id).value = values[id];
    input(valueBox[id]).textContent = labels[id](values[id]);
  }
  const sample = input("sample");
  // The preview is a fraction of this window, not of a full screen, so it is only a guide.
  sample.style.maxWidth = `${values.widthPercent}%`;
  sample.style.fontSize = `${Math.round(values.fontSize * 0.8)}px`;
  sample.replaceChildren(
    ...SAMPLE.slice(0, values.maxLines).map((text) => {
      const row = document.createElement("div");
      row.textContent = text;
      return row;
    })
  );
}

function current() {
  const values = {};
  for (const id of ids) values[id] = Number(input(id).value);
  return values;
}

function flashSaved() {
  const el = input("saved");
  el.textContent = "Saved";
  clearTimeout(flashSaved.t);
  flashSaved.t = setTimeout(() => (el.textContent = ""), 1500);
}

chrome.storage.local.get(DEFAULTS, (saved) => show({ ...DEFAULTS, ...saved }));

for (const id of ids) {
  input(id).addEventListener("input", () => {
    const values = current();
    show(values);
    chrome.storage.local.set(values, flashSaved);
  });
}

input("reset").addEventListener("click", () => {
  show(DEFAULTS);
  chrome.storage.local.set(DEFAULTS, flashSaved);
});
