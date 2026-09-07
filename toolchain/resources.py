"""Single-threaded cooperative RAM/VRAM leases; no hidden CUDA dependency."""
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ModelSpec:
    ram_bytes: int
    vram_bytes: int
    load: Callable
    unload: Callable


class ModelPool:
    def __init__(self, ram_bytes, vram_bytes, resources=None, gpu_index=0):
        self.budget = self._size(ram_bytes, vram_bytes)
        self.specs, self.loaded, self.active = {}, {}, set()
        self.resources, self.gpu_index, self.leases = resources, gpu_index, {}

    @staticmethod
    def _size(ram, vram):
        if any(not isinstance(x, int) or x < 0 for x in (ram, vram)):
            raise ValueError("nonnegative byte budgets required")
        return (ram, vram)

    def register(self, name, spec):
        self._size(spec.ram_bytes, spec.vram_bytes)
        if name in self.specs:
            raise ValueError("duplicate model name")
        self.specs[name] = spec

    def usage(self):
        return tuple(sum((self.specs[n].ram_bytes, self.specs[n].vram_bytes)[i]
                         for n in self.loaded) for i in (0, 1))

    def evict(self, name):
        if name in self.active:
            raise RuntimeError("cannot unload an active model")
        value = self.loaded[name]
        self.specs[name].unload(value)
        del self.loaded[name]
        if name in self.leases:
            self.resources.release(self.leases.pop(name))

    @contextmanager
    def lease(self, name):
        spec = self.specs[name]
        if name in self.active:
            raise RuntimeError("nested lease of same model unsupported")
        if name not in self.loaded:
            needed = (spec.ram_bytes, spec.vram_bytes)
            if any(n > b for n, b in zip(needed, self.budget)):
                raise MemoryError("model exceeds total budget")
            def fits():
                return all(u + n <= b for u, n, b in zip(self.usage(), needed, self.budget))
            idle = [n for n in self.loaded if n not in self.active]
            # Fail without evicting anything if active leases alone prevent loading.
            pinned = tuple(sum((self.specs[n].ram_bytes, self.specs[n].vram_bytes)[i]
                               for n in self.active) for i in (0, 1))
            if any(u + n > b for u, n, b in zip(pinned, needed, self.budget)):
                raise MemoryError("active models reserve the required budget")
            for old in idle:
                if fits():
                    break
                self.evict(old)
            token = None
            if self.resources:
                from core.resources import ResourceBusy
                token = self.resources.inspect(acquire=True, workload='model', request=dict(
                    ram_mb=spec.ram_bytes / 1048576, cpu_cores=0,
                    vram_mb=spec.vram_bytes / 1048576, gpu_index=self.gpu_index))
                if token is None:
                    raise ResourceBusy('Waiting for resources: ' + self.resources.last['reason'])
            try:
                self.loaded[name] = spec.load()
            except BaseException:
                if token: self.resources.release(token)
                raise
            if token: self.leases[name] = token
        self.active.add(name)
        try:
            yield self.loaded[name]
        finally:
            self.active.remove(name)
            # dict order is our idle LRU order.
            self.loaded[name] = self.loaded.pop(name)

    def close(self):
        if self.active:
            raise RuntimeError("active leases remain")
        for name in list(self.loaded):
            self.evict(name)
