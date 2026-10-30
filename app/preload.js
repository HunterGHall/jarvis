const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jarvis", {
  send: (command) => ipcRenderer.send("jarvis:command", command),
  setTheme: (theme) => ipcRenderer.send("jarvis:theme", theme),
  onEvent: (handler) => ipcRenderer.on("jarvis:event", (_event, data) => handler(data)),
});
