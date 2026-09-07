"""Compact factual turn records. Assistant prose never becomes execution evidence."""
import json


def summarize(request, answer, events, error=None):
    tools=[]
    tool_name = None
    for kind,text in events:
        if kind == 'tool':
            tool_name = text.partition('(')[0]
            continue
        if kind!='result': continue
        try: result=json.loads(text)
        except (ValueError,TypeError): continue
        if not isinstance(result,dict): continue
        if tool_name in ('session_task_read','session_task_update','load_toolset'):
            continue  # Current work/tool state already comes from live_context.
        viewer=result.get('viewer',result)
        evidence={k:result[k] for k in ('error','message','executed','action','scene') if k in result}
        if tool_name:
            evidence['tool'] = tool_name
        for key in ('path','sha256','start_line','end_line','total_lines','next_offset',
                    'returncode','report','stdout_path','stderr_path','valid','truncated',
                    'reuse_tool_call_id','stop_reason'):
            if key in result:
                evidence[key] = result[key]
        # Small inspected sources/results survive a turn without a new read.
        # Longer data retains its locator and an explicitly incomplete preview.
        for key in ('content','stdout','stderr'):
            value = result.get(key)
            if isinstance(value, str) and value:
                evidence[key] = value[:1200]
                if len(value) > 1200:
                    evidence[key+'_preview_truncated'] = True
        if isinstance(viewer,dict):
            evidence.update({k:viewer[k] for k in ('window_open','scene_sha256','reloaded') if k in viewer})
        if result.get('supported') is False:
            evidence.update({'error': result.get('reason', 'Unsupported adapter')})
        elif 'usb_devices' in result and 'input_devices' in result:
            evidence['device_inventory'] = {key: len(result.get(key, [])) for key in ('usb_devices', 'devices', 'input_devices')}
            evidence['opened'] = result.get('opened')
        if isinstance(result.get('objects'),dict): evidence['objects']=list(result['objects'])
        if tool_name in ('read_file','skill_read','python_check') and evidence.get('sha256'):
            identity = tuple(evidence.get(k) for k in ('tool','path','sha256','start_line','end_line'))
            for index, previous in enumerate(tools):
                if tuple(previous.get(k) for k in ('tool','path','sha256','start_line','end_line')) == identity:
                    # A later cache reference must not erase the earlier body.
                    evidence = {**tools.pop(index), **evidence}
                    break
        tools.append(evidence or {'result_received':True,'execution_verified':False})
    return {'request':request[:500], 'answer_excerpt':str(answer or '')[:500],
            'answer_is_execution_evidence':False, 'tool_evidence':tools[-8:],
            'status':'error' if error else 'tool_results' if tools else 'conversation_only',
            'error':str(error)[:500] if error else None}


def display(summary):
    if summary['error']: return '本轮总结：未完成；'+summary['error']
    if summary['tool_evidence']:
        last=summary['tool_evidence'][-1]
        if last.get('error'):
            result='工具失败：'+str(last.get('message') or last['error'])[:160]
        elif 'device_inventory' in last:
            counts = last['device_inventory']
            result = '已实际枚举：{} USB、{} 串口/摄像头节点、{} 输入节点；未打开设备'.format(counts['usb_devices'], counts['devices'], counts['input_devices'])
        elif last.get('objects'):
            result='场景物品：'+', '.join(last['objects'])+'；'+('窗口已打开' if last.get('window_open') else '窗口未确认打开')
        elif last.get('executed'):
            result='已执行：'+str(last.get('action','工具操作'))
        elif 'window_open' in last:
            result='窗口已打开' if last['window_open'] else '窗口未打开'
        else:
            result='已收到工具结果，不能仅据此判断任务成功'
        return '本轮总结：'+result+'。请求：'+summary['request'][:100]
    return '本轮总结：对话答复，未执行工具。'+summary['answer_excerpt'][:140]


def context(summaries, budget=6000):
    records=[]
    for entry in summaries[-3:]:
        records.append({'request':entry['request'][:250], 'status':entry['status'],
                        'tool_evidence':entry['tool_evidence'], 'error':entry['error']})
    while records and len(json.dumps(records,ensure_ascii=False)) > budget:
        if len(records) > 1:
            records.pop(0)
        elif records[0]['tool_evidence']:
            records[0] = {**records[0], 'tool_evidence': records[0]['tool_evidence'][1:]}
        else:
            records.pop(0)
    return json.dumps(records,ensure_ascii=False)
