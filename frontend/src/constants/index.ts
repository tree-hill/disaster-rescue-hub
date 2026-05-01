// 与 backend/app/core/constants.py 保持同步

export const W1_DISTANCE = 0.4;
export const W2_BATTERY = 0.2;
export const W3_CAPABILITY = 0.3;
export const W4_LOAD = 0.1;

export const VISION_BOOST_FACTOR = 1.5;
export const VISION_BOOST_DISTANCE_THRESHOLD_M = 200;
export const VISION_BOOST_CONFIDENCE_THRESHOLD = 0.8;

export const MAX_BIDDING_DISTANCE_KM = 10.0;
export const MIN_BATTERY_PCT_DEFAULT = 20.0;
export const MAX_LOAD_PER_ROBOT = 3;

export const NFR_STATE_PUSH_LATENCY_MS = 500;
export const NFR_DISPATCH_DECISION_LATENCY_MS = 2000;
export const NFR_YOLO_INFERENCE_LATENCY_MS = 100;

export const MAX_RECONNECT = 5;
