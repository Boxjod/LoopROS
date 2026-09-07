"""Validated rigid scene specification -> trusted MJCF compiler -> physics smoke."""
import json
import hashlib
import math
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET

SCENE_PROMPT = """将用户场景转换成一个 JSON 对象，不输出代码或 Markdown。
支持范围：桌面（默认1.2x0.8m，中心xy=0，桌面高度0.75m）及最多20个刚体 box/sphere/cylinder。
桌子由编译器自动创建，不要放入objects；地面z=0，桌面z=0.75。
物体放在桌面时中心z=0.75+物体半高，例如0.15m方块中心z=0.825。
输出字段：objects, assumptions, unsupported, needs_expert；可选table={size:[长,宽,厚],height:桌面高度,color:[r,g,b,a]}。
用户未给参数就自行选择合理默认值或合理随机值，写入assumptions，不要求确认。
仅生成桌子时objects=[]合法；泛指桌面场景时可默认加一个彩色方块。由当前模型处理全部布局推理。
objects 每项严格为 {name, shape, size, position, color, mass}。
name 为唯一英文标识符；box size=[完整长,宽,高]，sphere=[半径]，cylinder=[半径,完整高]。
position 为世界坐标中心 xyz（米，z向上）；color 为rgba四个0..1数；mass 为kg。
对象必须完全在桌面边界内，底部不低于0.75，不重叠；可略高于桌面让其落下。
assumptions 是补全尺寸/代理几何的说明字符串列表；unsupported 是无法忠实表达的需求列表。
单把固定椅子可使用替代预设JSON：{preset:"chair",include_table:false,color:[0.55,0.3,0.12,1],assumptions:[],unsupported:[],needs_expert:false}；尺寸固定0.45×0.45×0.85m，不支持此预设自定义尺寸/活动关节/额外物体，不可忽略这些要求。include_table=true添加默认空桌。
机器人、铰接抽屉、绳索、流体、软体、网格资产均未支持，必须放入unsupported，不可静默替换成盒子。
needs_expert 为兼容旧格式保留的布尔字段，始终输出false；包括复杂空间推理在内均由当前模型完成。
保留用户要求的数量、颜色、相对位置；不确定的语义明确写入assumptions。
"""


def _vector(value, size, low, high):
    if not isinstance(value, list) or len(value) != size:
        raise ValueError("invalid vector dimension")
    if any(type(x) not in (int, float) or not math.isfinite(x) or not low <= x <= high for x in value):
        raise ValueError("non-finite or out-of-range scene value")
    return value


DEFAULT_TABLE = {"size": [1.2, 0.8, 0.1], "height": 0.75, "color": [0.6, 0.5, 0.4, 1]}


def table_spec(spec):
    table = spec.get("table", DEFAULT_TABLE)
    if not isinstance(table, dict) or set(table) != {"size", "height", "color"}:
        raise ValueError("table requires size, height, color")
    _vector(table["size"], 3, 0.02, 3)
    _vector([table["height"]], 1, 0.1, 1.5)
    _vector(table["color"], 4, 0, 1)
    if table["size"][2] >= table["height"]:
        raise ValueError("table thickness must be smaller than table height")
    return table


def default_scene(cube=True):
    return {"objects": [{"name": "cube", "shape": "box", "size": [0.15]*3,
                         "position": [0, 0, 0.825], "color": [0.85, 0.12, 0.1, 1], "mass": 0.2}] if cube else [],
            "assumptions": ["未指定参数采用1.2×0.8m桌面，高0.75m；默认红色0.15m方块" if cube else "采用默认空桌面"],
            "unsupported": [], "needs_expert": False}


