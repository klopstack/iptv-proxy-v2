/**
 * Client helpers for the standardized admin API contract (TODO 73).
 */

export function parseDataResponse(payload) {
    if (payload !== null && typeof payload === 'object' && Object.prototype.hasOwnProperty.call(payload, 'data')) {
        return payload.data;
    }
    return payload;
}

export function unwrapData(payload) {
    return parseDataResponse(payload);
}

export function parseMutationResponse(payload) {
    if (payload !== null && typeof payload === 'object' && payload.success === true) {
        if (Object.prototype.hasOwnProperty.call(payload, 'data')) {
            return payload.data;
        }
        return payload;
    }
    return payload;
}

export function unwrapMutation(payload) {
    return parseMutationResponse(payload);
}

export function errorMessageFromPayload(payload) {
    if (payload === null || typeof payload !== 'object') {
        return 'Request failed';
    }
    if (typeof payload.error === 'string' && payload.error) {
        return payload.error;
    }
    if (typeof payload.message === 'string' && payload.message) {
        return payload.message;
    }
    return 'Request failed';
}
