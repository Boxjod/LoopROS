"""Portable deployment identities and carrier assignments. Standard library only."""
import hashlib
import json
from pathlib import Path
import re


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,23}', value):
        raise ValueError('IDs must be 1..24 lowercase letters, digits, _ or -, starting with a letter')
    return value


class Deployment:
    def __init__(self, manifest, host_id=None):
        if not isinstance(manifest, dict) or set(manifest) != {'version', 'deployment_id', 'hosts', 'carriers'} or type(manifest['version']) is not int or manifest['version'] != 1:
            raise ValueError('Deployment requires version=1, deployment_id, hosts and carriers')
        self.deployment_id = identity(manifest['deployment_id'])
        hosts = manifest['hosts']
        if not isinstance(hosts, list) or not 1 <= len(hosts) <= 64:
            raise ValueError('Deployment requires 1..64 host IDs')
        hosts = [identity(h) for h in hosts]
        if len(set(hosts)) != len(hosts):
            raise ValueError('Duplicate host ID')
        self.host_id = identity(host_id or (hosts[0] if len(hosts) == 1 else ''))
        if self.host_id not in hosts:
            raise ValueError('Local host is not in this deployment')
        carriers = manifest['carriers']
        if not isinstance(carriers, list) or not 1 <= len(carriers) <= 256:
            raise ValueError('Deployment requires 1..256 carriers')
        self.carriers = {}
        for item in carriers:
            if not isinstance(item, dict) or set(item) != {'id', 'host', 'label', 'adapter', 'config'}:
                raise ValueError('Carrier fields: id, host, label, adapter, config')
            name = identity(item['id'])
            if name in self.carriers or item['host'] not in hosts:
                raise ValueError('Duplicate carrier ID or unknown host')
            identity(item['adapter'])
            if not isinstance(item['label'], str) or not 1 <= len(item['label']) <= 100 or not all(c.isprintable() for c in item['label']):
                raise ValueError('Carrier label must be 1..100 printable characters')
            if not isinstance(item['config'], dict):
                raise ValueError('Carrier config must be an object')
            encoded = json.dumps(item, sort_keys=True, allow_nan=False)
            if len(encoded) > 4096:
                raise ValueError('Carrier configuration exceeds 4096 characters')
            self.carriers[name] = json.loads(encoded)
        self.manifest = json.loads(json.dumps(manifest, allow_nan=False))
        local = sorted((c for c in self.carriers.values() if c['host'] == self.host_id), key=lambda c: c['id'])
        self.fingerprint = hashlib.sha256(json.dumps(local, sort_keys=True).encode()).hexdigest()

    @classmethod
    def load(cls, path, host_id=None):
        path = Path(path)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('Deployment manifest exceeds 1 MiB')
        return cls(json.loads(path.read_text(encoding='utf-8')), host_id)

    def carrier(self, name, local=False):
        if not isinstance(name, str) or name not in self.carriers:
            raise ValueError('Unknown carrier ID')
        carrier = self.carriers[name]
        if local and carrier['host'] != self.host_id:
            raise ValueError('Carrier belongs to host ' + carrier['host'] + '; this host has no remote execution transport')
        return json.loads(json.dumps(carrier))

    def scope(self):
        return [self.deployment_id, self.host_id, self.fingerprint]
