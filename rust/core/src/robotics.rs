//! Port of contracts / execute-evidence-review semantics. This reference runtime
//! admits simulated bodies only, matching Python core.loop's hardware boundary.

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Task<const N: usize> {
    pub session_id: u32,
    pub task_id: u32,
    pub body_id: u32,
    pub target: [f32; N],
    pub tolerance: f32,
    pub max_attempts: u32,
    pub timeout_ms: u32,
}
#[derive(Clone, Copy, Debug)]
pub struct Embodiment<const N: usize> {
    pub body_id: u32,
    pub calibration: u32,
    pub limits: [(f32, f32); N],
    pub simulated: bool,
}
#[derive(Clone, Copy, Debug)]
pub struct Observation<const N: usize> {
    pub body_id: u32,
    pub calibration: u32,
    pub time_ms: u64,
    pub joints: [f32; N],
    pub joint_position: bool,
}
#[derive(Clone, Copy, Debug)]
pub struct Action<const N: usize> {
    pub session_id: u32,
    pub task_id: u32,
    pub body_id: u32,
    pub calibration: u32,
    pub target: [f32; N],
    pub expires_ms: u64,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Fault {
    Invalid,
    RealBody,
    Identity,
    Limit,
    MissingObservation,
    Expired,
    Driver,
    Store,
    Stop,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Verdict {
    Pass,
    Fail,
    Inconclusive,
}
#[derive(Clone, Copy, Debug)]
pub struct Review {
    pub verdict: Verdict,
    pub max_error: f32,
    pub error: Option<Fault>,
}
#[derive(Clone, Copy, Debug)]
pub struct Episode<const N: usize> {
    pub session_id: u32,
    pub task_id: u32,
    pub attempt: u32,
    pub before: Option<Observation<N>>,
    pub action: Option<Action<N>>,
    pub after: Option<Observation<N>>,
    pub error: Option<Fault>,
}
pub trait Body<const N: usize> {
    fn spec(&self) -> Embodiment<N>;
    fn observe(&mut self) -> Result<Observation<N>, Fault>;
    fn execute(&mut self, action: &Action<N>) -> Result<(), Fault>;
    fn stop(&mut self) -> Result<(), Fault>;
}
pub trait Clock {
    fn now_ms(&self) -> u64;
}
pub trait Planner<const N: usize> {
    fn plan(
        &mut self,
        task: &Task<N>,
        before: &Observation<N>,
        previous: Option<Review>,
    ) -> Result<[f32; N], Fault>;
}
pub trait Store<const N: usize> {
    fn intent(&mut self, action: &Action<N>) -> Result<(), Fault>;
    fn episode(&mut self, episode: &Episode<N>, review: &Review) -> Result<(), Fault>;
}

fn target<const N: usize>(q: &[f32; N], spec: &Embodiment<N>) -> Result<(), Fault> {
    if N == 0 {
        return Err(Fault::Invalid);
    }
    for (value, (low, high)) in q.iter().zip(spec.limits) {
        if !value.is_finite() || !low.is_finite() || !high.is_finite() || low > high {
            return Err(Fault::Invalid);
        }
        if *value < low || *value > high {
            return Err(Fault::Limit);
        }
    }
    Ok(())
}
fn observation<const N: usize>(
    obs: &Observation<N>,
    spec: &Embodiment<N>,
    now: u64,
    start: u64,
) -> Result<(), Fault> {
    if obs.body_id != spec.body_id || obs.calibration != spec.calibration {
        return Err(Fault::Identity);
    }
    if !obs.joint_position || obs.joints.iter().any(|v| !v.is_finite()) {
        return Err(Fault::MissingObservation);
    }
    if obs.time_ms > now || obs.time_ms < start {
        return Err(Fault::Expired);
    }
    Ok(())
}

pub fn run<const N: usize>(
    task: &Task<N>,
    body: &mut impl Body<N>,
    planner: &mut impl Planner<N>,
    clock: &impl Clock,
    store: &mut impl Store<N>,
) -> Result<Review, Fault> {
    let spec = body.spec();
    if !spec.simulated {
        return Err(Fault::RealBody);
    }
    if task.body_id != spec.body_id || task.session_id == 0 || task.task_id == 0 {
        return Err(Fault::Identity);
    }
    if !task.tolerance.is_finite()
        || task.tolerance <= 0.0
        || task.max_attempts == 0
        || task.timeout_ms == 0
    {
        return Err(Fault::Invalid);
    }
    target(&task.target, &spec)?;
    let start = clock.now_ms();
    let deadline = start
        .checked_add(u64::from(task.timeout_ms))
        .ok_or(Fault::Invalid)?;
    let mut previous = None;
    for attempt in 1..=task.max_attempts {
        let mut ep = Episode {
            session_id: task.session_id,
            task_id: task.task_id,
            attempt,
            before: None,
            action: None,
            after: None,
            error: None,
        };
        let execution = (|| {
            if clock.now_ms() >= deadline {
                return Err(Fault::Expired);
            }
            let before = body.observe()?;
            ep.before = Some(before);
            observation(&before, &spec, clock.now_ms(), start)?;
            let planned = planner.plan(task, &before, previous)?;
            target(&planned, &spec)?;
            if clock.now_ms() >= deadline {
                return Err(Fault::Expired);
            }
            let action = Action {
                session_id: task.session_id,
                task_id: task.task_id,
                body_id: task.body_id,
                calibration: spec.calibration,
                target: planned,
                expires_ms: deadline,
            };
            store.intent(&action)?;
            ep.action = Some(action);
            body.execute(&action)?;
            let after = body.observe()?;
            ep.after = Some(after);
            observation(&after, &spec, clock.now_ms(), before.time_ms)?;
            if clock.now_ms() >= deadline {
                return Err(Fault::Expired);
            }
            Ok(())
        })();
        ep.error = execution.err();
        if body.stop().is_err() {
            ep.error = Some(Fault::Stop);
        }
        let review = if let Some(error) = ep.error {
            Review {
                verdict: Verdict::Inconclusive,
                max_error: 0.0,
                error: Some(error),
            }
        } else if let Some(after) = ep.after {
            let mut max_error = 0.0f32;
            for (actual, wanted) in after.joints.iter().zip(task.target) {
                max_error = max_error.max((*actual - wanted).abs());
            }
            Review {
                verdict: if max_error <= task.tolerance {
                    Verdict::Pass
                } else {
                    Verdict::Fail
                },
                max_error,
                error: None,
            }
        } else {
            Review {
                verdict: Verdict::Inconclusive,
                max_error: 0.0,
                error: Some(Fault::MissingObservation),
            }
        };
        store.episode(&ep, &review)?;
        previous = Some(review);
        if review.verdict != Verdict::Fail {
            return Ok(review);
        }
    }
    previous.ok_or(Fault::Invalid)
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Fixture {
        q: [f32; 2],
        stopped: bool,
        fail_stop: bool,
        missing: bool,
    }
    impl Body<2> for Fixture {
        fn spec(&self) -> Embodiment<2> {
            Embodiment {
                body_id: 1,
                calibration: 1,
                limits: [(-1.0, 1.0); 2],
                simulated: true,
            }
        }
        fn observe(&mut self) -> Result<Observation<2>, Fault> {
            Ok(Observation {
                body_id: 1,
                calibration: 1,
                time_ms: 1,
                joints: self.q,
                joint_position: !self.missing,
            })
        }
        fn execute(&mut self, action: &Action<2>) -> Result<(), Fault> {
            self.stopped = false;
            self.q = action.target;
            Ok(())
        }
        fn stop(&mut self) -> Result<(), Fault> {
            self.stopped = true;
            if self.fail_stop {
                Err(Fault::Stop)
            } else {
                Ok(())
            }
        }
    }
    struct Ports {
        intents: usize,
        episodes: usize,
    }
    impl Clock for Ports {
        fn now_ms(&self) -> u64 {
            1
        }
    }
    impl Planner<2> for Ports {
        fn plan(
            &mut self,
            task: &Task<2>,
            _: &Observation<2>,
            _: Option<Review>,
        ) -> Result<[f32; 2], Fault> {
            Ok(task.target)
        }
    }
    impl Store<2> for Ports {
        fn intent(&mut self, _: &Action<2>) -> Result<(), Fault> {
            self.intents += 1;
            Ok(())
        }
        fn episode(&mut self, _: &Episode<2>, _: &Review) -> Result<(), Fault> {
            self.episodes += 1;
            Ok(())
        }
    }
    #[test]
    fn evidence_stop_and_missing_modality() {
        for (missing, fail_stop, verdict) in [
            (false, false, Verdict::Pass),
            (true, false, Verdict::Inconclusive),
            (false, true, Verdict::Inconclusive),
        ] {
            let mut body = Fixture {
                q: [0.0; 2],
                stopped: true,
                missing,
                fail_stop,
            };
            let mut planner = Ports {
                intents: 0,
                episodes: 0,
            };
            let mut store = Ports {
                intents: 0,
                episodes: 0,
            };
            let clock = Ports {
                intents: 0,
                episodes: 0,
            };
            let task = Task {
                session_id: 2,
                task_id: 3,
                body_id: 1,
                target: [0.5; 2],
                tolerance: 0.01,
                max_attempts: 2,
                timeout_ms: 100,
            };
            let result = run(&task, &mut body, &mut planner, &clock, &mut store).unwrap();
            assert_eq!(result.verdict, verdict);
            assert!(body.stopped);
            assert_eq!(store.episodes, 1);
            assert_eq!(store.intents, usize::from(!missing));
        }
    }
}
