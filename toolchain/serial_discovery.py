"""Cross-platform serial descriptors; enumeration never opens a port."""
import sys


def inventory():
    result = {'device_nodes': [], 'devices': [], 'usb_devices': [], 'input_devices': [],
              'opened': False, 'identified_or_safe': False, 'platform': sys.platform,
              'scope': 'serial_ports_and_their_usb_descriptors', 'supported': False}
    try:
        from serial.tools.list_ports import comports
        ports = sorted(comports(), key=lambda item: item.device)
    except ImportError:
        return {**result, 'reason': 'pyserial is required; install Loop ROS dependencies with this Python interpreter'}
    except (OSError, RuntimeError) as exc:
        return {**result, 'reason': 'Serial enumeration failed: ' + str(exc)}
    seen = set()
    for port in ports:
        if port.device in seen:
            continue
        seen.add(port.device)
        usb = None
        if port.vid is not None and port.pid is not None:
            usb = {'vid': format(port.vid, '04x'), 'pid': format(port.pid, '04x'),
                   'product': port.product, 'manufacturer': port.manufacturer,
                   'serial_number': port.serial_number, 'location': port.location}
        result['devices'].append({'node': port.device, 'name': port.description, 'kind': 'serial',
                                  'present': True, 'aliases': [], 'hwid': port.hwid,
                                  'usb': usb, 'motor_model': None})
    result['device_nodes'] = [item['node'] for item in result['devices']]
    result['supported'] = True
    return result
