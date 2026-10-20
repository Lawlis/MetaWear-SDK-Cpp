#pragma once

#include "metawear/platform/cpp/concurrent_queue.h"
#include "metawear/platform/cpp/task.h"

#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>

struct AsyncCreator {
    virtual ~AsyncCreator();

    ConcurrentQueue<std::function<void (void)>> pending_fns;
    std::shared_ptr<Task> timeout;

    /**
     * Serializes a request's timeout, which fires on its own thread, against the response
     * handler, which runs on the BLE thread. Recursive because both re-enter create_next.
     */
    std::recursive_mutex mutex;

    void create_next(bool force);

    /** Marks a request as in flight; the returned token identifies it to its timeout. */
    uint64_t begin_request();
    /**
     * Claims the in-flight request for its response and cancels the timeout. Returns false
     * for a response that arrives after the request timed out, which must be dropped.
     */
    bool end_request();
    /**
     * Claims the request identified by token for its timeout. Returns false when the
     * response already claimed it.
     */
    bool expire_request(uint64_t token);

private:
    uint64_t request_token = 0;
    bool request_in_flight = false;
};
