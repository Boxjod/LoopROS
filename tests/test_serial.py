import json
import os
from pathlib import Path
import pty
import tempfile
import unittest
from unittest.mock import patch

from terminal.app import App
from terminal.config import load_config
from terminal.control import list_devices
from toolchain.serial_port import SerialPort


class SerialTests(unittest.TestCase):
    def test_inventory_resolves_alias_and_groups_usb_video_interfaces(self):
        with tempfile.TemporaryDirectory() as d:
            dev, sys = Path(d)/'dev', Path(d)/'sys'
            (dev/'serial/by-id').mkdir(parents=True)
            (dev/'ttyACM0').touch()
            (dev/'serial/by-id/usb-bridge').symlink_to('../../ttyACM0')
            usb = sys/'devices/usb1'
            usb.mkdir(parents=True)
            (usb/'idVendor').write_text('1a86')
            (usb/'idProduct').write_text('55d3')
            interface = usb/'1:1.0'
            interface.mkdir()
            driver = sys/'bus/usb/drivers/cdc_acm'
            driver.mkdir(parents=True)
            (interface/'driver').symlink_to(driver)
            for kind, name in [('tty', 'ttyACM0'), ('video4linux', 'video0'), ('video4linux', 'video1')]:
                (dev/name).touch(exist_ok=True)
                base = sys/'class'/kind/name
                base.mkdir(parents=True)
                (base/'device').symlink_to(interface)
            data = list_devices(dev, sys)
            self.assertEqual(len(data['devices']), 3)
            serial = next(x for x in data['devices'] if x['kind'] == 'serial')
            self.assertEqual(serial['kernel_driver'], 'cdc_acm')
            self.assertEqual(len(serial['aliases']), 1)
            self.assertIsNone(serial['motor_model'])
            self.assertEqual(len({x['usb']['device_path'] for x in data['devices']}), 1)

    def test_real_pty_receive_bounds_and_disconnect(self):
        master, slave = pty.openpty()
        name = os.ttyname(slave)
        port = SerialPort()
        real_open = os.open
        try:
            with patch('toolchain.serial_port.Path.resolve', return_value=Path('/dev/ttyACM999')), patch('toolchain.serial_port.os.open', side_effect=lambda path, flags: real_open(name, flags)):
                port.open('/dev/ttyACM999', 115200)
            port.path = name
            self.assertTrue(port.status()['connected'])
            os.write(master, b'\x01motor?\xff')
            result = port.read(4, 100)
            self.assertEqual(result['hex'], b'\x01mot'.hex())
            self.assertFalse(result['motor_identified'])
            with self.assertRaises(ValueError):
                port.read(4097)
            os.close(master)
            master = None
            self.assertFalse(port.status()['connected'])
            with self.assertRaises(RuntimeError):
                port.read()
            self.assertFalse(port.close()['opened'])
        finally:
            port.close()
            os.close(slave)
            if master is not None:
                os.close(master)

    def test_tools_permissions_and_no_speculative_probe(self):
        with tempfile.TemporaryDirectory() as d:
            app = App(load_config(), d)
            try:
                with patch.object(app.serial, 'open') as opened, patch.object(app.client, 'complete',return_value={'content':'仅凭串口不能确定电机型号，请提供协议。'}) as llm:
                    answer = app.agent.reply('这个串口是什么电机')
                    self.assertIn('不能确定电机型号', answer)
                    opened.assert_not_called()
                    llm.assert_called_once()
                with self.assertRaises(ValueError):
                    app.tool('open_serial', {'port': '/dev/ttyACM0'})
                app.permissions.set_mode('plan')
                with self.assertRaises(PermissionError):
                    app.tool('open_serial', {'port': '/dev/ttyACM0', 'baud': 115200})
                self.assertFalse(app.tool('serial_status', {})['opened'])
                app.tool('close_serial', {})
                with self.assertRaises(ValueError):
                    app.scheduled_tool('open_serial', {'port': '/dev/ttyACM0', 'baud': 115200})
            finally:
                app.close()
