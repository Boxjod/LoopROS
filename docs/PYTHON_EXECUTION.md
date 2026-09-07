# Python 执行权限

2026-09-06。Loop 新增 `run_python`，实现见 [python_runner](../terminal/python_runner.py)。此前只有文件读写，没有 Python 执行工具；chmod 或笼统“允许所有权限”不能创造缺失的执行能力。

流程：read_file 读取已存在的工作区 `.py` 文件，取得 sha256；run_python 提交 path、expected_sha256，可选 arguments 字符串数组和 timeout_s（默认30，1–120秒）。run_python 在哈希校验后本地编译检查语法，失败不会启动子进程；正常执行无需额外调用 python_check，成功启动回执包含 syntax_valid。语法通过不代表运行或机器人目标成功。使用当前 Loop 的 sys.executable，不拼接 shell 命令，返回实际 stdout/stderr、returncode、是否截断、取消/超时和证据报告。stdout/stderr 各返回最多64KiB，运行中合计输出超过1MiB请求中断。退出码0仅证明进程正常退出，不代表机器人目标已完成。

动作经过同一个 PermissionGate；新状态默认 ask，plan 阻止执行。用户本轮明确授权后，当前 `artifacts/terminal/permissions.sqlite` 已将 run_python、feetech_scan、feetech_read、devices 设为 allow，其他规则保留。普通持久任务是否可用 run_python 取决于 worker_tools 和运行时权限；当前发行默认包含该工具，定时任务默认不包含；旧进程需要正常退出、重启才能加载新工具，权限文本不能热添加 Python 代码。

这是以宿主用户身份运行 Python，**不是沙箱**。哈希检查、路径约束和时限不隔离脚本的文件、网络或硬件访问，也不构成真机运动授权。不要把现有模拟运动门禁说成能约束任意 Python；优先使用已有飞特查询工具，不运行猜测的报文或极限位置脚本。子进程环境不自动转交 API Key 类变量。POSIX 使用独立进程组，取消、超时、输出超限及收尾清理使用 SIGINT，允许脚本运行 finally／中断处理；不自动升级 SIGTERM/SIGKILL。等待实际直接进程退出后才释放资源租约；10 秒仍未退出时显示 PID 和未停止状态，继续跟踪，保持队列暂停。Windows 使用新进程组和 CTRL_BREAK_EVENT，原生端到端尚未验收；独立会话子进程和远端程序必须由脚本／Node 自己处理停止，不能由直接进程退出推定硬件失能。

补齐的兼容入口为 `/home/boxjod/Workspace/box2net/feetech_baud_scan.py`。它自动切换到 LoopROS 虚拟环境，并调用既有模块，不复制协议代码；无 --port 时只有枚举到单一端口才继续，否则报告候选。`--environment` 只检查本地运行环境。默认扫描 ID 1–20，可传 --ids/--baudrates/--port。

验证：tests.test_python_runner 覆盖真实 stdout/stderr、非零退出、哈希过期、plan/ask、超时、输出上限、预取消、参数不被 shell 执行。真实 App.tool + 当前权限已执行脚本 --environment：returncode=0、stderr为空；本轮未执行真机扫描或运动。证据在 artifacts/terminal/python，相关回归日志见 artifacts/feetech/python-execution-tests.log。

长输出返回 `stdout_path` / `stderr_path` 文本文件，使用 read_file 的 offset/limit 按行取证，不为取回既有输出重新运行程序。内联输出各保留64KiB，文本文件各最多保留1MiB，文件截断由对应 `*_file_truncated` 标明；POSIX 文件创建权限0600。模型预览压缩保留退出码、停止原因和文件路径。test_python_runner 使用超过64KiB的真实子进程输出，验证可分页读到内联结果之外的末尾证据。

2026-09-08：终端执行中可独立输入“停止”／“停下”／stop，取消信号绕过普通消息队列。真实 Python 测试验证 SIGINT 清理回执、忽略中断时持续跟踪，以及取消后退出 0 仍仅为 inconclusive；真实 PTY 验证中文停止不入队、清理输出可见并可继续输入中文草稿。
