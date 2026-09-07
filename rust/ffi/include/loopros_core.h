#ifndef LOOPROS_CORE_H
#define LOOPROS_CORE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Initialize once, then exclusively own this context. No heap or global state.
 * Session and task IDs originate in the local app. Never resume pending tools
 * merely because a board rebooted. All timestamps are monotonic milliseconds. */
typedef struct { uint64_t storage[16]; } loop_core_context;
enum loop_core_state { LOOP_IDLE, LOOP_MODEL, LOOP_TOOL, LOOP_RECEIPT,
    LOOP_COMPLETE, LOOP_BLOCKED, LOOP_CANCELLED };
enum loop_core_error { LOOP_OK, LOOP_INVALID, LOOP_WRONG_STATE, LOOP_DEADLINE,
    LOOP_BUDGET, LOOP_PERMISSION, LOOP_IDENTITY, LOOP_UNVERIFIED,
    LOOP_TOOL_FAILED, LOOP_CLOCK, LOOP_RESOURCE, LOOP_STORAGE, LOOP_ADAPTER };
uint32_t loop_core_init(loop_core_context *);
uint32_t loop_core_begin(loop_core_context *, uint32_t session, uint32_t task,
    uint32_t allowed_tools, int32_t required_tool, uint32_t max_calls,
    uint32_t max_models, uint32_t timeout_ms, uint64_t now);
uint32_t loop_core_request_model(loop_core_context *, uint64_t now);
uint32_t loop_core_propose(loop_core_context *, uint32_t call, uint8_t tool, uint64_t now);
uint32_t loop_core_dispatch(loop_core_context *, uint8_t resources, uint8_t intent_recorded, uint64_t now);
uint32_t loop_core_receipt(loop_core_context *, uint32_t session, uint32_t task,
    uint32_t call, uint8_t ok, uint8_t checked, uint64_t now);
uint32_t loop_core_answer(loop_core_context *, uint64_t now);
void loop_core_cancel(loop_core_context *);
/* Adapter/runtime failure is blocked, distinct from an operator cancellation. */
uint32_t loop_core_fail(loop_core_context *, uint32_t error);
uint32_t loop_core_state(loop_core_context *);
uint32_t loop_core_verified(loop_core_context *);
#ifdef __cplusplus
}
#endif
#endif
