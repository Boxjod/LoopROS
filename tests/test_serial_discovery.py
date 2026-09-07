import sys
import types
import unittest
from unittest.mock import Mock, patch
from loop_robot.terminal.control import list_devices
from loop_robot.toolchain.serial_port import SerialPort


class PortableSerialTests(unittest.TestCase):
    def test_windows_and_mac_discovery_receive_disconnect_and_bounds(self):
        for platform, name in [('win32', 'COM7'), ('darwin', '/dev/cu.usbserial-7')]:
            with self.subTest(platform=platform):
                descriptor = types.SimpleNamespace(device=name, description='USB bridge', vid=0x1234, pid=0x5678,
                    product='Bridge', manufacturer='Vendor', serial_number='test', location='1', hwid='USB')
                ports = Mock(return_value=[descriptor, descriptor])
                handle = Mock(is_open=True)
                handle.read.return_value = b'\x01\xff'
                serial = types.ModuleType('serial')
                serial.Serial = Mock(return_value=handle)
                port_module = types.ModuleType('serial.tools.list_ports')
                port_module.comports = ports
                with patch.dict(sys.modules, {'serial': serial, 'serial.tools': types.ModuleType('serial.tools'), 'serial.tools.list_ports': port_module}), patch('sys.platform', platform):
                    data = list_devices()
                    self.assertEqual(data['device_nodes'], [name])
                    self.assertEqual(data['devices'][0]['usb']['vid'], '1234')
                    serial.Serial.assert_not_called()
                    port = SerialPort()
                    with self.assertRaises(ValueError): port.open('socket://host:1234', 115200)
                    with self.assertRaises(ValueError): port.open(name, True)
                    self.assertTrue(port.open(name, 115200)['connected'])
                    self.assertEqual(port.read(2, 10)['hex'], '01ff')
                    handle.write.assert_not_called()
                    self.assertFalse(handle.dtr)
                    self.assertFalse(handle.rts)
                    with self.assertRaises(ValueError): port.read(4097)
                    ports.return_value = []
                    self.assertFalse(port.status()['connected'])
                    with self.assertRaises(RuntimeError): port.read()
                    self.assertFalse(port.close()['opened'])
                    handle.close.assert_called_once()

    def test_missing_adapter_does_not_report_empty_success(self):
        with patch('sys.platform', 'win32'), patch.dict(sys.modules, {'serial.tools.list_ports': None}):
            self.assertFalse(list_devices()['supported'])
