# ESP32-C3 edge agent (Rust + Arduino C++)

The board runs the execution loop itself. Arduino C++ provides Wi-Fi, verified
TLS, Chat Completions JSON and two read-only board tools (`device_uptime`,
`free_heap`); the Rust `no_std` core checks permissions, budgets, task identity,
dispatch and receipts. The language model runs behind your configured remote
API. No separate Python/ZeroClaw host agent is required during operation.

First target: **ESP32-C3-DevKitM-1** with PlatformIO espressif32 6.12.0,
Arduino ESP32 2.0.17, ArduinoJson 7.4.2 and Rust 1.91.1.
This is a development port, not an official binary release. Board flashing,
Wi-Fi/TLS and real provider operation require a separate device acceptance run.

## Build on a Linux development computer

From the Loop ROS source root with Rust installed:

```sh
python3 -m venv .venv-embedded
. .venv-embedded/bin/activate
python -m pip install platformio==6.1.18
rustup target add riscv32imc-unknown-none-elf
pio run -d firmware/esp32 -e esp32c3
```

The build hook compiles `rust/ffi` and links its static library into the C++
firmware. It installs a modern RISC-V linker in the ignored project-local
`.pio/modern-tools` directory because Arduino's old ld cannot read LLVM's newer
ISA attributes; the original GCC8 compiler, SDK and libc remain in use.
Default configuration is blank: the image prints a configuration
message and does not connect to a model. It does not activate GPIO or motors.

For operation, locally copy `include/config.example.h` to `include/secrets.h`
and provide the Wi-Fi credentials, full **HTTPS Chat Completions URL**, its bound
API key, model ID (`LOOP_MODEL_ID`), and PEM root CA. That header and all build
outputs are ignored. The credential is compiled into the local firmware; never
publish a configured image or its build directory. The Python CLI's `~/.loop`
configuration is not read or altered by this adapter.

After confirming the actual board and serial port, the operator can run:

```sh
pio run -d firmware/esp32 -e esp32c3 -t upload --upload-port PORT
pio device monitor -b 115200 --port PORT
```

No flash command was executed during source preparation. Do not use a C3 image
on ESP32/S2/S3 (Xtensa) or on another RISC-V board with a different SDK target.

## Interaction and verification

After Wi-Fi and the TLS clock are ready, enter a message on the serial monitor.
An explicit `/task uptime Read and verify the board uptime` registers a task
whose check requires a real uptime tool receipt. A plain conversation registers
no execution check and reports only answer completion. Session and task IDs are
locally generated and distinct. This minimal serial composer is not the full
Python CLI interface; new text typed during an active request is discarded, and
Ctrl-C is observed at request/tool boundaries. Network operations have timeouts.

- Non-streaming Chat Completions only; Responses and streaming need an adapter.
- Per turn: 768 input bytes, 16 KiB request/response JSON, at most 16 tool calls,
  12 model requests, and 120 seconds. JSON allocation/heap admission is checked.
- Tool batches are validated before dispatch; only the two registered names and
  empty JSON arguments are accepted. Duplicate remote IDs are rejected.
- HTTP redirects are disabled to keep the key at its configured endpoint;
  no insecure TLS switch and no server error-body/credential logging.
- Evidence/history is RAM-only for the active turn. Reboot starts fresh and
  does not restore pending commands. Sensor or motor actions are not enabled.
- GPIO, camera and robot drivers are future explicit integrations. They must
  preserve ownership, hardware constraints and receipt-based verification.

## Other Arduino boards

Arduino C++ can call the C ABI when its CPU/toolchain can link the Rust static
library. The Cortex-M0+ `thumbv6m-none-eabi` library is cross-compiled for future
RP2040/Pico integration, but no ready Pico networking firmware is supplied.
Classic UNO R3/Mega AVR boards do not have a ready Rust port here; their very
different architecture and memory must not be hidden behind a generic command.
The next concrete board should be selected before adding its SDK integration.
