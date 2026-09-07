---
name: simulation-learning-data
description: >
  Configure multi-camera robot tasks, collect aligned simulation demonstrations,
  and prepare ACT-shaped datasets or Gymnasium environments for robot learning.
---

Inspect the simulation's action_space kind, names, units and bounds. A MuJoCo
actuator command is not automatically a joint target; Isaac's bridge uses joint
position targets. Preserve the user's camera set, task, variation and seed.

Define measurable success with sim_task. A reset and a variation are distinct:
variation is metadata, and seed alone does not randomize a scene. Apply requested
scene variations explicitly before collecting. A task horizon limits control
steps, not internal physics frames.

Use sim_record for bounded demonstrations. Observation[t] and all cameras precede
issued action[t]; next_observations[t] follows it. Record failed episodes as failed,
and reject incomplete episodes. Never infer grasp success from controller exit.

HDF5 contains observations/qpos, images/<camera>, depth, segmentation, intrinsics,
camera_to_world, action, timestamps, rewards and termination. Check camera shapes,
joint dimensions and action semantics against the chosen ACT trainer. File layout
compatibility does not imply an unmodified RLBench-ACT robot/policy configuration
will work. action_chunk provides future actions and is_pad; exclude padding from
loss and fit normalization on training episodes only.

For RL, SimulationEnv provides reset/step, reward, terminated/truncated and optional
camera observations. Use the selected external trainer/environment through the
existing process workflow; actual checkpoints and held-out success rates are the
evidence for learning. Do not start an unrequested long training run.
