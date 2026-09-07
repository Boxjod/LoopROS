"""Read local Linux network metadata; importing this module performs no I/O."""
import json
import os
import subprocess

def run(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=8)
        return {'stdout': p.stdout, 'stderr': p.stderr, 'returncode': p.returncode}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'error': str(e)}


def discover():
    return {
        'addresses': run(['ip', '-j', '-4', 'addr', 'show']),
        'routes': run(['ip', '-j', '-4', 'route', 'show']),
        'neighbors': run(['ip', '-j', 'neigh', 'show']),
        'ros_master_uri': os.environ.get('ROS_MASTER_URI'),
        'ros_distro': os.environ.get('ROS_DISTRO'),
    }


if __name__ == '__main__':
    print(json.dumps(discover(), ensure_ascii=False, indent=2))
