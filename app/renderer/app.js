const $ = (id) => document.getElementById(id);
const chat = $("chat");
const input = $("input");
const form = $("form");

let busy = false;
let ready = false;
let thinking = null;
let confirmId = null;
let needsSetup = false;
let shownSetup = false;
const openTools = new Map(); // tool name -> chips still waiting for their result

function send(command) {
  window.jarvis.send(command);
}

function scrollDown() {
  chat.scrollTop = chat.scrollHeight;
}

function add(className, content) {
  const element = document.createElement("div");
  element.className = className;
  if (typeof content === "string") element.textContent = content;
  else if (content) element.append(content);
  chat.append(element);
  scrollDown();
  return element;
}

function showNotice(text) {
  const notice = $("notice");
  notice.textContent = text;
  notice.hidden = !text;
}

function setBusy(value) {
  busy = value;
  $("send").disabled = value || !ready;
  Face.set({ busy: value });
  if (value && !thinking) {
    thinking = add("thinking", "");
    thinking.innerHTML = "<span></span><span></span><span></span>";
  } else if (!value && thinking) {
    thinking.remove();
    thinking = null;
  }
}

function userMessage(text) {
  $("hero").hidden = true;
  add("message user", text);
}

function submit(text) {
  text = text.trim();
  if (!text || busy || !ready) return;
  userMessage(text);
  send({ type: "message", text });
  input.value = "";
  resize();
}

function resize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
}

// ---- modes and theme -------------------------------------------------------------------------------------------
const MODES = [
  { id: "type_text", short: "TEXT", title: "Text", note: "You type, Jarvis types back." },
  { id: "voice_text", short: "DICTATE", title: "Dictate", note: "You speak, Jarvis types back." },
  { id: "type_voice", short: "READ ALOUD", title: "Read aloud", note: "You type, Jarvis speaks back." },
  { id: "voice_voice", short: "VOICE", title: "Voice", note: "You speak, Jarvis speaks back." },
];
let mode = "type_text";
let theme = document.documentElement.dataset.theme || "dark";
let wake = "Jarvis";

function applyUi(next) {
  if (next.mode) mode = next.mode;
  if (next.theme) {
    theme = next.theme;
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("jarvis-theme", theme);
    } catch (error) {}
    window.jarvis.setTheme(theme);
  }
  const speaks = mode.startsWith("voice");
  document.body.dataset.input = speaks ? "voice" : "text";
  for (const button of document.querySelectorAll("#modes button")) button.setAttribute("aria-checked", String(button.dataset.mode === mode));
  const current = MODES.find((item) => item.id === mode);
  $("mode-note").textContent = current.note + (speaks ? ` Say \u201c${wake}\u201d to wake me.` : "");
  if (settingsOpen) renderSettings();
}

function buildModes() {
  const bar = $("modes");
  for (const item of MODES) {
    const button = document.createElement("button");
    button.dataset.mode = item.id;
    button.textContent = item.short;
    button.title = item.note;
    button.setAttribute("role", "radio");
    button.addEventListener("click", () => send({ type: "set_ui", mode: item.id }));
    bar.append(button);
  }
}

// ---- tool calls ------------------------------------------------------------------------------------------------
// A tool call in the console is one line; the ring shows the details while it runs
function toolCall(event) {
  const chip = document.createElement("div");
  chip.className = "tool running";
  chip.style.setProperty("--tc", Face.color(event.name));
  const badge = document.createElement("span");
  badge.className = "badge";
  const name = document.createElement("b");
  name.textContent = event.name;
  const time = document.createElement("span");
  time.className = "time";
  time.textContent = "running";
  chip.append(badge, name, time);
  add("tool-row", chip);
  // Keep the "thinking" dots below the newest line
  if (thinking) chat.append(thinking);
  if (!openTools.has(event.name)) openTools.set(event.name, []);
  openTools.get(event.name).push({ chip, time });
  Face.toolStart(event.name, event.server, event.input);
  scrollDown();
}

function toolResult(event) {
  const pending = openTools.get(event.name);
  const entry = pending && pending.shift();
  if (!entry) return;
  entry.chip.className = "tool " + (event.is_error ? "error" : "done");
  entry.time.textContent = event.seconds == null ? "" : `${event.seconds.toFixed(1)}s`;
  Face.toolEnd(event.name, !event.is_error, event.seconds);
}

