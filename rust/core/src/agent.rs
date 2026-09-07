//! A bounded, cooperative model -> tool -> receipt loop. Identities and policy
//! originate in the application, never from a model or pasted history.

#[repr(u32)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum State {
    Idle = 0,
    Model = 1,
    Tool = 2,
    Receipt = 3,
    Complete = 4,
    Blocked = 5,
    Cancelled = 6,
}

#[repr(u32)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Error {
    None = 0,
    Invalid = 1,
    State = 2,
    Deadline = 3,
    Budget = 4,
    Permission = 5,
    Identity = 6,
    Unverified = 7,
    ToolFailed = 8,
    Clock = 9,
    Resource = 10,
    Storage = 11,
    Adapter = 12,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Check {
    Conversation,
    Tool(u8),
}

/// Fixed storage; no credential, prompt or tool payload is copied into the
/// kernel. Adapters own their bounded message history and raw receipts.
#[derive(Clone, Copy, Debug)]
pub struct Agent {
    pub(crate) state: State,
    pub(crate) error: Error,
    session: u32,
    task: u32,
    allowed: u32,
    check: Check,
    verified: bool,
    deadline: u64,
    last_time: u64,
    max_calls: u32,
    max_models: u32,
    calls: u32,
    models: u32,
    call_id: u32,
    tool: u8,
}

