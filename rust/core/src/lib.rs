//! Allocation-free execution kernel. Transports, model JSON, storage and device
//! drivers live in adapters. An assistant answer never establishes task success.
#![no_std]
#![forbid(unsafe_code)]

pub mod agent;
pub mod robotics;

/// Host/MCU adapters use the one resource authority for their runtime. A Linux
/// adapter must delegate to App.resources rather than keep another lease ledger.
pub trait Resources {
    type Lease;
    fn acquire(&mut self) -> Option<Self::Lease>;
    fn release(&mut self, lease: Self::Lease);
}

/// Persistence policy is external: RAM ring, flash, or the host event store.
pub trait Evidence {
    fn append(&mut self, event: Event) -> bool;
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Event {
    pub session_id: u32,
    pub task_id: u32,
    pub call_id: u32,
    pub kind: EventKind,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum EventKind {
    Intent,
    Receipt,
    Rejected,
    Cancelled,
}