def save_default_scene(directory, cube=True):
    spec = default_scene(cube)
    xml = compile_scene(spec)
    check = physics_check(xml)
    output = Path(directory) / uuid.uuid4().hex
    output.mkdir(parents=True)
    (output / "scene.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2))
    (output / "scene.xml").write_text(xml)
    report = {"scene": str(output / "scene.xml"), "description": "默认桌面场景", "backend": "mujoco",
              "model": "local-default", "expert_used": False, "validation": check, "assumptions": spec["assumptions"]}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def chair_scene(include_table=False):
    return {"preset": "chair", "include_table": include_table, "color": [0.55, 0.3, 0.12, 1],
            "assumptions": ["固定木椅：宽0.45m、深0.45m、总高0.85m，座高0.45m；座面、靠背和四条腿具有碰撞几何"],
            "unsupported": [], "needs_expert": False}


def compile_chair(spec):
    if spec['include_table']:
        root = ET.fromstring(compile_scene(default_scene(False)))
        world = root.find('worldbody')
    else:
        root = ET.Element('mujoco', model='loop_chair_scene')
        ET.SubElement(root, 'option', timestep='0.002', integrator='implicitfast')
        world = ET.SubElement(root, 'worldbody')
        ET.SubElement(world, 'light', pos='0 0 3')
        ET.SubElement(world, 'geom', name='floor', type='plane', size='2 2 0.1', rgba='0.3 0.3 0.3 1')
    body = ET.SubElement(world, 'body', name='chair', pos='-1 0 0' if spec['include_table'] else '0 0 0')
    color = ' '.join(map(str, spec['color']))
    def box(name, pos, size):
        ET.SubElement(body, 'geom', name=name, type='box', pos=pos, size=size, rgba=color)
    box('chair_seat', '0 0 0.4275', '0.225 0.225 0.0225')
    box('chair_back', '0 0.205 0.65', '0.225 0.02 0.2')
    for index, (x, y) in enumerate(((-1,-1), (-1,1), (1,-1), (1,1))):
        box('chair_leg_' + str(index), f'{x*.2} {y*.2} 0.2025', '0.025 0.025 0.2025')
    return ET.tostring(root, encoding='unicode')


def save_chair_scene(directory, include_table=False):
    spec = chair_scene(include_table)
    xml = compile_scene(spec)
    validation = physics_check(xml)
    output = Path(directory) / uuid.uuid4().hex
    output.mkdir(parents=True)
    (output / 'scene.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2))
    (output / 'scene.xml').write_text(xml)
    report = {'scene': str(output / 'scene.xml'), 'description': '木椅预设', 'backend': 'mujoco',
              'model': 'local-chair-preset', 'expert_used': False, 'validation': validation,
              'assumptions': spec['assumptions'], 'scene_sha256': hashlib.sha256(xml.encode()).hexdigest(),
              'contents': ['chair'] + (['table'] if include_table else []), 'report': str(output / 'report.json')}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def validate_scene(spec):
    if isinstance(spec, dict) and spec.get('preset') == 'chair':
        if set(spec) != {'preset', 'include_table', 'color', 'assumptions', 'unsupported', 'needs_expert'}:
            raise ValueError('Invalid chair preset fields')
        _vector(spec['color'], 4, 0, 1)
        if type(spec['include_table']) is not bool or spec['needs_expert'] is not False:
            raise ValueError('Invalid chair preset settings')
        if any(not isinstance(spec[k], list) or any(not isinstance(x, str) for x in spec[k]) for k in ('assumptions', 'unsupported')):
            raise ValueError('Invalid chair preset explanations')
        if spec['unsupported']:
            raise ValueError('场景超出已实现范围: ' + '; '.join(spec['unsupported']))
        return spec
    if not isinstance(spec, dict) or set(spec) - {"table"} != {"objects", "assumptions", "unsupported", "needs_expert"}:
        raise ValueError("invalid scene fields")
    for field in ("assumptions", "unsupported"):
        if not isinstance(spec[field], list) or any(not isinstance(x, str) for x in spec[field]):
            raise ValueError("invalid scene explanation")
    if type(spec["needs_expert"]) is not bool:
        raise ValueError("needs_expert must be boolean")
    if spec["unsupported"]:
        raise ValueError("场景超出已实现范围: " + "; ".join(spec["unsupported"])[:1000])
    if spec["needs_expert"]:
        raise ValueError("场景仍需专家复核")
    if not isinstance(spec["objects"], list) or not 0 <= len(spec["objects"]) <= 20:
        raise ValueError("scene allows 0..20 objects; the table is already included")
    table = table_spec(spec)
    names, bounds = set(), []
    for obj in spec["objects"]:
        if not isinstance(obj, dict) or set(obj) != {"name", "shape", "size", "position", "color", "mass"}:
            raise ValueError("invalid object fields")
        name = obj["name"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", name) or name in names:
            raise ValueError("invalid or duplicate object name")
        names.add(name)
        shape = obj["shape"]
        if shape not in ("box", "sphere", "cylinder"):
            raise ValueError("unsupported primitive")
        sizes = _vector(obj["size"], {"box": 3, "sphere": 1, "cylinder": 2}[shape], 0.005, 0.5)
        half = ([x / 2 for x in sizes] if shape == "box" else
                [sizes[0]] * 3 if shape == "sphere" else [sizes[0], sizes[0], sizes[1] / 2])
        position = _vector(obj["position"], 3, -2, 2)
        _vector(obj["color"], 4, 0, 1)
        _vector([obj["mass"]], 1, 0.001, 20)
        if (abs(position[0]) + half[0] > table["size"][0]/2 or abs(position[1]) + half[1] > table["size"][1]/2
                or position[2] - half[2] < table["height"] - 1e-8 or position[2] + half[2] > table["height"] + 0.75):
            raise ValueError(f"objects[{name}].position={position}: bottom z must be >={table['height']}; objects must fit the table bounds {table['size'][:2]}. Box size is full dimensions; table is built in, not an object.")
        for p, h in bounds:
            if all(abs(a - b) < ha + hb - 1e-8 for a, b, ha, hb in zip(position, p, half, h)):
                raise ValueError("initial object bounding boxes overlap")
        bounds.append((position, half))
    return spec


def compile_scene(spec):
    validate_scene(spec)
    if spec.get('preset') == 'chair':
        return compile_chair(spec)
    root = ET.Element("mujoco", model="loop_ros_generated_scene")
    ET.SubElement(root, "option", timestep="0.002", integrator="implicitfast")
    world = ET.SubElement(root, "worldbody")
    ET.SubElement(world, "light", pos="0 0 3")
    ET.SubElement(world, "geom", name="floor", type="plane", size="2 2 0.1", rgba="0.3 0.3 0.3 1")
    table = table_spec(spec)
    length, width, thickness = table["size"]
    height = table["height"]
    color = " ".join(map(str, table["color"]))
    ET.SubElement(world, "geom", name="table", type="box", pos=f"0 0 {height-thickness/2}",
                  size=f"{length/2} {width/2} {thickness/2}", rgba=color)
    leg = min(0.035, length/8, width/8)
    for i, (x, y) in enumerate(((-1,-1), (-1,1), (1,-1), (1,1))):
        ET.SubElement(world, "geom", name=f"table_leg_{i}", type="box",
                      pos=f"{x*(length/2-leg)} {y*(width/2-leg)} {(height-thickness)/2}",
                      size=f"{leg} {leg} {(height-thickness)/2}", rgba=color)
    for obj in spec["objects"]:
        body = ET.SubElement(world, "body", name=obj["name"], pos=" ".join(map(str, obj["position"])))
        ET.SubElement(body, "freejoint")
        size = obj["size"]
        size = [x / 2 for x in size] if obj["shape"] == "box" else [size[0], size[1] / 2] if obj["shape"] == "cylinder" else size
        ET.SubElement(body, "geom", type=obj["shape"], size=" ".join(map(str, size)),
                      rgba=" ".join(map(str, obj["color"])), mass=str(obj["mass"]))
    return ET.tostring(root, encoding="unicode")


def physics_check(xml):
    import mujoco
    import numpy as np
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    for _ in range(250):
        mujoco.mj_step(model, data)
        if np.any(data.warning.number) or not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
            raise ValueError("generated scene has invalid physics")
    return {"compiled": True, "physics_smoke": "pass", "sim_seconds": float(data.time),
            "semantic_verdict": "unverified", "task_success": "not_evaluated"}


class SceneGenerationError(ValueError):
    def __init__(self, details):
        self.details = details
        super().__init__(details["message"])


def parse_scene(content):
    text = content.strip()
    # Accept an enclosing JSON fence, without extracting arbitrary prose/code.
    if text.startswith("```json\n") and text.endswith("```"):
        text = text[8:-3].strip()
    elif text.startswith("```\n") and text.endswith("```"):
        text = text[4:-3].strip()
    return json.loads(text)


def generate_scene(description, primary, expert, directory, complex_task=False,
                   stop_event=None, on_event=None, compose=None, current_context=None):
    if not isinstance(description, str) or not description.strip() or len(description) > 16000:
        raise ValueError("场景描述须为1..16000字符")
    if stop_event and stop_event.is_set():
        raise RuntimeError("Master stopped")
    simple = description.strip().rstrip("。.!！")
    if not complex_task and simple in {'生成一个椅子', '生成一把椅子', '生成椅子', '椅子', '一把椅子', '生成一个木椅', '生成一把木椅'}:
        return save_chair_scene(directory)
    if not complex_task and simple in {'生成一个桌子和一个椅子', '生成桌子和椅子', '生成一张桌子和一把椅子'}:
        return save_chair_scene(directory, include_table=True)
    if not complex_task and simple in {"桌面场景", "生成一个桌面场景", "生成桌面场景", "默认桌面场景", "一个桌面场景", "tabletop scene"}:
        return save_default_scene(directory)
    if not complex_task and simple in {"桌子", "生成一个桌子", "生成一张桌子", "一张桌子", "空桌面"}:
        return save_default_scene(directory, cube=False)
    prompt = SCENE_PROMPT
    if compose:
        from toolchain.composition import PROMPT
        prompt = "将用户请求转成单个组合编辑JSON，不输出解释、Markdown或XML。只使用下面的顶层字段。\n" + PROMPT + "\n当前场景物品：" + json.dumps(current_context or {},ensure_ascii=False)
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": description}]
    client = primary  # Legacy expert/complex_task arguments never select another provider.
    attempts = []
    emit = on_event or (lambda *args: None)

    def cancelled():
        if stop_event and stop_event.is_set():
            raise RuntimeError("Master stopped")

    def save_report(report, spec=None, xml=None):
        output = Path(directory) / uuid.uuid4().hex
        output.mkdir(parents=True, exist_ok=False)
        if xml is not None:
            (output / "scene.xml").write_text(xml, encoding="utf-8")
            (output / "scene.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        report["attempts"] = attempts
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return output

    stage, error = "model_request", "No valid scene generated"
    cause = {}
    for attempt in range(1, 4):
        cancelled()
        emit("Scene", f"Generating and validating scene (attempt {attempt}/3)")
        raw, stage = "", "model_request"
        try:
            result = client.complete(messages, [])
            cancelled()
            raw = result.get("content") or ""
            stage = "scene_json"
            spec = parse_scene(raw)
            if isinstance(spec, dict) and spec.get("needs_expert") is True:
                # Obsolete routing hint; geometry and unsupported checks still apply.
                spec["needs_expert"] = False
            if compose and isinstance(spec,dict) and any(k in spec for k in ("base","add","remove","move")):
                stage = "scene_composition"
                return compose(spec)
            stage = "scene_validation"
            xml = compile_scene(spec)
            stage = "physics_validation"
            check = physics_check(xml)
            cancelled()
        except (ValueError, RuntimeError, ImportError) as exc:
            cancelled()
            error = str(exc)[:2000]
            cause = getattr(exc,"details",{})
            attempts.append({"attempt": attempt, "model": client.config["model"],
                             "stage": stage, "error": type(exc).__name__, "message": error, "candidate": raw[:20000]})
            # Availability and unsupported capabilities cannot be repaired by
            # changing the user's geometry or silently choosing another model.
            if stage == "model_request" or isinstance(exc, ImportError) or getattr(exc,"details",{}).get("retryable") is False or error.startswith("场景超出已实现范围"):
                break
            emit("Scene repair", f"{stage}: {error}")
            messages.extend([
                {"role": "assistant", "content": raw[:20000]},
                {"role": "user", "content": "Validation failed at " + stage + ": " + error +
                 "\nCorrect the previous JSON and return the complete SceneSpec only. Preserve the original user request. "
                 "Use the exact schema in the system message. The table is built in. Do not retry the unchanged candidate; "
                 "do not remove requested objects or unsupported requirements to pass validation."}])
            continue
        attempts.append({"attempt": attempt, "model": client.config["model"], "stage": "validated"})
        report = {"description": description, "backend": "mujoco", "model": client.config["model"],
                  "expert_used": False, "validation": check, "assumptions": spec["assumptions"]}
        output = save_report(report, spec, xml)
        return {"scene": str(output / "scene.xml"), "report": str(output / "report.json"), **report}

    details = {"error": "scene_generation_failed", "stage": stage, "message": error,
               "retryable": False, "repair_attempts": len(attempts), "cause": cause,
               "hint": "Do not repeat the same generate_scene request or rewrite the user's requirements. "
                       "Report this concrete blocker; expert_advice does not fix API access or unsupported geometry."}
    output = save_report({"description": description, "validation": {"compiled": False}, **details})
    details["report"] = str(output / "report.json")
    raise SceneGenerationError(details)
