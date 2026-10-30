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

function startBackend(root, candidates) {
  const [command, ...args] = candidates[0];
  const child = spawn(command, [...args, "-m", "jarvis.server"], {
    cwd: root,
    env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
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
    if (error.code === "ENOENT" && candidates.length > 1) return startBackend(root, candidates.slice(1));
    send({ type: "fatal", message: `Couldn't start Python (${error.message}). Install Python 3.10+ or set JARVIS_PYTHON.` });
  });
  child.on("exit", (code) => {
    if (quitting || backend !== child) return;
    send({ type: "fatal", message: `Jarvis' back end stopped (exit code ${code}).\n${stderrTail}`.trim() });
  });
}

function launchBackend() {
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

function createWindow() {
  win = new BrowserWindow({
    width: 1360,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#e5e4df",
    title: "J.A.R.V.I.S.",
    titleBarStyle: "hidden",
    titleBarOverlay: { color: "#e5e4df", symbolColor: "#0c0c0d", height: 48 },
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.setMenuBarVisibility(false);
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

// The window's own buttons (minimize, close) are drawn by Electron, so they have to be told about the theme
const THEME_COLORS = { light: { color: "#e5e4df", symbolColor: "#0c0c0d" }, dark: { color: "#09090b", symbolColor: "#ecece8" } };
ipcMain.on("jarvis:theme", (_event, theme) => {
  const colors = THEME_COLORS[theme] || THEME_COLORS.light;
  if (win && !win.isDestroyed()) {
    win.setTitleBarOverlay({ ...colors, height: 48 });
    win.setBackgroundColor(colors.color);
  }
});

ipcMain.on("jarvis:command", (_event, command) => {
  if (backend && backend.stdin.writable) backend.stdin.write(JSON.stringify(command) + "\n");
});

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
