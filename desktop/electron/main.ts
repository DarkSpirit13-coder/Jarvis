/** Electron entrypoint for the desktop JARVIS shell. */
import { app, BrowserWindow } from "electron";

function createWindow() {
  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  const frontendUrl = process.env.JARVIS_FRONTEND_URL ?? "http://localhost:3000";
  void window.loadURL(frontendUrl);
}

void app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

