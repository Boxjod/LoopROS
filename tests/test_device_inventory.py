"""Device enumeration remains available through explicitly selected tools."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from terminal.app import App
from terminal.config import load_config
from terminal.control import list_devices
from model_fixture import call


class DeviceInventoryTests(unittest.TestCase):
    def test_inventory_reads_sysfs_without_opening_devices(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);dev=root/'dev';sys=root/'sys';dev.mkdir()
            usb=sys/'bus/usb/devices/1-1';usb.mkdir(parents=True)
            for name,value in {'idVendor':'1234','idProduct':'abcd','product':'Test Keyboard'}.items():
                (usb/name).write_text(value)
            data=list_devices(str(dev),str(sys))
            self.assertEqual(data['usb_devices'][0]['product'],'Test Keyboard')
            self.assertFalse(data['opened'])

    def test_model_device_query_records_receipts_and_preserves_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            inventory={'supported':True,'devices':[{'node':'COM7','kind':'serial'}],'opened':False,'usb_devices':[],'input_devices':[]}
            try:
                for denied in (False,True):
                    app.permissions.set_rule('devices','deny' if denied else 'allow')
                    with patch('terminal.app.list_devices',return_value=inventory) as scan, patch.object(app.serial,'open') as opened, patch.object(app.client,'complete',side_effect=[call('load_toolset',name='robotics'),call('devices'),{'content':'Inventory checked.'}]) as model:
                        app.agent.reply('读取我的机械臂')
                        self.assertEqual(scan.call_count,0 if denied else 1)
                        opened.assert_not_called()
                        receipts=[json.loads(m['content']) for m in model.call_args.args[0] if m['role']=='tool']
                        self.assertEqual(receipts[-1].get('error'),'PermissionError' if denied else None)
                        if not denied:
                            self.assertEqual(receipts[-1],inventory)
                            self.assertIn('device_inventory',app.agent.turn_summaries[-1]['tool_evidence'][-1])
            finally:app.close()

    def test_device_coding_request_never_scans_automatically(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            try:
                with patch('terminal.app.list_devices') as scan, patch.object(app.client,'complete',return_value={'content':'Code review'}):
                    self.assertEqual(app.agent.reply('write code to list connected devices'),'Code review')
                    scan.assert_not_called()
            finally:app.close()
