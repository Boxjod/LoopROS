import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from loop_robot.core.deployment import Deployment
from loop_robot.terminal.app import App
from loop_robot.terminal.carriers import bind, validate_bindings
from loop_robot.terminal.config import ROOT, load_config
from loop_robot.toolchain.node_workers import definitions


def manifest():
    return json.loads((ROOT / 'examples/deployments/two-hosts.json').read_text())


class DeploymentTests(unittest.TestCase):
    def test_identity_schema_assignments_and_profiles(self):
        data = manifest()
        with self.assertRaises(ValueError): Deployment(data)
        a, b = Deployment(data, 'bench-a'), Deployment(data, 'bench-b')
        self.assertNotEqual(a.scope(), b.scope())
        with self.assertRaises(ValueError): a.carrier('arm-remote', local=True)
        for bad in ('../host', 'A', 'a'*25, ''):
            changed = copy.deepcopy(data);changed['deployment_id'] = bad
            with self.assertRaises(ValueError): Deployment(changed, 'bench-a')
        changed = copy.deepcopy(data);changed['carriers'].append(changed['carriers'][0])
        with self.assertRaises(ValueError): Deployment(changed, 'bench-a')
        changed = copy.deepcopy(data);changed['carriers'][0]['config'] = {'unexpected': True}
        with self.assertRaises(ValueError): validate_bindings(Deployment(changed, 'bench-a'), definitions())

    def test_duplicate_device_resources_and_state_host_binding(self):
        data = manifest()
        for carrier in data['carriers'][:2]:
            carrier.update(adapter='serial_rx', config={'port':'/dev/ttyUSB99','baud':115200})
        with self.assertRaises(ValueError): validate_bindings(Deployment(data, 'bench-a'), definitions())
        with tempfile.TemporaryDirectory() as d:
            bind(d, Deployment(manifest(), 'bench-a'))
            bind(d, Deployment(manifest(), 'bench-a'))
            with self.assertRaises(ValueError): bind(d, Deployment(manifest(), 'bench-b'))

    def test_cli_outside_project_loads_manifest_without_starting_nodes(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, LOOP_HOME=d+'/home', LOOP_TASK_AUTOSTART='0')
            result = subprocess.run([str(ROOT/'loop'), 'node', '--deployment', str(ROOT/'examples/deployments/two-hosts.json'),
                                     '--host', 'bench-a', '--state-dir', d+'/state', '--once', '/carrier list'],
                                    cwd=d, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            listing = json.loads(result.stdout)
            self.assertEqual(listing['host_id'], 'bench-a')
            self.assertEqual(len(listing['carriers']), 3)
            self.assertEqual(listing['carriers'][2]['availability'], 'remote_unconnected')
            self.assertFalse(list((Path(d)/'state/nodes').glob('*.sqlite')))
            rebound = subprocess.run([str(ROOT/'loop'), '--state-dir', d+'/state', '--once', '/carrier list'],
                                    cwd=d, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(json.loads(rebound.stdout)['host_id'], 'bench-a')


class CarrierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'LOOP_HOME': str(self.root/'home'), 'LOOP_TASK_AUTOSTART':'0'})
        self.env.start()
        state = self.root/'state';state.mkdir()
        bind(state, Deployment(manifest(), 'bench-a'))
        self.app = App(load_config(), state)

    def tearDown(self):
        self.app.close();self.env.stop();self.temp.cleanup()

    def status(self, carrier):
        return self.app.tool('carrier_status', {'carrier_id': carrier})['node']

    def ready(self, carrier):
        self.app.tool('carrier_start', {'carrier_id':carrier})
        deadline = time.monotonic()+8
        while time.monotonic()<deadline:
            status = self.status(carrier)
            if status['state']=='running':return status['instance_id']
            if status['state']=='failed':self.fail(str(status))
            time.sleep(.02)
        self.fail('Carrier did not become ready')

    def args(self, carrier, instance, request='request1'):
        return {'carrier_id':carrier,'instance_id':instance,'request_id':request,'action':'move','arguments':{'target':[.2,-.1]}}

    def test_parallel_simulators_command_target_and_duplicate_suppression(self):
        left = self.ready('arm-left');right = self.ready('arm-right')
        self.assertNotEqual(left,right)
        args = self.args('arm-left',left)
        first = self.app.tool('carrier_command',args)
        duplicate = self.app.tool('carrier_command',args)
        self.assertEqual(first['command_id'],duplicate['command_id']);self.assertTrue(duplicate['duplicate'])
        with self.assertRaises(ValueError): self.app.tool('carrier_command',{**args,'arguments':{'target':[0,0]}})
        deadline=time.monotonic()+8
        while time.monotonic()<deadline and not self.status('arm-left')['results']:time.sleep(.02)
        results=self.status('arm-left')['results']
        self.assertEqual(len(results),1)
        self.assertEqual(results[0]['result']['review']['verdict'],'pass')
        self.assertEqual(self.status('arm-right')['results'],[])
        self.assertTrue(self.status('arm-right')['heartbeat_fresh'])
        with self.assertRaises(ValueError): self.app.tool('carrier_start',{'carrier_id':'arm-remote'})
        self.app.tool('carrier_stop',{'carrier_id':'arm-left','instance_id':left})
        new=self.ready('arm-left');self.assertNotEqual(left,new)
        with self.assertRaises(ValueError): self.app.tool('carrier_command',args)
        with self.assertRaises(ValueError): self.app.tool('carrier_stop',{'carrier_id':'arm-left','instance_id':left})
        self.assertEqual(self.status('arm-left')['instance_id'],new)
        self.assertEqual(self.status('arm-left')['results'],[])

    def test_reply_loss_does_not_repeat_an_enqueued_command(self):
        instance=self.ready('arm-left');args=self.args('arm-left',instance)
        original=self.app.tool
        calls=[]
        def reply_lost(name,arguments):
            result=original(name,arguments)
            if name=='node_command':
                calls.append(result);raise OSError('simulated lost acknowledgement')
            return result
        with patch.object(self.app,'tool',side_effect=reply_lost):
            with self.assertRaises(OSError): self.app.carriers.call('carrier_command',args)
            duplicate=self.app.carriers.call('carrier_command',args)
        self.assertEqual(len(calls),1)
        self.assertEqual(duplicate['state'],'inconclusive');self.assertTrue(duplicate['duplicate'])

    def test_permission_layers_and_unbound_name_cannot_be_bypassed(self):
        self.app.permissions.set_rule('node_start','deny')
        with self.assertRaises(PermissionError):self.app.tool('carrier_start',{'carrier_id':'arm-left'})
        self.app.permissions.set_rule('node_start','allow')
        instance=self.ready('arm-left')
        self.app.permissions.set_rule('carrier_command','deny')
        with self.assertRaises(PermissionError):self.app.tool('carrier_command',self.args('arm-left',instance))
        self.app.permissions.set_rule('carrier_command','allow')
        self.app.permissions.set_mode('plan')
        with self.assertRaises(PermissionError):self.app.tool('carrier_command',self.args('arm-left',instance))
        self.app.permissions.set_mode('sim')
        self.app.tool('node_start',{'kind':'sim_arm','name':'carrier-arm-right'})
        with self.assertRaises(ValueError):self.app.tool('carrier_status',{'carrier_id':'arm-right'})
        with self.assertRaises(ValueError):self.app.scheduled_tool('carrier_start',{'carrier_id':'arm-left'})

    def test_declared_unknown_adapter_does_not_create_capabilities(self):
        data=manifest();data['carriers'][0]['adapter']='future_base'
        from loop_robot.terminal.carriers import Carriers
        self.app.carriers=Carriers(self.app,Deployment(data,'bench-a'))
        listing=self.app.tool('carrier_list',{})
        self.assertEqual(listing['carriers'][0]['capabilities'],{})
        self.assertFalse(listing['carriers'][0]['supported_here'])
        with self.assertRaises(ValueError):self.app.tool('carrier_start',{'carrier_id':'arm-left'})

    def test_two_host_instances_keep_nodes_and_experience_scopes_separate(self):
        state = self.root/'host-b';state.mkdir()
        bind(state,Deployment(manifest(),'bench-b'))
        other = App(load_config(),state)
        try:
            left = self.ready('arm-left')
            remote = other.tool('carrier_start',{'carrier_id':'arm-remote'})['node']['instance_id']
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                remote_state=other.tool('carrier_status',{'carrier_id':'arm-remote'})['node']
                if remote_state['state']=='running':break
                time.sleep(.02)
            self.assertEqual(remote_state['state'],'running')
            self.assertNotEqual(left,remote)
            self.assertNotEqual(self.app.learning.scope(),other.learning.scope())
            self.assertNotEqual(self.app.nodes.directory,other.nodes.directory)
            with self.assertRaises(ValueError):other.tool('carrier_status',{'carrier_id':'arm-left'})
            self.app.close()
            self.assertEqual(other.tool('carrier_status',{'carrier_id':'arm-remote'})['node']['state'],'running')
        finally:other.close()
