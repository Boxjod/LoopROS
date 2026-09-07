import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from prompt_toolkit.document import Document
from terminal.app import App
from terminal.config import load_config, ROOT
from terminal.references import extract
from terminal.protocols import encode
from model_fixture import call


class CodingAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'LOOP_HOME':str(self.root/'home'),'LOOP_TASK_AUTOSTART':'0'});self.env.start()
        self.app=App(load_config(),self.root/'state');self.app.workspace_root=self.root/'workspace';self.app.workspace_root.mkdir()
        self.events=[];self.app.agent.on_event=lambda *e:self.events.append(e)
    def tearDown(self):
        self.app.close();self.env.stop();self.temp.cleanup()
    def test_file_create_read_edit_conflict_backup_search_and_bounds(self):
        app=self.app
        created=app.tool('write_file',{'path':'src/demo.py','content':'x = 1\n'})
        self.assertEqual(app.tool('read_file',{'path':'src/demo.py'})['sha256'],created['sha256'])
        edited=app.tool('edit_file',{'path':'src/demo.py','old_text':'x = 1','new_text':'x = 2'})
        self.assertEqual(Path(edited['backup']).read_text(),'x = 1\n')
        self.assertIn('+x = 2',edited['diff'])
        with self.assertRaises(ValueError):app.tool('write_file',{'path':'src/demo.py','content':'oops','expected_sha256':created['sha256']})
        with self.assertRaises(PermissionError):app.tool('write_file',{'path':str(self.root/'outside.txt'),'content':'no'})
        outside=self.root/'outside';outside.mkdir();(app.workspace_root/'link').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(PermissionError):app.tool('write_file',{'path':'link/x','content':'no'})
        self.assertEqual(app.tool('search_files',{'query':'x = 2'})['matches'][0]['line'],1)
        app.permissions.set_mode('plan')
        with self.assertRaises(PermissionError):app.tool('edit_file',{'path':'src/demo.py','old_text':'2','new_text':'3'})
    def test_plain_chat_has_no_robot_state_or_robot_tool_schemas(self):
        seen=[]
        def complete(messages,tools):
            seen.append((messages,tools));return {'content':'你好'}
        with patch.object(self.app.client,'complete',side_effect=complete),patch.object(self.app.viewer,'status',side_effect=AssertionError('No robot snapshot')):
            self.assertEqual(self.app.agent.reply('你好'),'你好')
        system='\n'.join(m['content'] for m in seen[0][0] if m['role']=='system')
        self.assertNotIn('latest_generated_scene',system)
        self.assertNotIn('你是MuJoCo操作Agent',system)
        names={t['function']['name'] for t in seen[0][1]}
        self.assertIn('write_file',names);self.assertIn('read_image',names)
        self.assertNotIn('simulator_control',names)
    def test_specialists_load_only_on_model_request_and_reset_each_turn(self):
        observed=[]
        responses=iter([call('load_toolset',name='robotics'),call('simulator_status'),{'content':'State checked.'}])
        def complete(messages,tools):
            observed.append(({t['function']['name'] for t in tools}, messages[0]['content']))
            return next(responses)
        with patch.object(self.app.client,'complete',side_effect=complete), patch.object(self.app.viewer,'status',return_value={'window_open':False}) as status:
            self.assertEqual(self.app.agent.reply('查看仿真状态'),'State checked.')
            status.assert_called_once()
        self.assertNotIn('simulator_status',observed[0][0])
        self.assertIn('simulator_status',observed[1][0])
        self.assertNotIn('task_submit',observed[1][0])
        self.assertNotIn('spawn_agent',observed[1][0])
        self.assertEqual(observed[0][1], observed[1][1])
        self.app.prepare_input('继续',[])
        context=self.app.agent.context_provider('继续')
        self.assertNotIn('simulator_status',{t['function']['name'] for t in context['tools']})
        self.assertIn('workspace_root',context['live_context']())
    def test_exact_image_request_reaches_current_model_with_pixels(self):
        image=ROOT/'assets/logo.png';seen=[]
        def complete(messages,tools):
            seen.append(messages);return {'content':'Logo analysis fixture'}
        with patch.object(self.app.client,'complete',side_effect=complete):
            self.app.agent.reply("帮我分析一下这个图'"+str(image)+"'")
        content=next(m['content'] for m in seen[0] if m['role']=='user')
        self.assertTrue(any(p['type']=='image_url' and p['image_url']['url'].startswith('data:image/png;base64,') for p in content))
        self.assertTrue(any(k=='tool' and v.startswith('read_image(') for k,v in self.events))
        self.assertFalse(any('base64,' in v for k,v in self.events if k=='result'))
        _,body=encode({**self.app.client.config,'protocol':'openai-responses'},seen[0],[])
        self.assertTrue(any(p.get('type')=='input_image' for m in body['input'] if isinstance(m.get('content'),list) for p in m['content']))
    def test_multiple_paths_spaces_missing_and_url_refs(self):
        path=self.app.workspace_root/'a file.txt';path.write_text('local evidence')
        image=ROOT/'assets/logo.png'
        text=f'分析 "{path}" 和 "{image}" 并参考 https://example.com/info'
        refs=extract(text,self.app.workspace_root)
        self.assertEqual(len(refs),3)
        with patch('terminal.references.read_url',return_value={'url':'https://example.com/info','text':'web evidence'}):
            parts=self.app.prepare_input(text,[])
        self.assertIn('local evidence',json.dumps(parts));self.assertIn('web evidence',json.dumps(parts))
        self.assertTrue(any(p['type']=='image_url' for p in parts))
        bad=self.app.prepare_input('读取 "./missing.png"',[])
        self.assertIn('error',bad[0]['text'])
    def test_multi_tool_images_and_edits_in_one_turn(self):
        round_no=0
        def complete(messages,tools):
            nonlocal round_no
            round_no+=1
            if round_no==1:
                return {'tool_calls':[{'id':'a','function':{'name':'write_file','arguments':json.dumps({'path':'demo.txt','content':'old'})}}, {'id':'b','function':{'name':'read_image','arguments':json.dumps({'path':str(ROOT/'assets/logo.png')})}}]}
            if round_no==2:
                self.assertEqual([m['role'] for m in messages[-3:]],['tool','tool','user'])
                self.assertTrue(any(p['type']=='image_url' for p in messages[-1]['content']))
                return {'tool_calls':[{'id':'c','function':{'name':'edit_file','arguments':json.dumps({'path':'demo.txt','old_text':'old','new_text':'new'})}}]}
            return {'content':'Done'}
        with patch.object(self.app.client,'complete',side_effect=complete):
            self.assertEqual(self.app.agent.reply('创建文件并根据工具结果修改内容'),'Done')
        self.assertEqual((self.app.workspace_root/'demo.txt').read_text(),'new')
        self.assertEqual(round_no,3)
        self.assertFalse(any('base64,' in v for k,v in self.events if k=='result'))
    def test_skill_and_harness_reload_next_call_without_restart(self):
        app=self.app;app.permissions.set_rule('skill_write','allow');app.permissions.set_rule('harness_write','allow')
        original=app.agent.context_provider('hello')['system_prompt']
        result=app.tool('skill_write',{'name':'code-notes','description':'Write coding notes: review and verify','content':'# Coding notes\nUse for coding documentation.\nRead evidence, edit, validate links, then stop.'})
        self.assertNotIn('code-notes',original)
        self.assertIn('code-notes',app.agent.context_provider('hello')['system_prompt'])
        old=app.tool('skill_read',{'name':'code-notes'})
        app.tool('skill_write',{'name':'code-notes','description':'Updated coding notes','content':'# Updated notes\nRead then write and verify.','expected_sha256':old['sha256']})
        self.assertIn('Updated coding notes',app.agent.context_provider('hello')['system_prompt'])
        app.tool('harness_write',{'path':'harness/style.md','content':'Use concise paragraphs. Marker: LOCAL_STYLE_17.'})
        self.assertIn('LOCAL_STYLE_17',app.agent.context_provider('hello')['system_prompt'])
        with self.assertRaises(ValueError):app.tool('harness_write',{'path':'../credentials.json','content':'no'})
        with self.assertRaises(PermissionError):app.tool('write_file',{'path':str(self.root/'home/credentials.json'),'content':'no'})
        self.assertTrue(Path(result['path']).exists())

    def test_url_image_and_no_coding_handoff(self):
        from terminal.references import read_url
        with patch('terminal.web.request',return_value={'body_bytes':(ROOT/'assets/logo.png').read_bytes(),'content_type':'image/png','url':'https://example.com/logo.png'}):
            result=read_url('https://example.com/logo.png')
        self.assertTrue(result['image_loaded'])
        self.assertTrue(result['_media'][0]['image_url']['url'].startswith('data:image/png;base64,'))
        self.app.prepare_input('编写文件',[])
        with patch('terminal.task_service.start',side_effect=AssertionError('No background task')):
            self.assertIsNone(self.app.agent.on_turn_finished)

    def test_harness_refresh_inside_tool_loop(self):
        self.app.permissions.set_rule('harness_write','allow')
        count=0
        def complete(messages,tools):
            nonlocal count
            count+=1
            if count==1:
                return {'tool_calls':[{'id':'h','function':{'name':'harness_write','arguments':json.dumps({'path':'harness/live.md','content':'Marker LIVE_RELOAD_42'})}}]}
            self.assertIn('LIVE_RELOAD_42',messages[0]['content'])
            return {'content':'Updated'}
        with patch.object(self.app.client,'complete',side_effect=complete):
            self.assertEqual(self.app.agent.reply('更新我的对话指令'),'Updated')

    def test_vision_routing_same_endpoint_and_text_model_preserved(self):
        from terminal.llm import QwenClient
        from unittest.mock import MagicMock
        client=QwenClient({**self.app.client.config,'model':'qwen-plus'})
        images=[{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,AA=='}}]}]
        opener=MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value=b'{"data":[{"id":"qwen3-vl-plus"}]}'
        with patch('terminal.llm.build_opener',return_value=opener):
            self.assertEqual(client.request_config(images,'test-key')['model'],'qwen3-vl-plus')
            self.assertEqual(client.request_config(images,'test-key')['model'],'qwen3-vl-plus')
        self.assertEqual(opener.open.call_count,1)
        self.assertEqual(opener.open.call_args.args[0].full_url,client.config['base_url'].rstrip('/')+'/models')
        self.assertEqual(client.request_config([{'role':'user','content':'hello'}],'test-key')['model'],'qwen-plus')
        client.config={**client.config,'vision_model':'my-visual-model'}
        self.assertEqual(client.request_config(images,'test-key')['model'],'my-visual-model')
        client.config={k:v for k,v in client.config.items() if k!='vision_model'};client._vision_models.clear()
        opener.open.return_value.__enter__.return_value.read.return_value=b'{"data":[]}'
        with patch('terminal.llm.build_opener',return_value=opener),self.assertRaisesRegex(RuntimeError,'No supported vision model'):
            client.request_config(images,'test-key')

    def test_domain_words_never_execute_or_inject_robot_context(self):
        requests = ['修复机器人场景编辑代码', '写一个天气接口', '生成一个桌子', '检测飞特舵机波特率', '读取我的机械臂', '继续', '没变']
        self.app.last_scene_request = '生成一个椅子'
        self.app.agent.history = [{'role':'user','content':'检测飞特舵机波特率'}]
        for request in requests:
            with self.subTest(request=request), patch.object(self.app.client,'complete',return_value={'content':'Model reply'}) as model, patch.object(self.app,'tool',side_effect=AssertionError('No implicit tool')), patch.object(self.app.viewer,'status',side_effect=AssertionError('No implicit state')):
                self.assertEqual(self.app.agent.reply(request),'Model reply')
                messages,tools=model.call_args.args
                self.assertNotIn('generate_scene',{t['function']['name'] for t in tools})
                systems=' '.join(m['content'] for m in messages if m['role']=='system')
                self.assertNotIn('latest_generated_scene',systems)
                self.assertNotIn('MuJoCo',systems)
                self.assertNotIn('你是MuJoCo操作Agent',systems)
                self.assertFalse(self.app.active_toolsets)
                self.assertIsNone(self.app.agent.on_turn_finished)

    def test_unloaded_robot_tool_is_rejected_without_execution(self):
        with patch.object(self.app.client,'complete',side_effect=[call('open_simulator'),{'content':'Tool unavailable.'}]) as model, patch.object(self.app.viewer,'open') as opened:
            self.app.agent.reply('打开仿真器')
            opened.assert_not_called()
            receipts=[json.loads(m['content']) for m in model.call_args.args[0] if m['role']=='tool']
            self.assertEqual(receipts[-1]['error'],'ValueError')

    def test_agent_and_task_toolsets_do_not_load_robotics(self):
        for group,expected in [('tasks','task_submit'),('agents','spawn_agent')]:
            self.app.prepare_input('handle task',[])
            self.app.tool('load_toolset',{'name':group})
            context=self.app.agent.context_provider('handle task')
            names={t['function']['name'] for t in context['tools']}
            self.assertIn(expected,names)
            self.assertNotIn('generate_scene',names)
            self.assertNotIn('viewer',context['live_context']())

    def test_multi_turn_history_survives_session_save_and_restore(self):
        from terminal.session import SessionStore
        config=self.app.client.config
        with patch.object(self.app.client,'complete',return_value={'content':'I will use project name Birch.'}):
            self.app.agent.reply('项目名字叫Birch')
        store=SessionStore(self.root/'saved.sqlite')
        try:
            store.save(config,self.app.agent.history,[],summaries=self.app.agent.turn_summaries)
            identity=store.session_id
        finally:store.close()
        self.app.agent.history=[]
        store=SessionStore(self.root/'saved.sqlite')
        try:
            state=store.resume(config,identity)
            self.app.agent.history=state['history']
            self.app.agent.turn_summaries=state['summaries']
        finally:store.close()
        with patch.object(self.app.client,'complete',return_value={'content':'Birch'}) as model:
            self.assertEqual(self.app.agent.reply('刚才项目叫什么？'),'Birch')
            messages=model.call_args.args[0]
            self.assertTrue(any(m['role']=='user' and m['content']=='项目名字叫Birch' for m in messages))
            self.assertTrue(any(m['role']=='assistant' and 'Birch' in m['content'] for m in messages))
        self.assertEqual(len(self.app.agent.history),4)
