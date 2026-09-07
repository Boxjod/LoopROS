"use strict";
const platforms = {
  linux: {command: "curl -fsSL https://8.134.90.171/LoopROS/install.sh | sh", note: "Ubuntu 20.04 tested with private Python 3.13. Ubuntu 16.04/18.04 need a compatible private Python or SSH. 22.04/24.04/25.04 are not individually verified."},
  mac: {command: "curl -fsSL https://8.134.90.171/LoopROS/install.sh | sh", note: "Choose Python 3.10+ compatible with your macOS version and Intel/Apple Silicon CPU. Native macOS validation is pending; simulation wheels have separate limits."},
  windows: {command: "powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\install.ps1", note: "Windows 10/11: install a compatible Python 3.10+ first. Bypass applies only to this PowerShell process; inspect the local script before running. Native OS validation is pending."},
  legacy: {command: "ssh -t USER@HOST '$HOME/.local/bin/loop'", note: "Replace USER/HOST with a compatible machine where Loop ROS is already installed. Windows 7/8 and older unsupported systems use an OS-compatible SSH client. No local USB/camera forwarding is included."}
};
let selected = "linux";
const command = document.getElementById("command");
const light = document.getElementById("light");
const status = document.getElementById("copy-status");
function update() {
  light.disabled = selected === "legacy";
  command.textContent = platforms[selected].command + (light.checked && selected !== "legacy" ? (selected === "linux" || selected === "mac" ? " -s -- --terminal-only" : " --terminal-only") : "");
  document.getElementById("platform-note").textContent = platforms[selected].note;
  document.querySelectorAll("[data-platform]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.platform === selected)));
  status.textContent = "";
}
document.querySelectorAll("[data-platform]").forEach(button => button.addEventListener("click", () => {selected = button.dataset.platform; update();}));
light.addEventListener("change", update);
document.getElementById("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(command.textContent);
    status.textContent = "Command copied. Paste it into your terminal.";
  } catch (_) {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(command);
    selection.removeAllRanges(); selection.addRange(range);
    status.textContent = "Command selected. Press Ctrl+C / Command+C to copy.";
  }
});

update();
