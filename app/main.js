const { app, BrowserWindow, ipcMain, shell } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

// The Python side lives in the project folder (jarvis/server.py). Find it next to the app or any folder above it.
function findRoot() {
  const starts = [process.env.JARVIS_HOME, process.env.PORTABLE_EXECUTABLE_DIR, path.dirname(process.execPath), __dirname];
  for (const start of starts.filter(Boolean)) {
    let dir = path.resolve(start);
    for (;;) {
      if (fs.existsSync(path.join(dir, "jarvis", "server.py"))) return dir;
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  return null;
}

let win = null;
let backend = null;
let quitting = false;
let stderrTail = "";

function send(event) {
  if (win && !win.isDestroyed()) win.webContents.send("jarvis:event", event);
}

function startBackend(root, candidates, extraEnv = {}) {
  const [command, ...args] = candidates[0];
  const child = spawn(command, [...args, "-m", "jarvis.server"], {
    cwd: root,
    env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1", ...extraEnv },
    windowsHide: true,
  });
  backend = child;

  let buffer = "";
  child.stdout.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    let newline;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (!line) continue;
      try {
        send(JSON.parse(line));
      } catch {
        stderrTail = (stderrTail + line + "\n").slice(-2000);
      }
    }
  });
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => {
    stderrTail = (stderrTail + chunk).slice(-2000);
  });
  child.on("error", (error) => {
    if (error.code === "ENOENT" && candidates.length > 1) return startBackend(root, candidates.slice(1), extraEnv);
    send({ type: "fatal", message: `Couldn't start Python (${error.message}). Install Python 3.10+ or set JARVIS_PYTHON.` });
  });
  child.on("exit", (code) => {
    if (quitting || backend !== child) return;
    send({ type: "fatal", message: `Jarvis' back end stopped (exit code ${code}).\n${stderrTail}`.trim() });
  });
}

// The installed app carries its own Python and the jarvis code in its resources folder (see scripts/prepare-backend.ps1),
// and keeps what belongs to the user (config.conf, the conversation) in the user's profile, not in the install folder.
function bundledBackend() {
  if (!app.isPackaged) return null;
  const python = path.join(process.resourcesPath, "python", "python.exe");
  const code = path.join(process.resourcesPath, "backend");
  return fs.existsSync(python) && fs.existsSync(path.join(code, "jarvis", "server.py")) ? { python, code } : null;
}

function launchBackend() {
  const bundled = bundledBackend();
  if (bundled) {
    startBackend(bundled.code, [[bundled.python]], { JARVIS_DATA: app.getPath("userData") });
    return;
  }
  const root = findRoot();
  if (!root) {
    send({ type: "fatal", message: "Couldn't find the Jarvis project folder (jarvis/server.py). Put Jarvis.exe inside it, or set JARVIS_HOME." });
    return;
  }
  const candidates = [];
  if (process.env.JARVIS_PYTHON) candidates.push([process.env.JARVIS_PYTHON]);
  candidates.push(["python"], ["py", "-3"]);
  startBackend(root, candidates);
}

// The window's own buttons (minimize, close) are drawn by Electron, so they have to be told about the theme. The theme
// is saved in a small file, so the window starts in the right colors instead of flashing the other theme while the page
// loads, and it is applied again whenever Windows redraws that part of the window (it can reset it).
const THEME_COLORS = { light: { color: "#e5e4df", symbolColor: "#0c0c0d" }, dark: { color: "#09090b", symbolColor: "#ecece8" } };
let theme = "dark";

function themeFile() {
  return path.join(app.getPath("userData"), "theme.txt");
}

function loadTheme() {
  try {
    const saved = fs.readFileSync(themeFile(), "utf8").trim();
    if (THEME_COLORS[saved]) theme = saved;
  } catch {}
}

function applyTheme() {
  if (!win || win.isDestroyed()) return;
  const colors = THEME_COLORS[theme];
  win.setTitleBarOverlay({ ...colors, height: 48 });
  win.setBackgroundColor(colors.color);
}

function createWindow() {
  loadTheme();
  win = new BrowserWindow({
    width: 1360,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: THEME_COLORS[theme].color,
    title: "J.A.R.V.I.S.",
    // Packaged builds carry the icon inside the exe; this is for `npm start`
    ...(app.isPackaged ? {} : { icon: path.join(__dirname, "jarvis-logo.ico") }),
    titleBarStyle: "hidden",
    titleBarOverlay: { ...THEME_COLORS[theme], height: 48 },
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.setMenuBarVisibility(false);
  for (const name of ["maximize", "unmaximize", "restore", "enter-full-screen", "leave-full-screen", "focus", "show"]) win.on(name, applyTheme);
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith("file://")) {
      event.preventDefault();
      if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    }
  });
  // Start the back end once the page can receive its events.
  win.webContents.once("did-finish-load", launchBackend);
}

ipcMain.on("jarvis:theme", (_event, next) => {
  if (!THEME_COLORS[next]) return;
  theme = next;
  try {
    fs.writeFileSync(themeFile(), theme);
  } catch {}
  applyTheme();
});

ipcMain.on("jarvis:command", (_event, command) => {
  if (backend && backend.stdin.writable) backend.stdin.write(JSON.stringify(command) + "\n");
});

// The installed app and a copy run from the project folder (npm start, or the portable jarvis.exe) each get their own
// profile. Sharing one would also share the single-instance lock, and whichever started second would quit without a word.
if (!bundledBackend() && !app.commandLine.hasSwitch("user-data-dir")) app.setPath("userData", path.join(app.getPath("appData"), "jarvis-portable"));

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(createWindow);
}

app.on("before-quit", () => {
  quitting = true;
  if (backend) {
    // Takes the whole tree down, since the back end may have a PowerShell child running.
    spawn("taskkill", ["/pid", String(backend.pid), "/t", "/f"], { windowsHide: true });
  }
});
app.on("window-all-closed", () => app.quit());
