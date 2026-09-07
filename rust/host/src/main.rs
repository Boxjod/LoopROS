//! Offline receipt fixture, not a replacement for the Python CLI or a real LLM.
use loopros_core::agent::{Agent, Check, Config, Error, State};
fn main() {
    let mut agent = Agent::default();
    agent
        .begin(
            Config {
                session_id: 1,
                task_id: 2,
                allowed_tools: 1,
                check: Check::Tool(0),
                max_calls: 8,
                max_models: 12,
                timeout_ms: 1000,
            },
            0,
        )
        .unwrap();
    agent.request_model(1).unwrap();
    assert_eq!(agent.answer(2), Err(Error::Unverified));
    agent.request_model(3).unwrap();
    agent.propose(1, 0, 4).unwrap();
    agent.dispatch(true, true, 5).unwrap();
    agent.receipt(1, 2, 1, true, true, 6).unwrap();
    agent.request_model(7).unwrap();
    agent.answer(8).unwrap();
    assert_eq!(agent.state(), State::Complete);
    println!("{{\"fixture\":true,\"session_id\":1,\"task_id\":2,\"tool_calls\":{},\"verified\":{},\"state\":\"complete\"}}", agent.calls(), agent.verified());
}