function reply(event) {
  const panel = document.createElement("div");
  panel.className = "message jarvis";
  const label = document.createElement("div");
  label.className = "label";
  label.textContent = "JARVIS";
  const body = document.createElement("div");
  body.className = "body";
  body.innerHTML = window.renderMarkdown(event.text);
  const foot = document.createElement("div");
  foot.className = "foot";
  const calls = event.calls ? `${event.calls} tool call${event.calls === 1 ? "" : "s"}` : "no tools";
  foot.textContent = `${event.seconds.toFixed(1)}s · ${calls}`;
  panel.append(label, body, foot);
  if (event.cost) {
    const cost = document.createElement("div");
    cost.className = "cost";
    cost.textContent = event.cost;
    panel.append(cost);
  }
  if (thinking) chat.insertBefore(panel, thinking);
  else chat.append(panel);
  scrollDown();
}

function voiceState(state) {
  // "waiting" is the sleeping state: the microphone is on but Jarvis only reacts to its name
  Face.set({ voice: state === "idle" ? null : state });
}

function askApproval(event) {
  confirmId = event.id;
  $("confirm-message").textContent = event.message.trim();
  $("confirm").hidden = false;
  $("confirm-yes").focus();
}

function answer(approved) {
  if (confirmId == null) return;
  send({ type: "confirm", id: confirmId, approved });
  confirmId = null;
  $("confirm").hidden = true;
  input.focus();
}

// ---- the settings page -----------------------------------------------------------------------------------------
let settingsOpen = false;
let schema = [];
let draft = {}; // setting id -> the value typed in, for settings that were changed
let section = "Appearance";
let saving = false;
let savingError = "";
let statusTimer = null;

function setStatus(text, kind = "") {
  const status = $("settings-status");
  status.textContent = text;
  status.className = "sp-status " + kind;
  clearTimeout(statusTimer);
  if (kind === "ok") statusTimer = setTimeout(() => setStatus(""), 2600);
}

function openSettings(name) {
  if (name) section = name;
  settingsOpen = true;
  $("settings-page").hidden = false;
  setStatus("");
  renderSettings();
  send({ type: "get_settings" });
}

function closeSettings() {
  settingsOpen = false;
  $("settings-page").hidden = true;
  draft = {};
  input.focus();
}

function updateSaveState() {
  const count = Object.keys(draft).length;
  $("settings-save").disabled = saving || count === 0;
  $("settings-hint").textContent = count ? `${count} unsaved change${count === 1 ? "" : "s"}` : "Saved to config.conf in the project folder.";
  for (const row of document.querySelectorAll(".sp-row[data-id]")) row.classList.toggle("changed", row.dataset.id in draft);
}

function setDraft(id, value, original) {
  if (value === original) delete draft[id];
  else draft[id] = value;
  updateSaveState();
}

function row(title, help, control, options = {}) {
  const element = document.createElement("div");
  element.className = "sp-row";
  if (options.id) element.dataset.id = options.id;
  const label = document.createElement("div");
  label.className = "title";
  label.textContent = title.charAt(0).toUpperCase() + title.slice(1);
  if (options.required) {
    const badge = document.createElement("em");
    badge.textContent = "required";
    label.append(badge);
  }
  element.append(label);
  if (help) {
    const text = document.createElement("div");
    text.className = "help";
    text.textContent = help;
    element.append(text);
  }
  const wrap = document.createElement("div");
  wrap.className = "control";
  wrap.append(...[].concat(control));
  element.append(wrap);
  return element;
}

function segmented(items, current, onPick) {
  const group = document.createElement("div");
  group.className = "seg";
  group.setAttribute("role", "radiogroup");
  for (const [value, label] of items) {
    const button = document.createElement("button");
    button.textContent = label;
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(value === current));
    button.addEventListener("click", () => onPick(value));
    group.append(button);
  }
  return group;
}

