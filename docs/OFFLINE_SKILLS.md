# 离线执行型 Skills

已反复使用的启动流程可以保存为用户 Skill 包：`SKILL.md` 提供使用说明，`run.json` 指定平台入口，`scripts/` 保存 Bash 或 Windows 批处理。选择、执行和日志读取直接使用本地命令分发，不调用聊天 API。普通 Skill 没有 run.json 时仍只作为说明，不因被读取或召回而执行。

## 选择和运行

无聊天 API 时用 `loop node` 进入本地终端：

```text
/skills
/skills inspect 启动Jetson Host
/skills run 启动Jetson Host
/skills status 启动Jetson Host
/skills logs 启动Jetson Host
/skills stop 启动Jetson Host
```

`/skills` 列可执行包的标题和内部名称，支持按标题调用与 Tab 补全；同名不猜测，可用唯一 Skill 名称。`status`／`logs`／`stop` 也能找到本终端已启动但源包后来被删除或改名的实例。启动后服务由 Node 维持，不需要 LLM 心跳；退出 Loop 会回收这些进程。`--once` 退出也会清理，不能当守护服务启动器。

无聊天 API 不表示所有网络都不需要：SSH、远端推理接口仍须可达，模型和依赖须事先准备好。

## 固化已有进程配置

```text
/node profiles
/skills save jetson-host start-jetson-host 启动Jetson Host
```

save 把现有 `~/.loop/processes/PROFILE.json` 的 argv、cwd、停止命令和环境声明导出成新包；只为当前主机生成脚本，不假装 Linux 命令能直接在 Windows 使用。不覆盖已有 Skill，不运行源程序，也不把配置存在等同于历史验收成功。生成脚本固定 argv 并转义，外部脚本、可执行程序、模型路径仍是外部依赖，不会自动复制进包。

模型侧入口为 `skill_executables`、`skill_export`、`skill_run`；run 要求读取到的包哈希。export 默认走现有 ask／approve，run 继续通过 node_start 和 process 的宿主执行门禁（run_python=allow）；plan 禁止执行和导出。授权一次流程不表示可以任意改目标、使能或运动。命令由脚本确定，Skill 文本不能给自己授权。

## 包结构和平台入口

```text
~/.loop/skills/start-host/
  SKILL.md
  run.json
  scripts/start.sh
  scripts/stop.sh
  scripts/start.cmd
  scripts/stop.cmd
```

只需保留实际支持平台的文件。run.json 示例：

```json
{
  "version": 1,
  "title": "启动Host",
  "cwd": ".",
  "platforms": {
    "posix": {"start": "scripts/start.sh", "stop": "scripts/stop.sh"},
    "nt": {"start": "scripts/start.cmd", "stop": "scripts/stop.cmd"}
  },
  "env_names": []
}
```

stop 可省略；存在时在停止流程先运行，随后回收所拥有的本地进程。`cwd="."` 指向本次运行的包快照，也可指定绝对工作目录。env／env_names／remote 复用进程配置格式，凭据只引用已有环境变量名。POSIX 使用 Bash；Windows 通过 cmd.exe 执行 .cmd／.bat，并用管道输入、文件输出和进程树停止，无 POSIX PTY 依赖。Windows 批处理导出拒绝有 cmd 展开歧义的参数，复杂情况应编写固定脚本后检查；本轮只完成 Linux 端到端实测。

包内脚本不能指向目录外或使用符号链接，包文件总大小上限1 MiB、文件最多100个；哈希涵盖 SKILL.md、run.json 和 scripts 下文件。启动子进程再次校验，并复制为私有临时快照；运行期间源文件改变不影响当前包内停止脚本。快照不冻结外部依赖，也不是宿主代码沙箱。

## 反馈和验收

复用 Node 生命周期、统一权限与 [共享资源基础层](RESOURCE_RUNTIME.md)，不会新造任务循环。资源不足即报告未启动；重复启动同一包被拒绝。节点心跳、脚本进程存活、退出码、输出、停止结果均可查看，`task_success`／`readiness` 保持未验证，不能把 Bash 退出0当作机械臂或推理服务已经就绪。

需要设备就绪验收、机械臂初始化、模型健康检查的流程，应在所保存的脚本中显式检查并以失败退出码停止后续步骤。当前没有从历史自然语言自动重建流程、自动补齐依赖或重放未知副作用，也没有独立 DAG 配方解析器。启动驱动、Host、推理服务与机械臂运动必须在具体脚本说明中区分。

## 当前本机保存的入口

2026-09-07 从已有用户进程配置导出以下包，均通过 Skill 格式和 Bash语法校验；本轮未启动对应服务、验证远端就绪或控制机械臂：

| 标题 | Skill 名称 | 源配置 |
| --- | --- | --- |
| 启动Jetson Host | start-jetson-host | jetson-host |
| 启动机械臂程序 | start-robot | jetson-robot |
| 启动ACT推理 | start-act-inference | workstation-act |
| 启动OpenPI推理 | start-openpi-inference | openpi-policy |

源配置与生成包留在 `~/.loop`；项目不保存个人命令、地址和凭据。验证入口为 test_offline_skills、test_offline_skill_terminal：真实 Bash／进程、中文输入输出 PTY、禁止模型调用、审批、修改检测、取消和快照停止。


### 重复任务快捷复用（2026-09-07）

已有适用且已验证流程时，保留 Skill 名称、已检查包 sha256 和就绪验收条件，直接 skill_run 再做定向就绪检查，不必每次 skill_read 三份文件、遍历目录或扫描所有 Skill。需要更新检查时可调用 `skill_executables({"name":"start-robot"})`，只检查指定包；无 name 仍列全部。该入口不启动设备。skill_run 在执行前复核包哈希，包变化拒绝旧哈希。

手动 Task 默认增加 skill_executables/skill_run，继续通过原有技能、进程和执行权限；定时/事件任务不能获得 skill_run。是否单独建 Task 依据用户既有偏好与当前要求，不用固定关键词拦截所有对话。

包哈希覆盖 Skill 自身，不代表外部工作目录或远端机器人代码版本。已知机器人代码/配置变更后应检查受影响依赖并更新验证记录；尚未实现通用远端依赖版本追踪。启动受理不等于就绪，用户不纠正也不等于验收通过。失败时再读取相关日志和源码，避免每次重走完整探索流程。

远端项目可将连接观察、入口与已跟踪文件指纹存入 `.loopros/context.json`，用 `python3 .loopros/check_context.py` 一次返回概要。Jetson 当前部署位置与实查结果见 [运行记录](RUNBOOK.md)。仅指纹一致不能替代就绪验收；依赖变更需定向检查并备份后更新，不自动覆盖基线。
