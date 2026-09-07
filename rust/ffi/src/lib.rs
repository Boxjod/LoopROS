//! C++ board SDK boundary. The caller owns a zeroed, 8-byte aligned 128-byte
//! context, calls init once, and serializes access. No raw payload enters Rust.
#![cfg_attr(target_os = "none", no_std)]
use loopros_core::agent::{Agent, Check, Config, Error};

#[cfg(target_os = "none")]
#[panic_handler]
fn panic(_: &core::panic::PanicInfo<'_>) -> ! {
    loop {
        core::hint::spin_loop();
    }
}

const _: () = assert!(core::mem::size_of::<Agent>() <= 128 && core::mem::align_of::<Agent>() <= 8);

fn code(result: Result<(), Error>) -> u32 {
    result.err().unwrap_or(Error::None) as u32
}
unsafe fn context<'a>(ptr: *mut Agent) -> Option<&'a mut Agent> {
    if ptr.is_null() || (ptr as usize) % core::mem::align_of::<Agent>() != 0 {
        None
    } else {
        unsafe { ptr.as_mut() }
    }
}

/// # Safety
/// p points to at least 128 writable bytes aligned to 8, exclusively owned.
#[no_mangle]
pub unsafe extern "C" fn loop_core_init(p: *mut Agent) -> u32 {
    if p.is_null() || (p as usize) % 8 != 0 {
        return Error::Invalid as u32;
    }
    unsafe {
        p.write(Agent::default());
    }
    0
}

/// # Safety
/// All context functions require a live initialized exclusive context from init.
#[no_mangle]
pub unsafe extern "C" fn loop_core_begin(
    p: *mut Agent,
    session: u32,
    task: u32,
    allowed: u32,
    required_tool: i32,
    max_calls: u32,
    max_models: u32,
    timeout_ms: u32,
    now: u64,
) -> u32 {
    let Some(a) = (unsafe { context(p) }) else {
        return Error::Invalid as u32;
    };
    let check = match required_tool {
        -1 => Check::Conversation,
        0..=31 => Check::Tool(required_tool as u8),
        _ => return Error::Invalid as u32,
    };
    code(a.begin(
        Config {
            session_id: session,
            task_id: task,
            allowed_tools: allowed,
            check,
            max_calls,
            max_models,
            timeout_ms,
        },
        now,
    ))
}

macro_rules! action {
    ($name:ident($($arg:ident:$typ:ty),*) => $method:ident($($value:expr),*)) => {
        /// # Safety
        /// p must be initialized by loop_core_init, valid and exclusively owned.
        #[no_mangle]
        pub unsafe extern "C" fn $name(p: *mut Agent, $($arg:$typ),*) -> u32 {
            let Some(a) = (unsafe { context(p) }) else { return Error::Invalid as u32; };
            code(a.$method($($value),*))
        }
    };
}
action!(loop_core_request_model(now:u64) => request_model(now));
action!(loop_core_propose(call:u32,tool:u8,now:u64) => propose(call,tool,now));
action!(loop_core_dispatch(resources:u8,recorded:u8,now:u64) => dispatch(resources == 1,recorded == 1,now));
action!(loop_core_receipt(session:u32,task:u32,call:u32,ok:u8,checked:u8,now:u64) => receipt(session,task,call,ok == 1,checked == 1,now));
action!(loop_core_answer(now:u64) => answer(now));

/// # Safety
/// p must be initialized by loop_core_init, valid and exclusively owned.
#[no_mangle]
pub unsafe extern "C" fn loop_core_cancel(p: *mut Agent) {
    if let Some(a) = unsafe { context(p) } {
        a.cancel();
    }
}
/// # Safety
/// p must be initialized by loop_core_init, valid and exclusively owned.
#[no_mangle]
pub unsafe extern "C" fn loop_core_fail(p: *mut Agent, error: u32) -> u32 {
    let Some(a) = (unsafe { context(p) }) else {
        return Error::Invalid as u32;
    };
    let error = match error {
        3 => Error::Deadline,
        4 => Error::Budget,
        5 => Error::Permission,
        6 => Error::Identity,
        7 => Error::Unverified,
        8 => Error::ToolFailed,
        9 => Error::Clock,
        10 => Error::Resource,
        11 => Error::Storage,
        12 => Error::Adapter,
        _ => Error::Invalid,
    };
    code(a.abort(error))
}
/// # Safety
/// p must be initialized by loop_core_init, valid and exclusively owned.
#[no_mangle]
pub unsafe extern "C" fn loop_core_state(p: *mut Agent) -> u32 {
    unsafe { context(p) }.map_or(u32::MAX, |a| a.state() as u32)
}
/// # Safety
/// p must be initialized by loop_core_init, valid and exclusively owned.
#[no_mangle]
pub unsafe extern "C" fn loop_core_verified(p: *mut Agent) -> u32 {
    unsafe { context(p) }.map_or(0, |a| u32::from(a.verified()))
}
