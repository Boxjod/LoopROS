"""Release metadata shared by the client, builder and standalone publisher."""
import re


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise ValueError("Expected stable major.minor.patch version")
    return tuple(map(int, value.split(".")))


def validate_manifest(data, target_version=None):
    if not isinstance(data, dict):
        raise ValueError("Expected release metadata object")
    version(data.get('version'))
    if target_version and data['version'] != target_version:
        raise ValueError("Requested version does not match release metadata")
    if data.get('state_schema', 1) != 1:
        raise ValueError("This release requires an unsupported state migration")
    expected = 'loop_ros-' + data['version'] + '-py3-none-any.whl'
    if data.get('wheel') != expected or not isinstance(data.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', data['sha256']):
        raise ValueError("Invalid release artifact metadata")
    return data
