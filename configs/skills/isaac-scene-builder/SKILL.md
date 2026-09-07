---
name: isaac-scene-builder
description: >
  Build Isaac Sim USD robot environments through Loop's authenticated bridge,
  including attached cameras, bounded physics stepping and synchronized captures.
---

Load robotics tools. sim_create(backend=isaac) connects to an operator-configured
Isaac bridge; it does not install Isaac or start a GUI. If the bridge is absent,
report the actual error and locate the project's SIMULATION_WORKBENCH guide.
Never silently change an endpoint, launch a second instance or retry a mutation
whose receipt is missing.

Inspect the returned version/capabilities. sim_edit adds boxes and local USD robot
references; paths resolve on the Isaac host. Adding geometry resets this owned
world; report that behavior and build before collecting an episode. Import MJCF
or URDF only through sim_convert for the installed version, then
check articulation/limits/masses and a bounded control response. Format conversion
does not prove equivalent dynamics across simulators.

Create fixed cameras under world and wrist cameras under the exact existing USD
link prim. sim_camera takes parent-local metres and wxyz OpenGL camera orientation
(+X right, +Y up, -Z forward). sim_capture returns RGB, metric image-plane depth,
instance segmentation and per-frame intrinsics/extrinsics. Inspect actual images.

Use sim_task and sim_step to evaluate requested measurable conditions. Missing
contact measurements remain inconclusive. Do not substitute USD authored poses,
trajectory animation or fixed-joint attachment for evidence of physical grasping.
Keep the current provider/profile and Loop permission rules. Skills confer no
permission to start training or operate hardware.
