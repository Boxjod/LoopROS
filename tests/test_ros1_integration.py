"""Opt-in ROS 1 loopback transport test. No robot or existing ROS master used."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import unittest
import xmlrpc.client

from loop_robot.core.nodes import NodeDefinition, NodeRuntime
from loop_robot.toolchain.ros_node import RosNode, config, resource, ENV_NAMES
from tests.test_ros_runtime import wait_for


@unittest.skipUnless(os.environ.get('LOOP_TEST_ROS1') == '1', 'opt-in: requires /opt/ros/noetic')
class Ros1IntegrationTests(unittest.TestCase):
    def test_loopback_master_joint_map_and_sigint_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            # Only retrieve ROS environment fields; never print the shell environment.
            command = "source /opt/ros/noetic/setup.bash\n/usr/bin/python3 -c 'import os,json; print(json.dumps({k:v for k,v in os.environ.items() if k.startswith(\"ROS_\") or k in (\"PATH\",\"PYTHONPATH\",\"LD_LIBRARY_PATH\",\"CMAKE_PREFIX_PATH\")}))'"
            extra = json.loads(subprocess.check_output(['bash','-c',command], text=True))
            extra = {k:v for k,v in extra.items() if k in ENV_NAMES}
            extra.update(ROS_MASTER_URI='http://127.0.0.1:%s' % port, ROS_IP='127.0.0.1', ROS_HOSTNAME='127.0.0.1')
            env = {**extra, 'HOME': directory, 'ROS_HOME': str(root/'ros')}
            children = []
            runtime = NodeRuntime({'ros':NodeDefinition(RosNode, config, resource, 5, False)},root/'nodes')
            with (root/'ros.log').open('w') as log:
                try:
                    master = subprocess.Popen(['/opt/ros/noetic/bin/roscore','-p',str(port)], env=env,
                        stdout=log, stderr=log, start_new_session=True)
                    children.append(master)
                    def master_ready():
                        try:
                            with xmlrpc.client.ServerProxy(extra['ROS_MASTER_URI']) as proxy:
                                return proxy.getPid('/loop_test')[0] == 1
                        except OSError: return False
                    wait_for(master_ready, 15)
                    script = root/'publisher.py'
                    script.write_text('''import rospy
from sensor_msgs.msg import JointState
from nav_msgs.msg import OccupancyGrid
rospy.init_node('loop_fixture_publisher')
joints=rospy.Publisher('/loop_test/joints',JointState,queue_size=1)
maps=rospy.Publisher('/loop_test/map',OccupancyGrid,queue_size=1,latch=True)
m=OccupancyGrid(); m.header.frame_id='map'; m.info.width=2; m.info.height=2
m.info.resolution=0.1; m.info.origin.orientation.w=1.; m.data=[0,100,-1,0]
maps.publish(m)
rate=rospy.Rate(10)
while not rospy.is_shutdown():
    j=JointState(); j.header.stamp=rospy.Time.now(); j.name=['fixture_joint']; j.position=[0.75]
    joints.publish(j); rate.sleep()
''')
                    publisher=subprocess.Popen(['/usr/bin/python3',str(script)],env=env,stdout=log,stderr=log,start_new_session=True)
                    children.append(publisher)
                    runtime.start('ros1','ros',{'version':1,'python':'/usr/bin/python3','env':extra,'topics':[
                        {'name':'joints','topic':'/loop_test/joints','kind':'joints'},
                        {'name':'map','topic':'/loop_test/map','kind':'map','max_age_s':30}]})
                    wait_for(lambda: runtime.status('ros1')['snapshot'].get('readiness') == 'observations_ready',15)
                    snap=runtime.status('ros1')['snapshot']
                    self.assertEqual(snap['observations']['joints']['summary']['positions'],[.75])
                    self.assertEqual(snap['observations']['map']['summary']['width'],2)
                    request=runtime.command('ros1','export_map',{'name':'map'})
                    wait_for(lambda: runtime.status('ros1')['results'])
                    result=runtime.status('ros1')['results'][-1]
                    self.assertEqual(result['command_id'],request['command_id'])
                    artifact=json.loads(Path(result['result']['artifact']).read_text())
                    self.assertEqual(artifact['data'],[0,100,-1,0])
                    host_pid=snap['host_pid']
                    self.assertFalse(runtime.stop('ros1')['process_alive'])
                    with self.assertRaises(ProcessLookupError): os.kill(host_pid,0)
                finally:
                    runtime.close()
                    for child in reversed(children):
                        if child.poll() is None: os.killpg(child.pid, signal.SIGINT)
                    for child in reversed(children): child.wait(timeout=15)


if __name__ == '__main__': unittest.main()
