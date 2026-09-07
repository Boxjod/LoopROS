# Loop ROS Rust core — development port

This workspace prepares the execution kernel for MCU use. It does not replace
the Python CLI or publish a second product release. Workspace metadata mirrors
the authoritative [`_version.py`](../_version.py); packages have `publish = false`.

- `core`: dependency-free `no_std`, allocation-free state, portable task/session
  identities, locally supplied permissions, tool/model budgets, cancellation,
  receipt matching, evidence acceptance and simulated robot review.
- `ffi`: an explicitly initialized 128-byte, 8-byte aligned C context. Arduino
  C++ calls the same Rust kernel through [the header](ffi/include/loopros_core.h).
- `host`: offline fixture proving continuation after an unverified prose answer;
  it is not an interactive CLI or an actual model request.

The ESP32-C3 adapter lives in [firmware/esp32](../firmware/esp32/README.md).
It runs the agent loop on the board and calls a remote model API directly.
Microcontrollers are not restricted to a programming language: Arduino C++ owns
the SDK integration while Rust owns execution state.

## Build and verify

Verified compiler: Rust 1.91.1 on Linux x86_64. Install the two target libraries:

```sh
rustup target add riscv32imc-unknown-none-elf thumbv6m-none-eabi
python3 scripts/validate_rust_core.py
```

Run these commands from the repository root. Validation checks package versions,
formatting, tests, Clippy, host/RISC-V/Cortex-M0+ static libraries, a real C++/Rust
link and execution, and the offline host fixture. It never opens a device.

Bare-metal outputs are static libraries, not bootable firmware:

```sh
cargo build --manifest-path rust/Cargo.toml -p loopros-ffi --release --target riscv32imc-unknown-none-elf
cargo build --manifest-path rust/Cargo.toml -p loopros-ffi --release --target thumbv6m-none-eabi
```

## Contracts and boundaries

The application registers session/task IDs, allowed tool numbers and an optional
acceptance check. `Check::Conversation` permits a final answer but does **not**
mark execution verified. `Check::Tool(n)` needs a current matching driver receipt
and a passing local predicate; prose returns `Unverified`, allowing another model
request within the configured budget. Model/tool/clock limits stop execution with
a concrete reason. IDs and permissions must never be sourced from model output.

A resource admission result and recorded intent are required before dispatch.
The `Resources` and `Evidence` ports leave the authority and persistence medium
to the runtime. A future Python-host adapter must delegate to `App.resources` and
the existing stores, not introduce another host budget/lease ledger. The ESP
adapter has a single active task, samples its own heap, and keeps receipts in
bounded RAM history. No pending action is restored or replayed at boot.

`robotics::run` ports target checks, observation/body/calibration identities,
deadlines, before/after evidence, stopping, and numerical review. It retains the
Python reference's simulated-only boundary. It is not a motor driver or a
hard real-time control loop.

SQLite task persistence, full session memory, Skills, Node subprocess supervision,
cross-terminal leases, provider selection and the complete Python tool catalog
remain host services. They are not falsely represented as MCU-compatible Rust
implementations. This first port supplies the independently usable kernel and
one board SDK integration; see [port mapping and validation](../docs/RUST_CORE.md).

## Reference

Studied local ZeroClaw commit `4129a18ac7f8a52ab2b13095310a41090a81dbf8`:
its ESP firmware describes a host-mediated serial peripheral and a future
edge-native agent; its Arduino sketch is C++. Loop's code is independently
implemented. No third-party source has been modified or copied into this core.
