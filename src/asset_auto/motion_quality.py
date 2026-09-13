"""Motion evidence from sampled local transforms; no anatomy or style assumptions.

Pure Python so both the application and Blender can use the same analysis.
Quaternion values use Blender's (w, x, y, z) convention.
"""

import math
from itertools import pairwise


def distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


def quat_delta(a, b):
    """Shortest signed rotation vector from a to b, expressed in a's frame."""
    a = [value / math.sqrt(sum(x * x for x in a)) for value in a]
    b = [value / math.sqrt(sum(x * x for x in b)) for value in b]
    w, x, y, z = a
    v, i, j, k = b
    q = [w*v + x*i + y*j + z*k, w*i - x*v - y*k + z*j,
         w*j + x*k - y*v - z*i, w*k - x*j + y*i - z*v]
    if q[0] < 0:
        q = [-value for value in q]
    length = math.sqrt(sum(value * value for value in q[1:]))
    angle = math.degrees(2 * math.atan2(length, max(0, q[0])))
    return [value * angle / length for value in q[1:]] if length > 1e-12 else [0, 0, 0]


def pose_delta(a, b, excluded=None):
    result = {"position_m": 0.0, "rotation_degrees": 0.0, "scale": 0.0, "morph": 0.0}
    for name in a:
        left, right = a[name], b[name]
        if "value" in left:
            result["morph"] = max(result["morph"], abs(right["value"] - left["value"]))
        else:
            if name != excluded:
                result["position_m"] = max(result["position_m"], distance(left["p"], right["p"]))
                result["rotation_degrees"] = max(result["rotation_degrees"], distance(quat_delta(left["q"], right["q"]), [0, 0, 0]))
            result["scale"] = max(result["scale"], distance(left["s"], right["s"]))
    return result


def sample_times(start, end, rate, limit, events):
    if end <= start:
        raise ValueError("Motion assessment requires a positive clip duration")
    count = math.ceil((end - start) * rate) + 1
    if count > limit:
        raise ValueError("Clip exceeds sample budget; select a lower sample_rate or raise max_samples_per_clip")
    times = {start + (end - start) * index / (count - 1) for index in range(count)}
    for event in events:
        value = event["time_seconds"]
        if not start <= value <= end:
            raise ValueError(f"Event {event['name']!r} lies outside its clip")
        times.add(value)
        times.add(max(start, value - 1 / rate))
        times.add(min(end, value + 1 / rate))
    if len(times) > limit:
        raise ValueError("Event neighborhoods exceed the motion sample budget")
    # Float-near grid/event duplicates can create zero-length finite-difference
    # intervals after import. Keep one time, preferring explicit event timestamps.
    ordered, event_times = [], {event["time_seconds"] for event in events}
    epsilon = min(1e-9, (end - start) / 1000)
    for value in sorted(times):
        if ordered and value - ordered[-1] <= epsilon:
            if value in event_times or value == end:
                ordered[-1] = value
        else:
            ordered.append(value)
    return ordered


