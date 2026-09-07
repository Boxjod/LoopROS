---
name: mujoco-scene-builder
description: >
  Build or edit MuJoCo robot environments with fixed and wrist cameras, then verify
  geometry, physics and observations using Loop simulation tools.
---

Use `load_toolset robotics` and read the actual tool schemas. For an existing GUI,
use its existing compose_scene/model_library/simulator_control workflow; workbench
instances are separate headless simulations, not the same GUI scene.

For a reproducible workbench use sim_create(backend=mujoco, scene=local MJCF) or a
blank instance. sim_edit adds boxes (full dimensions in metres) and local MJCF
robots. Inspect body and actuator names before targeting them; actuator controls
are not universally joint positions. Preserve supplied robot models and units.

Measure bounds and plan placement before importing assets. Use sim_camera with
world for a fixed camera, or an existing body for a wrist camera. Positions and
wxyz quaternions are local to the parent; camera axes are +X right, +Y up, -Z
forward. Choose resolution and views from the task, not a universal preset.

Use sim_task for measurable requested conditions, sim_step for bounded execution,
and sim_capture for RGB/depth/segmentation with calibration and state. Read the
PNG through read_image for visual claims. Numeric bounds and image statistics
alone do not establish semantic correctness. Fix concrete failures and recapture;
keep missing measurements inconclusive. Stop on unknown execution receipts.

Data collection is an explicit sim_record operation after the task and cameras
are configured; do not start training or replace the user's open simulator.
