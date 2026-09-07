# Loop ROS 机器人工程 Agent

2026-09-05。能力范围从 MuJoCo 操作扩展到电机/驱动、故障排查、控制与模型计算、常用工具链。当前是一套带确定性计算、官方资料和证据记录的工程工作流，不代表所有机器人协议都已接通。

## 已接入的工具

| 工具 | 实际能力 | 执行边界 |
| --- | --- | --- |
| robot_toolchains | 检查当前Python环境包版本、PATH命令、ROS_DISTRO，给出工具链和官方手册入口 | 不导入SDK、不连接设备；安装存在不等于适配成功 |
| robot_docs | 查询ROS 2、ros2_control、MoveIt、Pinocchio、MuJoCo、Mink、DYNAMIXEL、ODrive、SocketCAN、EtherCAT、SimpleFOC官方资料 | 版本路径限定、一天缓存；未知厂商继续用已有联网工具查官方来源 |
| robot_diagnose | 根据实际日志匹配端口权限/掉线、通信超时、CAN bus-off、过流/电压、编码器和振荡排查路径 | 明确记录用户观测、假设和缺失项；不猜型号/固件对应错误码 |
| motor_torque | 校验电流/Kt定义，估算电机轴与减速器输出轴力矩 | 不把母线电流/负载百分比换成力矩，不发电机命令 |
| pid_trial | 实际离线单轴惯量/阻尼模型PID试验；条件积分抗饱和、测量微分低通、限幅、误差/超调/饱和统计 | 理想力矩源；不等于真实电流环或自动增益整定 |
| robot_model_analysis | 已校验模型的FK、世界坐标雅可比、惯量矩阵、偏置力、逆动力学及J转置力映射 | 默认保存的home状态；可指定qpos/qvel/qacc；不改变窗口或真机 |

原有 `devices`、串口接收、`simulator_control` 和 Mink FK/约束微分IK保持可用。工具注册在 `terminal/robotics.py`，计算位于 `toolchain/robot_engineering.py` 与 `toolchain/robot_model_analysis.py`。Mink仍是已有代码适配器，不将其误称为新增通用IK对话工具。

## 电流换算力矩

调用示例：

```json
{"current_A":2,"kt_Nm_per_A":0.1,"current_basis":"iq_peak","kt_current_basis":"iq_peak","gear_ratio":10,"efficiency":0.9}
```

此例电机轴估算力矩为 **0.2 N·m**，输出轴为 **1.8 N·m**。这是电机向负载传递动力、给定恒定效率的估算：

- 电机电磁力矩 `tau_motor = Kt * (I - signed_sensor_offset)`。
- 输出轴 `tau_output = tau_motor * reduction_ratio * efficiency`，减速比定义为电机转速/输出转速。

必须知道Kt采用哪一种电流定义：直流电枢、Iq峰值/RMS、相电流峰值/RMS；工具要求输入与Kt定义匹配。不自动套用sqrt(2)/sqrt(3)、Kv倒数或厂商专用换算。`current_offset_A`仅为有符号电流传感器零偏，不代表无载摩擦电流。外部接触力估计还需减去重力、惯性和摩擦等，不能把这个结果当力矩传感器读数或用同一效率模型描述反拖回馈。

依据：[ODrive的Iq与力矩定义](https://docs.odriverobotics.com/v/latest/fibre_types/com_odriverobotics_ODrive.html)、[电机参数](https://docs.odriverobotics.com/v/latest/articles/motor-parameters.html)。公式只有在参数/定义匹配时适用；不是对未知电机的参数承诺。

## PID与模型分析

PID参数示例：`kp=10, ki=1, kd=2, inertia_kg_m2=0.05, damping_Nm_s_per_rad=0.1, torque_limit_Nm=2, target_rad=1`。默认dt=0.001s、时长3s。控制量单位N·m、反馈rad；模型为 `J*qdd + b*qd = torque - load`，每采样内采用恒定力矩的解析传播。结果包括轨迹文件、误差、超调和饱和比例，不自动将参数写入真实驱动器。限20000步；plan模式禁止仿真试验。

模型分析以保存的模型home位姿或显式参数计算，不默认当作实时关节测量。body必须是实际模型名称，例如`panda/hand`。qpos长度为nq，速度、加速度与广义力长度为nv；四元数须归一、有限值及标量关节限位须通过检查。雅可比是body原点在世界坐标中的线速度/角速度映射。

`wrench_to_joint` 输入顺序为 `[Fx,Fy,Fz,Mx,My,Mz]`，世界坐标、作用于body原点；`Jv.T*F + Jw.T*M`是外载荷广义力，抵消该载荷需反号，并考虑重力/动力学。逆动力学输出不是actuator ctrl，也不是电机电流。

本机MuJoCo 3.12的`mj_fullM(model,data,dst)`接口已实测；旧qM接口按字段存在性兼容，旧版本本轮未安装验证。来源：[3.12 API](https://mujoco.readthedocs.io/en/3.12.0/APIreference/APIfunctions.html#mj-fullm)。惯量矩阵通过对称正定和动力学残差检查，雅可比通过有限差分检查。PID设计参考：[control_toolbox PID](https://control.ros.org/master/doc/api/classcontrol__toolbox_1_1Pid.html)。

## 故障排查和真机接入

工作顺序：机械与供电→主机设备枚举→电气通信与链路→协议/寄存器→驱动状态机→反馈/标定→电流/速度/位置环→规划。不同层的问题不能用“调大PID”统一处理。

例如输入`CAN bus-off; encoder timeout`，工具返回CAN链路、编码器反馈和协议超时的候选原因，以及下一步需核对的位率、错误计数、编码器定义/接线、ID/固件和收发记录；结论仍是inconclusive，不声明电机损坏或自动清故障。依据：[SocketCAN](https://docs.kernel.org/networking/can.html)、[DYNAMIXEL Protocol 2.0](https://emanual.robotis.com/docs/en/dxl/protocol2/)。型号和固件未确定时不解码厂商错误位、不猜寄存器地址。

首批真机需要用户提供：电机/机械臂型号、驱动器和固件、通信方式/协议、供电和接线、节点地址/位率、编码器、减速器、工作模式、关节/电流限制及本地停止方式。当前串口为接收模式，真机发送驱动尚未实现；具体型号适配必须完成所有权、新鲜反馈、watchdog/限值、失联处理与硬件验收，不能以模型咨询替代。这些信息尚未提供，不虚构连接/转动结果。

## 证据与验证

计算和诊断报告保存在状态目录`engineering/`，含输入、单位、假设、结果、Episode/Review；PID完整轨迹留文件，模型默认只收到摘要。诊断记录的“用户输入”不升级为独立硬件事实。

`tests/test_robotics.py`覆盖力矩正负号/单位约束/缺参数、PID阶跃与抗饱和、雅可比有限差分、惯量正定及逆动力学残差、力映射、文档版本过滤/缓存、诊断假设区分和权限/无硬件副作用。

现有Panda模型、官方SocketCAN文档、当前工具链清单及真实模型问答验证结果保存于[validation.json](../artifacts/terminal/engineering/validation.json)。新增工具不安装ROS/电机SDK，不扫描其他项目，不自动使能设备。