function fieldRow(f) {
  const original = f.type === "secret" ? "" : f.value ?? "";
  const value = f.id in draft ? draft[f.id] : original;
  let control;
  if (f.type === "bool") {
    const label = document.createElement("label");
    label.className = "switch";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = value === "true";
    box.addEventListener("change", () => setDraft(f.id, box.checked ? "true" : "false", original));
    label.append(box, document.createElement("span"));
    control = label;
  } else if (f.type === "select") {
    const select = document.createElement("select");
    for (const option of f.options || []) select.add(new Option(option, option));
    if (value && !(f.options || []).includes(value)) select.add(new Option(value, value));
    select.value = value;
    select.addEventListener("change", () => setDraft(f.id, select.value, original));
    control = select;
  } else if (f.type === "secret") {
    const box = document.createElement("input");
    box.type = "password";
    box.autocomplete = "off";
    box.spellcheck = false;
    box.placeholder = draft[f.id] === "" ? "will be removed" : f.set ? f.hint : "not set";
    box.value = draft[f.id] || "";
    box.addEventListener("input", () => {
      // Left empty means "keep what is saved"
      if (box.value) draft[f.id] = box.value;
      else delete draft[f.id];
      updateSaveState();
    });
    control = [box];
    if (f.set) {
      const remove = document.createElement("button");
      remove.className = "sp-link";
      remove.textContent = "REMOVE";
      remove.addEventListener("click", () => {
        draft[f.id] = "";
        renderSettings();
      });
      control.push(remove);
    }
  } else {
    const box = document.createElement("input");
    box.type = "text";
    box.value = value;
    box.spellcheck = false;
    if (f.options) {
      const list = document.createElement("datalist");
      list.id = "dl-" + f.id.replace(/\W/g, "-");
      for (const option of f.options) list.append(new Option(option));
      box.setAttribute("list", list.id);
      document.body.append(list);
    }
    box.addEventListener("input", () => setDraft(f.id, box.value, original));
    control = box;
  }
  return row(f.label, f.help, control, { id: f.id, required: f.required });
}

function renderAppearance(form) {
  form.append(
    row("Theme", "Light or dark for the whole window.", segmented([["light", "LIGHT"], ["dark", "DARK"]], theme, (value) => send({ type: "set_ui", theme: value })))
  );
}

function renderSettings() {
  const names = ["Appearance", ...schema.map((item) => item.title)];
  if (!names.includes(section)) section = "Appearance";
  const nav = $("settings-nav");
  nav.replaceChildren();
  for (const name of names) {
    const button = document.createElement("button");
    button.textContent = name;
    button.className = name === section ? "active" : "";
    if (name === "Keys" && needsSetup) button.append(Object.assign(document.createElement("span"), { className: "dot" }));
    button.addEventListener("click", () => {
      section = name;
      renderSettings();
    });
    nav.append(button);
  }
  const formElement = $("settings-form");
  formElement.replaceChildren();
  formElement.style.animation = "none";
  void formElement.offsetWidth;
  formElement.style.animation = "";
  if (section === "Appearance") {
    renderAppearance(formElement);
  } else {
    const data = schema.find((item) => item.title === section);
    if (data) {
      if (section === "Keys" && needsSetup) {
        const banner = document.createElement("div");
        banner.className = "sp-banner";
        banner.textContent = "ADD YOUR ANTHROPIC API KEY TO GET STARTED.";
        formElement.append(banner);
      }
      if (data.note) {
        const note = document.createElement("p");
        note.className = "sp-note";
        note.textContent = data.note;
        formElement.append(note);
      }
      for (const f of data.fields) formElement.append(fieldRow(f));
      if (section === "Voice") {
        const test = document.createElement("button");
        test.className = "sp-test";
        test.textContent = "TEST VOICE";
        test.addEventListener("click", () => send({ type: "voice_test" }));
        formElement.append(test);
      }
    }
  }
  updateSaveState();
}

// ---- the first-run welcome screen ------------------------------------------------------------------------------
let welcomeBusy = false;
let welcomeKey = "";

function setWelcomeStatus(text, kind = "") {
  $("wl-status").textContent = text;
  $("wl-status").className = "wl-status " + kind;
}

function lockWelcome(locked) {
  welcomeBusy = locked;
  for (const element of $("welcome-form").elements) element.disabled = locked;
  if (!locked) $("wl-go").disabled = !$("wl-anthropic").value.trim();
}

function showWelcome() {
  $("welcome").hidden = false;
  $("wl-anthropic").focus();
}

function hideWelcome() {
  if ($("welcome").hidden) return;
  $("welcome").hidden = true;
  lockWelcome(false);
  setWelcomeStatus("");
  input.focus();
}

function submitWelcome() {
  welcomeKey = $("wl-anthropic").value.trim();
  if (!welcomeKey || welcomeBusy) return;
  lockWelcome(true);
  setWelcomeStatus("CHECKING YOUR KEY…");
  send({ type: "verify_key", key: welcomeKey });
}