def analyze(samples, usage):
    rules = usage["rules"]
    root = usage.get("root_target")
    if root and root not in samples[0]["pose"]:
        raise ValueError(f"Unknown root_target: {root}")
    if root and "value" in samples[0]["pose"][root]:
        raise ValueError("root_target must be a transform, not a morph value")
    excluded = root if usage["motion"] == "root_motion" else None
    checks = []

    def check(name, value=None, limit=None, note=None):
        checks.append({"name": name, "status": "untested" if limit is None else "passed" if value <= limit else "failed",
                       "measured": value, "limit": limit, "note": note})

    seam = pose_delta(samples[0]["pose"], samples[-1]["pose"], excluded)
    if usage["playback"] == "loop":
        for key, rule in (("position_m", "position_tolerance_m"), ("rotation_degrees", "rotation_tolerance_degrees"),
                          ("scale", "scale_tolerance"), ("morph", "morph_tolerance")):
            check("loop_" + key, seam[key], rules[rule])
    velocities = []
    for left, right in pairwise(samples):
        dt = right["time_seconds"] - left["time_seconds"]
        delta = pose_delta(left["pose"], right["pose"], excluded)
        velocities.append({key: value / dt for key, value in delta.items()})
    still, longest, intervals = None, 0, []
    for index, speed in enumerate(velocities):
        quiet = (speed["position_m"] <= rules["still_position_speed_mps"]
                 and speed["rotation_degrees"] <= rules["still_rotation_speed_dps"]
                 and max(speed["scale"], speed["morph"]) <= rules["still_value_speed"])
        if quiet and still is None:
            still = samples[index]["time_seconds"]
        if still is not None and (not quiet or index == len(velocities) - 1):
            end = samples[index + (1 if quiet else 0)]["time_seconds"]
            longest = max(longest, end - still)
            intervals.append({"start": still, "end": end})
            still = None
    if usage["playback"] == "loop" and len(intervals) > 1 and intervals[0]["start"] == samples[0]["time_seconds"] \
            and intervals[-1]["end"] == samples[-1]["time_seconds"]:
        longest = max(longest, intervals[0]["end"] - intervals[0]["start"] + intervals[-1]["end"] - intervals[-1]["start"])
    check("longest_low_activity_seconds", longest, rules["max_still_seconds"],
          "Thresholded local transform activity; intentional holds are allowed unless a limit is supplied")
    first, second, penultimate, last = samples[0], samples[1], samples[-2], samples[-1]
    dt0, dt1 = second["time_seconds"] - first["time_seconds"], last["time_seconds"] - penultimate["time_seconds"]
    linear, angular = 0, 0
    for name, pose in first["pose"].items():
        if "value" in pose:
            continue
        poses = [item["pose"][name] for item in (first, second, penultimate, last)]
        v0 = [(b - a) / dt0 for a, b in zip(poses[0]["p"], poses[1]["p"], strict=True)]
        v1 = [(b - a) / dt1 for a, b in zip(poses[2]["p"], poses[3]["p"], strict=True)]
        linear = max(linear, distance(v0, v1))
        a0 = [value / dt0 for value in quat_delta(poses[0]["q"], poses[1]["q"])]
        a1 = [value / dt1 for value in quat_delta(poses[2]["q"], poses[3]["q"])]
        angular = max(angular, distance(a0, a1))
    if usage["playback"] == "loop":
        check("loop_linear_velocity_jump_mps", linear, rules["max_linear_velocity_jump_mps"], "One-sided finite differences")
        check("loop_angular_velocity_jump_dps", angular, rules["max_angular_velocity_jump_dps"], "One-sided local rotation differences")
    root_report = None
    if root:
        origin = first["pose"][root]["p"]
        displacement = [b - a for a, b in zip(origin, last["pose"][root]["p"], strict=True)]
        duration = last["time_seconds"] - first["time_seconds"]
        root_report = {"target": root, "local_displacement_m": displacement,
                       "mean_displacement_speed_mps": distance(displacement, [0, 0, 0]) / duration,
                       "target_speed_mps": usage.get("target_speed_mps"),
                       "space": "parent-local; not actor/world speed if ancestors are transformed"}
        drift = max(distance(origin, sample["pose"][root]["p"]) for sample in samples)
        check("root_drift_m", drift, rules["max_root_drift_m"])
    elif usage["motion"] == "in_place":
        check("root_drift_m", note="No root_target supplied; in-place policy has not been verified")
    return {"checks": checks, "loop_pose_delta": seam, "low_activity_intervals": intervals,
            "root_motion": root_report, "sample_count": len(samples),
            "numeric_status": "failed" if any(c["status"] == "failed" for c in checks) else
                              "passed" if any(c["status"] == "passed" for c in checks) else "untested",
            "scope": "Sampled local node/bone transforms and morph values; not contact, collision, mass or artistic quality"}


