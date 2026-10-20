#include "async_creator.h"

AsyncCreator::~AsyncCreator() {
    if (timeout.use_count()) {
        timeout->cancel();
    }
}

void AsyncCreator::create_next(bool force) {
    std::lock_guard<std::recursive_mutex> lock(mutex);

    if (force && !pending_fns.empty()) {
        pending_fns.pop();
    }
    if ((force && !pending_fns.empty()) || (!force && pending_fns.size() == 1)) {
        pending_fns.front()();
    }
}

uint64_t AsyncCreator::begin_request() {
    std::lock_guard<std::recursive_mutex> lock(mutex);
    request_in_flight = true;
    return ++request_token;
}

bool AsyncCreator::end_request() {
    std::lock_guard<std::recursive_mutex> lock(mutex);
    if (!request_in_flight) {
        return false;
    }
    request_in_flight = false;
    if (timeout) {
        timeout->cancel();
    }
    return true;
}

bool AsyncCreator::expire_request(uint64_t token) {
    std::lock_guard<std::recursive_mutex> lock(mutex);
    if (!request_in_flight || token != request_token) {
        return false;
    }
    request_in_flight = false;
    return true;
}

bool AsyncCreator::request_active() {
    std::lock_guard<std::recursive_mutex> lock(mutex);
    return request_in_flight;
}
