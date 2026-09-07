# 共享资源基础层

Loop ROS 的资源管理属于运行基础设施，与 Session、Task、Agent 和机器人领域分离。核心入口是 `core.resources.ResourceManager`，只依赖标准库；`toolchain.admission.HostMonitor` 是本机遥测适配器。导入模块不采样、不连接设备、不启动模型。

`App.resources` 在应用初始化时创建，前台与同 state 的后台通过原有 `resource_leases.sqlite` 共享账本。原 `ResourceAdmission` 构造入口保留兼容，算法和持久化只有一份。当前额度共享范围仍是同一 state 目录，不是跨主机集群。

| 消费者 | 申请与释放 |
| --- | --- |
| Agent／TaskSupervisor | 进程启动准入；资源不足排队；结束释放 |
| NodeRuntime | 创建本地 Node 进程前申请；退出／取消／启动失败释放；保留设备所有权校验 |
| Python／自编工具 | run_python 执行段申请，进程清理后释放；资源不足返回 ResourceBusy，不伪装为已排队 |
| PolicyServices | 服务启动申请，退出／停止／启动失败释放；有共享管理器时按预算允许多个服务 |
| ModelPool | 可注入同一管理器；模型加载时申请，闲置仍持有，卸载时释放；加载异常释放 |

模型请求、Node、Python、模型驻留和策略服务使用工作负载标签分别统计。`max_workers` 仅限制 Agent 数量；其他工作负载共同消耗 RAM／CPU／VRAM。旧账本中没有标签的记录视为 Agent，不丢弃活跃预留。

Master 默认工具集中提供 `resource_status`，无需加载 agents 或 robotics。查询遵从统一权限门禁，plan 可读，deny 仍有效；返回采样、分类预留、共享预算和 Agent 可新增数量，不自动往每轮提示词注入遥测。Agent 工具组中的 `/agents` 保留相同信息。

## 接入约定

```python
from core.resources import ResourceManager
from toolchain.admission import HostMonitor

resources = ResourceManager(state_dir / "resource_leases.sqlite", policy, HostMonitor())
with resources.lease("python", {"ram_mb": 512, "cpu_cores": 0.5, "vram_mb": 0}):
    execute_and_reap_owned_process()
```

短操作用 lease 上下文确保异常释放。长进程用 `inspect(acquire=True, workload=..., request=...)` 原子申请，取得 token 后才能启动，启动成功 `bind(token, pid)`，失败／结束 `release(token)`。返回 None 表示未授权资源额度；是否排队由已有任务调度层决定。不能在 core 中依赖 terminal、创建会话或触发机器人动作。

请求字段为 ram_mb、cpu_cores、vram_mb、gpu_index；模型纯驻留允许 cpu_cores=0。通用未声明请求的默认估算为256 MiB RAM、0.25 CPU核、0显存；Agent 保留现有 resources 配置字段作为兼容成本默认。Python和Node目前使用上述通用估算，未根据脚本或远程负载推断成本。

策略服务可在 `config.json` 的 `services.pi05`／`services.act` 对象中添加 `resources` 请求，例如 `{"ram_mb":4096,"cpu_cores":1,"vram_mb":6144,"gpu_index":0}`；argv／cwd 保持原字段。显存估算和设备绑定由部署者按实际服务设置，0显存不代表服务实际不用GPU。配置经 settings_update 的原有门禁验证，下次启动生效。

## 边界

预算是保守估算加实测余量，并非 OS 硬限额。主机遥测能看到其他程序的占用，但未托管程序没有声明预留；当前窗口渲染器、外部模型服务、SSH远端程序及子进程自行创建的额外负载不因此获得独立租约或远端遥测。Node租约表示本地受管Node成本，不表示远端GPU容量。新增适配器应复用该接口并显式声明成本，不能据此宣称所有外部负载已受控。

采样平台边界、Agent默认上限和CPU／GPU阈值见 [AGENT_RUNTIME](AGENT_RUNTIME.md)。资源许可不替代安全权限、设备所有权、模型服务就绪检查或目标验收。停止与诊断路径不因资源不足被禁止，避免在压力下无法回收资源。

验证：`test_resource_foundation` 覆盖跨工作负载预算、真实双服务／Node进程释放、模型驻留及失败回收、默认查询工具权限和Python拒绝执行；原资源／Agent／Python测试保持兼容。


### 进程诊断与回收

`process_inspect` 补充本地/SSH 主机的进程 RSS 与可用 RAM；本机 RAM/CPU/VRAM 总预算仍由 `resource_status` 和共享 ResourceManager 管理，不另建账本。RSS 可能包含共享页，不能简单相加当作物理内存；可用 RAM 前后差额也不等于该进程释放量。外部/远端服务只观测，不冒充已有资源租约。

进程控制器使用 `ResourceManager.control_lease()` 在同一 leases 表固定记账 32 MiB RAM、0.05 CPU、0 VRAM；这是内部有界诊断/停止专用入口，不是模型可配置的预算绕过。即使常规工作负载因内存/CPU压力被拒绝，控制器仍可运行，结束/异常释放记账。远端脚本开销和外部服务并未纳入本机硬限制。不会执行 drop_caches、清空任意进程内存或因压力擅自杀服务。
