# Platform support — 2026-09-05

Loop ROS separates the API terminal, simulation and hardware adapters. Terminal installation does not certify ROS, CUDA, motor SDKs or simulation wheels.

| Requested platform | Terminal route | Validation / limits |
| --- | --- | --- |
| Ubuntu 16.04 | Compatible private Python 3.10+, otherwise SSH | Untested; stock Python insufficient; libc/TLS/wheels may block installation |
| Ubuntu 18.04 | Compatible private Python 3.10+, otherwise SSH | Untested; stock Python insufficient |
| Ubuntu 20.04 | Python 3.8 bootstrap → uv Python 3.12 `.venv` | Fresh terminal install, external launcher and repeat install verified locally on 2026-09-07; runtime also previously verified with Python 3.13.14 |
| Ubuntu 22.04 | Compatible Python + installer | CI configured, not run here |
| Ubuntu 24.04 | Compatible Python + installer | CI configured, not run here |
| Ubuntu 25.04 | Compatible Python + installer | Untested; check repository/lifecycle availability |
| Other Linux | Compatible Python + installer | No distro-wide certification; package managers and ABIs differ |
| Windows 7 / 8 | SSH to compatible host | Native unsupported; no local USB/camera forwarding |
| Windows 8.1 | Conditional interpreter compatibility | Not an application support promise; untested |
| Windows 10 / 11 | Python 3.10+ and user cmd launchers | Platform branches tested with substitutes; native tests pending |
| macOS Intel / Apple Silicon | OS-compatible Python 3.10+ | Native tests pending; latest-runner CI is not every release |
| Older macOS without compatible Python | SSH | Not a native port |

## Implemented boundaries

- Terminal: prompt-toolkit input, POSIX flock / Windows byte lock, Windows queued stdin, Windows venv layout and user PATH installer.
- Owned policy services: POSIX process groups / Windows taskkill process tree. This is not a hardware safety mechanism.
- macOS passive viewer uses mjpython; wheels, display and drivers still need verification.
- Linux device discovery uses /dev and /sys; Linux serial receive uses the owned native adapter. Windows COM and macOS serial discovery/receive use lazy-loaded pySerial (installed by platform-specific package dependencies). Windows/macOS branches have substitute tests only; native device tests remain pending. Their inventory scope is serial ports and associated USB descriptors, not all USB/camera/input devices. No motor transmission/control added.
- Clipboard images: Linux wl-paste/xclip only; use file attachments elsewhere. Video extraction requires external ffmpeg.
- ROS/ROS 2, GPU models and vendor SDKs require separate integration and validation.

## Evidence

Ubuntu 20.04.6 x86_64 / Python 3.13.14: 102 regression tests passed, including real PTY Chinese streaming/editing and locking. A fresh venv with only terminal dependencies successfully ran `loop ros --once /status` with isolated state; MuJoCo and NumPy were absent. Installed `loop --version` returns Loop ROS 0.1.0.

[CI](../.github/workflows/platform-smoke.yml) targets Ubuntu 22.04/24.04, windows-latest and macos-latest with Python 3.10/3.12. It can run when this directory is hosted as a repository root; configuration is not an executed result. Only portable terminal tests are selected, not hardware certification. No other OS was tested locally.

Before marking another OS verified: fresh-user install, launch outside the project, missing-key wizard/cancel, Unicode streaming with simultaneous editing, lock collision/release, session restart and owned-service shutdown. Validate simulation and hardware separately.

## Official constraints

[Python 3.10 Windows documentation](https://docs.python.org/3.10/using/windows.html) requires Windows 8.1+, excluding native Windows 7/8 for this Python 3.10+ application. A Python 3.8 backport would be a separate maintenance effort.

[Python 3.13 macOS documentation](https://docs.python.org/3.13/using/mac.html) describes universal2 Intel/Apple Silicon installers and macOS 10.13+ support. This interpreter boundary does not certify every application dependency on 10.13 or every later OS.

[MuJoCo Python documentation](https://mujoco.readthedocs.io/en/stable/python.html) requires mjpython for the macOS passive viewer. [Ubuntu lifecycle](https://ubuntu.com/about/release-cycle) is distinct from application launchability; old repositories and security support need separate checking.

See [installation](INSTALL.md) and [research archive](../../projects/reports/09_loop_ros_platform_compatibility.md).
