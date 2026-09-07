"""Build and link the no_std Rust kernel; never flash a board."""
from pathlib import Path
import subprocess
from platformio.package.manager.tool import ToolPackageManager

Import("env")  # noqa: F821 -- PlatformIO/SCons supplies this object.
root = Path(env["PROJECT_DIR"]).resolve().parents[1]
target = "riscv32imc-unknown-none-elf"
subprocess.run(["cargo", "build", "--manifest-path", str(root / "rust/Cargo.toml"),
                "-p", "loopros-ffi", "--release", "--target", target], check=True)
env.Append(CPPPATH=[str(root / "rust/ffi/include")],
           LIBPATH=[str(root / "rust/target" / target / "release")],
           LIBS=["loopros_ffi"])

# Arduino 2.0.17 uses GCC 8 and its original SDK/libc. Its old linker cannot
# parse LLVM 21's RISC-V zmmul/zca attributes. Select only a modern ld through
# GCC's linker-time -B prefix, preserving the Arduino compiler, libc and ABI.
modern = ToolPackageManager(package_dir=str(root / "firmware/esp32/.pio/modern-tools")).install(
    "platformio/toolchain-riscv32-esp@14.2.0+20241119")
linker_bin = Path(modern.path) / "riscv32-esp-elf/bin"
if not (linker_bin / "ld").is_file():
    raise RuntimeError("Expected modern RISC-V linker is unavailable")
env.Append(LINKFLAGS=["-B" + str(linker_bin) + "/"])
