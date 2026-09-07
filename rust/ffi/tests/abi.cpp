#include "loopros_core.h"
#include <cassert>
#include <iostream>
int main() {
    loop_core_context state{};
    assert(loop_core_init(&state) == LOOP_OK);
    assert(loop_core_begin(&state, 1, 2, 1, 0, 8, 12, 1000, 0) == LOOP_OK);
    assert(loop_core_request_model(&state, 1) == LOOP_OK);
    assert(loop_core_answer(&state, 2) == LOOP_UNVERIFIED);
    for (uint32_t i = 1; i <= 5; ++i) {
        assert(loop_core_request_model(&state, 3*i) == LOOP_OK);
        assert(loop_core_propose(&state, i, 0, 3*i) == LOOP_OK);
        assert(loop_core_dispatch(&state, 0, 1, 3*i) == LOOP_RESOURCE);
        assert(loop_core_dispatch(&state, 1, 1, 3*i) == LOOP_OK);
        assert(loop_core_receipt(&state, 1, 99, i, 1, 1, 3*i) == LOOP_IDENTITY);
        assert(loop_core_receipt(&state, 1, 2, i, 1, 1, 3*i) == LOOP_OK);
    }
    assert(loop_core_request_model(&state, 20) == LOOP_OK);
    assert(loop_core_answer(&state, 21) == LOOP_OK);
    assert(loop_core_state(&state) == LOOP_COMPLETE);
    assert(loop_core_verified(&state) == 1);
    assert(loop_core_begin(&state, 1, 3, 1, 0, 8, 12, 1000, 30) == LOOP_OK);
    loop_core_cancel(&state);
    assert(loop_core_state(&state) == LOOP_CANCELLED);
    assert(loop_core_receipt(&state, 1, 2, 5, 1, 1, 31) == LOOP_WRONG_STATE);
    assert(loop_core_begin(&state, 1, 4, 1, 0, 8, 12, 1000, 40) == LOOP_OK);
    assert(loop_core_fail(&state, LOOP_ADAPTER) == LOOP_ADAPTER);
    assert(loop_core_state(&state) == LOOP_BLOCKED);
    std::cout << "C++/Rust ABI: 5 calls, identities, admission, completion and cancellation passed\n";
}