def important_frames(samples, events, report, rules=None):
    """Rank event neighborhoods, boundaries, activity transitions and extrema."""
    selected = {}
    rules = rules or {"position_tolerance_m": .001, "rotation_tolerance_degrees": 1,
                      "scale_tolerance": .001, "morph_tolerance": .001}
    tolerances = {"position_m": rules["position_tolerance_m"], "rotation_degrees": rules["rotation_tolerance_degrees"],
                  "scale": rules["scale_tolerance"], "morph": rules["morph_tolerance"]}

    def add(index, reason, priority=0, score=0):
        index = max(0, min(index, len(samples) - 1))
        item = selected.setdefault(index, {"reasons": [], "priority": priority, "score": score, "order": len(selected)})
        item["reasons"].append(reason)
        item["priority"], item["score"] = min(item["priority"], priority), max(item["score"], score)

    for event in events:
        index = min(range(len(samples)), key=lambda i: abs(samples[i]["time_seconds"] - event["time_seconds"]))
        add(index, "event:" + event["name"])
    for index in (0, len(samples) - 1):
        add(index, "boundary", 1)
    for index in (1, len(samples) - 2):
        add(index, "boundary_neighbor", 4)
    for event in events:
        index = min(range(len(samples)), key=lambda i: abs(samples[i]["time_seconds"] - event["time_seconds"]))
        add(index - 1, "before:" + event["name"], 2)
        add(index + 1, "after:" + event["name"], 2)
    for interval in report["low_activity_intervals"]:
        priority = 2 if any(check["name"] == "longest_low_activity_seconds" and check["status"] == "failed"
                            for check in report["checks"]) else 5
        for time in (interval["start"], interval["end"]):
            add(min(range(len(samples)), key=lambda i: abs(samples[i]["time_seconds"] - time)), "activity_transition", priority)
    # Include extrema for every changing component, not one anatomy-specific pose.
    for target, first in samples[0]["pose"].items():
        scores = [pose_delta({target: first}, {target: sample["pose"][target]}) for sample in samples]
        for component in ("position_m", "rotation_degrees", "scale", "morph"):
            index = max(range(len(scores)), key=lambda i: scores[i][component])
            significance = scores[index][component] / tolerances[component]
            if significance >= 1:
                add(index, "excursion:" + target + ":" + component, 3, significance)
        values = [[sample["pose"][target]["value"]] if "value" in first else
                  sample["pose"][target]["p"] + quat_delta(first["q"], sample["pose"][target]["q"]) + sample["pose"][target]["s"]
                  for sample in samples]
        for component in range(len(values[0])):
            minimum = min(range(len(values)), key=lambda i: values[i][component])
            maximum = max(range(len(values)), key=lambda i: values[i][component])
            threshold = rules["morph_tolerance"] if "value" in first else (
                rules["position_tolerance_m"] if component < 3 else rules["rotation_tolerance_degrees"]
                if component < 6 else rules["scale_tolerance"])
            significance = (values[maximum][component] - values[minimum][component]) / threshold
            if significance >= 1:
                add(minimum, "component_minimum:" + target, 3, significance)
                add(maximum, "component_maximum:" + target, 3, significance)
    ordered = sorted(selected.items(), key=lambda item: (item[1]["priority"],
                     -item[1]["score"] if item[1]["priority"] == 3 else item[1]["order"]))
    return [{"time_seconds": samples[i]["time_seconds"], "reasons": item["reasons"]} for i, item in ordered]


def render_schedule(reports, views, budget):
    """Allocate images by moment, then clip, with complementary views together."""
    chosen = []
    depth = 0
    while len(chosen) < budget:
        moments = [(name, report["frames"][depth]) for name, report in reports.items()
                   if len(report["frames"]) > depth]
        if not moments:
            break
        for name, frame in moments:
            for view in views:
                if len(chosen) == budget:
                    return chosen
                chosen.append((name, frame, view))
        depth += 1
    return chosen
