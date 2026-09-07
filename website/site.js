"use strict";
const platforms = {
  linux: {command: "curl -fsSL https://loopmaster.box2ai.com/LoopROS/install.sh | sh", note: "Linux hosted installation tested with Python 3.8 bootstrapping a uv Python 3.12 runtime. Older OS compatibility still depends on TLS, libc and available runtimes."},
  mac: {command: "curl -fsSL https://loopmaster.box2ai.com/LoopROS/install.sh | sh", note: "Choose a bootstrap Python 3.8+ compatible with your macOS version and Intel/Apple Silicon CPU. Native macOS validation is pending; simulation wheels have separate limits."},
  windows: {command: "Invoke-WebRequest -Uri https://loopmaster.box2ai.com/LoopROS/install.ps1 -OutFile loop-install.ps1 -ErrorAction Stop\npowershell -NoProfile -ExecutionPolicy Bypass -File .\\loop-install.ps1", note: "Windows 10/11: install a compatible Python 3.8+ first. Bypass applies only to this PowerShell process; inspect the local script before running. Native OS validation is pending."},
  legacy: {command: "ssh -t USER@HOST '$HOME/.local/bin/loop'", note: "Replace USER/HOST with a compatible machine where Loop ROS is already installed. Windows 7/8 and older unsupported systems use an OS-compatible SSH client. No local USB/camera forwarding is included."}
};
platforms.cmd = {
  command: "curl.exe -fSLo loop-install.ps1 https://loopmaster.box2ai.com/LoopROS/install.ps1 && powershell -NoProfile -ExecutionPolicy Bypass -File .\\loop-install.ps1",
  note: "Windows 10/11 Command Prompt (CMD). Python 3.8+ is required to bootstrap. The installer runs only after the download succeeds. Native Windows validation is pending."
};
const chinese = document.documentElement && document.documentElement.lang === "zh-CN";
const zhNotes = {
  linux: "已验证 Linux 下通过 Python 3.8 引导 uv Python 3.12 环境完成安装。旧系统还需满足 TLS、libc 和运行环境兼容性。",
  mac: "macOS 支持 Intel 与 Apple Silicon；请选择兼容系统版本的 Python 3.8+ 引导解释器。尚未完成 macOS 原生实测，仿真依赖另有兼容要求。",
  windows: "Windows 10/11 PowerShell：先安装兼容的 Python 3.8+。下载后检查脚本，再运行安装命令；Bypass 只作用于该 PowerShell 进程。尚未完成 Windows 原生实测。",
  cmd: "Windows 10/11 命令提示符（CMD）：需要 Python 3.8+ 启动安装器。下载成功后才执行安装脚本。尚未完成 Windows 原生实测。",
  legacy: "将 USER/HOST 替换为已安装 Loop ROS 的兼容主机。Windows 7/8 等旧系统通过 SSH 使用，不包含本地 USB 或摄像头转发。"
};
let selected = "linux";
const command = document.getElementById("command");
const light = document.getElementById("light");
const status = document.getElementById("copy-status");
function update() {
  light.disabled = selected === "legacy";
  command.textContent = platforms[selected].command + (light.checked && selected !== "legacy" ? (selected === "linux" || selected === "mac" ? " -s -- --terminal-only" : " --terminal-only") : "");
  document.getElementById("platform-note").textContent = (chinese ? zhNotes[selected] : platforms[selected].note);
  document.querySelectorAll("[data-platform]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.platform === selected)));
  status.textContent = "";
}
document.querySelectorAll("[data-platform]").forEach(button => button.addEventListener("click", () => {selected = button.dataset.platform; update();}));
light.addEventListener("change", update);
document.getElementById("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(command.textContent);
    status.textContent = chinese ? "命令已复制，请粘贴到终端运行。" : "Command copied. Paste it into your terminal.";
  } catch (_) {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(command);
    selection.removeAllRanges(); selection.addRange(range);
    status.textContent = chinese ? "命令已选中，请按 Ctrl+C / Command+C 复制。" : "Command selected. Press Ctrl+C / Command+C to copy.";
  }
});

update();