function applyProfile(event) {
  $("greeting").textContent = event.greeting;
  if (event.wake_word) {
    wake = event.wake_word.charAt(0).toUpperCase() + event.wake_word.slice(1);
    Face.setWakeWord(wake);
  }
  needsSetup = event.needs_setup;
  applyUi({ mode: event.mode, theme: event.theme });
  if (needsSetup && !shownSetup) {
    shownSetup = true;
    showWelcome();
  } else if (!needsSetup) {
    hideWelcome();
  }
  if (settingsOpen) renderSettings();
}

const handlers = {
  ready(event) {
    ready = true;
    Face.set({ starting: false });
    input.placeholder = "Message Jarvis";
    applyProfile(event);
    setBusy(false);
    if (!settingsOpen) input.focus();
  },
  profile: applyProfile,
  ui: applyUi,
  settings(event) {
    schema = event.sections;
    if (saving) {
      saving = false;
      if (savingError) {
        setStatus(savingError, "bad");
      } else {
        draft = {};
        setStatus("SAVED ✓", "ok");
      }
      savingError = "";
    }
    if (settingsOpen) renderSettings();
  },
  key_check(event) {
    if (!event.ok) {
      lockWelcome(false);
      setWelcomeStatus(event.message, "bad");
      $("wl-anthropic").focus();
      return;
    }
    // The key is good: save it with whatever else was filled in. The profile that comes back closes the screen.
    const values = { "anthropic.anthropic_api_key": welcomeKey };
    for (const [id, field] of [["fish.api_key", "wl-fish"], ["personal.name", "wl-name"], ["personal.zip_code", "wl-zip"]]) {
      if ($(field).value.trim()) values[id] = $(field).value.trim();
    }
    setWelcomeStatus(event.message || "SAVING…");
    send({ type: "save_settings", values });
  },
  busy: () => setBusy(true),
  idle: () => setBusy(false),
  tool_call: toolCall,
  tool_result: toolResult,
  reply,
  error(event) {
    if (welcomeBusy) {
      lockWelcome(false);
      setWelcomeStatus(event.message, "bad");
    }
    add("message error", event.message);
    Face.alert();
    if (saving) savingError = event.message;
    else if (settingsOpen) setStatus(event.message, "bad");
  },
  fatal(event) {
    ready = false;
    Face.set({ starting: false });
    input.placeholder = "Jarvis isn't running";
    setBusy(false);
    Face.alert();
    showNotice(event.message);
    $("send").disabled = true;
  },
  update(event) {
    const pill = $("update-pill");
    pill.hidden = false;
    pill.disabled = event.state !== "ready";
    pill.textContent = event.state === "ready" ? `RESTART TO UPDATE (${event.version})` : `DOWNLOADING ${event.version}…`;
  },
  confirm: askApproval,
  levels: (event) => Face.levels(event),
  voice_state(event) {
    voiceState(event.state);
  },
  heard(event) {
    if (event.text) userMessage(event.text);
  },
  note(event) {
    add("note", event.text);
  },
};

window.jarvis.onEvent((event) => {
  const handler = handlers[event.type];
  if (handler) handler(event);
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  submit(input.value);
});
input.addEventListener("input", resize);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    submit(input.value);
  }
});
document.querySelectorAll(".suggestions button").forEach((button) =>
  button.addEventListener("click", () => submit(button.dataset.prompt))
);
$("settings-open").addEventListener("click", () => openSettings());
$("update-pill").addEventListener("click", () => window.jarvis.installUpdate());
$("welcome-form").addEventListener("submit", (event) => {
  event.preventDefault();
  submitWelcome();
});
$("wl-anthropic").addEventListener("input", () => ($("wl-go").disabled = welcomeBusy || !$("wl-anthropic").value.trim()));
$("wl-skip").addEventListener("click", hideWelcome);
$("settings-back").addEventListener("click", closeSettings);
$("settings-save").addEventListener("click", () => {
  saving = true;
  savingError = "";
  setStatus("SAVING…");
  updateSaveState();
  send({ type: "save_settings", values: draft });
});
$("confirm-yes").addEventListener("click", () => answer(true));
$("confirm-no").addEventListener("click", () => answer(false));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (confirmId != null) answer(false);
    else if (settingsOpen) closeSettings();
  }
});

buildModes();
applyUi({});
input.placeholder = "Starting up…";
window.jarvis.setTheme(document.documentElement.dataset.theme || "dark");
setBusy(false);
