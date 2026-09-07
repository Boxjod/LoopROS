"""Verify the portable kernel and C++ ABI without flashing or opening devices."""
import ast
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    version = next(ast.literal_eval(node.value) for node in ast.parse((ROOT / '_version.py').read_text()).body
                   if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets))
    manifest = ROOT / 'rust/Cargo.toml'
    metadata = json.loads(subprocess.check_output(['cargo', 'metadata', '--no-deps', '--format-version', '1', '--manifest-path', str(manifest)]))
    if any(p['version'] != version for p in metadata['packages']):
        raise ValueError('Rust workspace version must mirror _version.py before validation/release')
    def cargo(*args):
        subprocess.run(['cargo', *args, '--manifest-path', str(manifest)], check=True, cwd=ROOT)
    cargo('fmt', '--all', '--check')
    cargo('test', '--workspace')
    subprocess.run(['cargo', 'clippy', '--manifest-path', str(manifest), '--workspace', '--all-targets', '--', '-D', 'warnings'], check=True)
    cargo('build', '-p', 'loopros-ffi', '--release')
    for target in ('riscv32imc-unknown-none-elf', 'thumbv6m-none-eabi'):
        cargo('build', '-p', 'loopros-ffi', '--release', '--target', target)
    with tempfile.TemporaryDirectory(prefix='loopros-abi-') as directory:
        binary = Path(directory) / 'abi'
        subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT / 'rust/ffi/include'), str(ROOT / 'rust/ffi/tests/abi.cpp'),
                        str(ROOT / 'rust/target/release/libloopros_ffi.a'), '-ldl', '-lpthread', '-lm', '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    cargo('run', '-p', 'loopros-core-host', '--release')


if __name__ == '__main__':
    main()