impl Default for Agent {
    fn default() -> Self {
        Self {
            state: State::Idle,
            error: Error::None,
            session: 0,
            task: 0,
            allowed: 0,
            check: Check::Conversation,
            verified: false,
            deadline: 0,
            last_time: 0,
            max_calls: 0,
            max_models: 0,
            calls: 0,
            models: 0,
            call_id: 0,
            tool: 0,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Config {
    pub session_id: u32,
    pub task_id: u32,
    pub allowed_tools: u32,
    pub check: Check,
    pub max_calls: u32,
    pub max_models: u32,
    pub timeout_ms: u32,
}

impl Agent {
    pub fn state(&self) -> State {
        self.state
    }
    pub fn error(&self) -> Error {
        self.error
    }
    pub fn verified(&self) -> bool {
        self.verified
    }
    pub fn active_call(&self) -> u32 {
        self.call_id
    }
    pub fn calls(&self) -> u32 {
        self.calls
    }
    pub fn models(&self) -> u32 {
        self.models
    }
    pub fn identities(&self) -> (u32, u32) {
        (self.session, self.task)
    }

    pub fn begin(&mut self, config: Config, now: u64) -> Result<(), Error> {
        if matches!(self.state, State::Model | State::Tool | State::Receipt) {
            return Err(Error::State);
        }
        if config.session_id == 0
            || config.task_id == 0
            || config.timeout_ms == 0
            || config.max_models == 0
            || config.max_calls == 0
        {
            return Err(Error::Invalid);
        }
        if let Check::Tool(tool) = config.check {
            if tool >= 32 || config.allowed_tools & (1u32 << tool) == 0 {
                return Err(Error::Invalid);
            }
        }
        let deadline = now
            .checked_add(u64::from(config.timeout_ms))
            .ok_or(Error::Invalid)?;
        *self = Self {
            state: State::Model,
            session: config.session_id,
            task: config.task_id,
            allowed: config.allowed_tools,
            check: config.check,
            deadline,
            last_time: now,
            max_calls: config.max_calls,
            max_models: config.max_models,
            ..Self::default()
        };
        Ok(())
    }

    pub fn abort(&mut self, error: Error) -> Result<(), Error> {
        self.state = State::Blocked;
        self.error = error;
        self.verified = false;
        Err(error)
    }

    fn tick(&mut self, now: u64) -> Result<(), Error> {
        if now < self.last_time {
            return self.abort(Error::Clock);
        }
        self.last_time = now;
        if now >= self.deadline {
            return self.abort(Error::Deadline);
        }
        Ok(())
    }

    /// Call once immediately before each model request, including a continuation.
    pub fn request_model(&mut self, now: u64) -> Result<(), Error> {
        if self.state != State::Model {
            return Err(Error::State);
        }
        self.tick(now)?;
        if self.models >= self.max_models {
            return self.abort(Error::Budget);
        }
        self.models += 1;
        Ok(())
    }

    pub fn propose(&mut self, call: u32, tool: u8, now: u64) -> Result<(), Error> {
        if self.state != State::Model || self.models == 0 {
            return Err(Error::State);
        }
        self.tick(now)?;
        if call == 0 || call <= self.call_id {
            return self.abort(Error::Identity);
        }
        if tool >= 32 || self.allowed & (1u32 << tool) == 0 {
            return self.abort(Error::Permission);
        }
        if self.calls >= self.max_calls {
            return self.abort(Error::Budget);
        }
        self.call_id = call;
        self.tool = tool;
        self.state = State::Tool;
        Ok(())
    }

    /// Resource admission and durable intent recording precede dispatch. Call
    /// only with locally observed adapter results, never model-supplied booleans.
    pub fn dispatch(
        &mut self,
        resources: bool,
        intent_recorded: bool,
        now: u64,
    ) -> Result<(), Error> {
        if self.state != State::Tool {
            return Err(Error::State);
        }
        self.tick(now)?;
        if !resources {
            return Err(Error::Resource);
        }
        if !intent_recorded {
            return self.abort(Error::Storage);
        }
        self.calls += 1;
        self.state = State::Receipt;
        Ok(())
    }

    /// A driver returns ok after inspecting its actual result; checked means
    /// the application's acceptance predicate passed on that same receipt.
    pub fn receipt(
        &mut self,
        session: u32,
        task: u32,
        call: u32,
        ok: bool,
        checked: bool,
        now: u64,
    ) -> Result<(), Error> {
        if self.state != State::Receipt {
            return Err(Error::State);
        }
        if (session, task, call) != (self.session, self.task, self.call_id) {
            return Err(Error::Identity);
        }
        self.tick(now)?;
        if !ok {
            self.verified = false;
            self.error = Error::ToolFailed;
        } else {
            self.error = Error::None;
            if self.check == Check::Tool(self.tool) {
                self.verified = checked;
            }
        }
        self.state = State::Model;
        Ok(())
    }

    pub fn answer(&mut self, now: u64) -> Result<(), Error> {
        if self.state != State::Model || self.models == 0 {
            return Err(Error::State);
        }
        self.tick(now)?;
        if self.check != Check::Conversation && !self.verified {
            self.error = Error::Unverified;
            // Continue in this turn; a failed check does not authorize new tools.
            return Err(Error::Unverified);
        }
        self.state = State::Complete;
        self.error = Error::None;
        Ok(())
    }

    pub fn cancel(&mut self) {
        if matches!(self.state, State::Model | State::Tool | State::Receipt) {
            self.state = State::Cancelled;
            self.verified = false;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn agent() -> Agent {
        let mut a = Agent::default();
        a.begin(
            Config {
                session_id: 11,
                task_id: 23,
                allowed_tools: 3,
                check: Check::Tool(0),
                max_calls: 12,
                max_models: 20,
                timeout_ms: 1000,
            },
            0,
        )
        .unwrap();
        a
    }
    #[test]
    fn prose_is_not_task_success() {
        let mut a = agent();
        a.request_model(1).unwrap();
        assert_eq!(a.answer(2), Err(Error::Unverified));
        assert_eq!(a.state(), State::Model);
        a.request_model(3).unwrap();
        a.propose(1, 0, 4).unwrap();
        a.dispatch(true, true, 5).unwrap();
        a.receipt(11, 23, 1, true, true, 6).unwrap();
        a.request_model(7).unwrap();
        a.answer(8).unwrap();
        assert!(a.verified());
        assert_eq!(a.state(), State::Complete);
    }
    #[test]
    fn mismatched_and_duplicate_receipts_cannot_finish() {
        let mut a = agent();
        a.request_model(1).unwrap();
        a.propose(1, 0, 2).unwrap();
        a.dispatch(true, true, 3).unwrap();
        assert_eq!(a.receipt(11, 99, 1, true, true, 4), Err(Error::Identity));
        assert_eq!(a.state(), State::Receipt);
        a.receipt(11, 23, 1, false, true, 5).unwrap();
        assert_eq!(a.receipt(11, 23, 1, true, true, 6), Err(Error::State));
        assert!(!a.verified());
        assert_eq!(a.propose(1, 0, 6), Err(Error::Identity));
    }
    #[test]
    fn permission_and_missing_intent_prevent_dispatch() {
        let mut a = agent();
        a.request_model(1).unwrap();
        assert_eq!(a.propose(1, 5, 2), Err(Error::Permission));
        assert_eq!(a.calls(), 0);
        let mut a = agent();
        a.request_model(1).unwrap();
        a.propose(1, 0, 2).unwrap();
        assert_eq!(a.dispatch(false, true, 3), Err(Error::Resource));
        assert_eq!(a.dispatch(true, false, 4), Err(Error::Storage));
        assert_eq!(a.calls(), 0);
    }
    #[test]
    fn bounded_continuation_and_deadline() {
        let mut a = agent();
        for i in 1..=20 {
            a.request_model(i).unwrap();
        }
        assert_eq!(a.request_model(21), Err(Error::Budget));
        let mut a = agent();
        assert_eq!(a.request_model(1000), Err(Error::Deadline));
        let mut a = agent();
        a.request_model(20).unwrap();
        assert_eq!(a.propose(1, 0, 19), Err(Error::Clock));
    }
    #[test]
    fn cancellation_cannot_be_overridden_by_late_receipt() {
        let mut a = agent();
        a.request_model(1).unwrap();
        a.propose(1, 0, 2).unwrap();
        a.dispatch(true, true, 3).unwrap();
        a.cancel();
        assert_eq!(a.receipt(11, 23, 1, true, true, 4), Err(Error::State));
        assert_eq!(a.state(), State::Cancelled);
    }
    #[test]
    fn conversation_and_active_identity_remain_distinct() {
        let mut a = Agent::default();
        let config = Config {
            session_id: 8,
            task_id: 9,
            allowed_tools: 0,
            check: Check::Conversation,
            max_calls: 1,
            max_models: 2,
            timeout_ms: 100,
        };
        a.begin(config, 0).unwrap();
        assert_eq!(
            a.begin(
                Config {
                    task_id: 10,
                    ..config
                },
                1
            ),
            Err(Error::State)
        );
        assert_eq!(a.identities(), (8, 9));
        a.request_model(1).unwrap();
        a.answer(2).unwrap();
        assert_eq!(a.state(), State::Complete);
        assert!(!a.verified());
    }
    #[test]
    fn more_than_four_calls_and_latest_failure_invalidates_check() {
        let mut a = agent();
        for i in 1..=12 {
            a.request_model(u64::from(i)).unwrap();
            a.propose(i, 0, u64::from(i)).unwrap();
            a.dispatch(true, true, u64::from(i)).unwrap();
            a.receipt(11, 23, i, i != 12, true, u64::from(i)).unwrap();
        }
        assert_eq!(a.calls(), 12);
        assert!(!a.verified());
        a.request_model(20).unwrap();
        assert_eq!(a.propose(13, 0, 21), Err(Error::Budget));
    }
}
