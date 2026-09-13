import math
from itertools import pairwise

import pytest
from pydantic import ValidationError

from asset_auto.models import AssessmentRequest, ClipUsage
from asset_auto.motion_quality import analyze, important_frames, quat_delta, sample_times


def frame(time, x=0, angle=0, value=0, scale=1):
    return {"time_seconds": time, "pose": {
        "object:root": {"p": [x, 0, 0], "q": [math.cos(angle / 2), 0, 0, math.sin(angle / 2)], "s": [scale]*3},
        "morph:surface/shape": {"value": value}}}


def usage(**changes):
    return ClipUsage.model_validate(changes).model_dump()


def checks(report):
    return {item["name"]: item for item in report["checks"]}


def test_periodic_endpoint_alone_does_not_pass_velocity_or_stillness():
    samples = [frame(0), frame(.1, 1), frame(.4, 1), frame(.8, 1), frame(1)]
    report = analyze(samples, usage(playback="loop", rules={"max_still_seconds": .2, "max_linear_velocity_jump_mps": .01}))
    observed = checks(report)
    assert observed["loop_position_m"]["status"] == "passed"
    assert observed["loop_linear_velocity_jump_mps"]["status"] == "failed"
    assert observed["longest_low_activity_seconds"]["status"] == "failed"


def test_intentional_hold_is_not_a_loop_or_unwanted_stop():
    report = analyze([frame(0), frame(.5, 1), frame(1, 1), frame(2, 1)], usage(playback="hold"))
    assert not any(name.startswith("loop_") for name in checks(report))
    assert checks(report)["longest_low_activity_seconds"]["status"] == "untested"


def test_root_motion_allows_travel_but_not_scale_seam():
    samples = [frame(0), frame(.5, 1), frame(1, 2)]
    report = analyze(samples, usage(playback="loop", motion="root_motion", root_target="object:root",
                                    rules={"max_linear_velocity_jump_mps": .01}))
    assert report["numeric_status"] == "passed"
    assert report["root_motion"]["local_displacement_m"] == [2, 0, 0]
    assert report["root_motion"]["mean_displacement_speed_mps"] == 2
    samples[-1] = frame(1, 2, scale=2)
    assert checks(analyze(samples, usage(playback="loop", motion="root_motion", root_target="object:root")))["loop_scale"]["status"] == "failed"


def test_root_drift_measures_excursion_not_only_endpoint():
    report = analyze([frame(0), frame(.5, 2), frame(1)], usage(motion="in_place", root_target="object:root",
                                                         rules={"max_root_drift_m": .1}))
    assert checks(report)["root_drift_m"]["measured"] == 2
    assert checks(report)["root_drift_m"]["status"] == "failed"


def test_unknown_and_missing_roots_do_not_pass():
    assert checks(analyze([frame(0), frame(1)], usage(motion="in_place")))["root_drift_m"]["status"] == "untested"
    with pytest.raises(ValueError, match="Unknown root"):
        analyze([frame(0), frame(1)], usage(root_target="missing"))
    with pytest.raises(ValidationError):
        usage(motion="root_motion")


def test_quaternion_sign_equivalence_and_morph_loop():
    assert quat_delta([1, 0, 0, 0], [-1, 0, 0, 0]) == [0, 0, 0]
    report = analyze([frame(0), frame(.5, angle=.2), frame(1, value=.2)], usage(playback="loop"))
    assert checks(report)["loop_rotation_degrees"]["status"] == "passed"
    assert checks(report)["loop_morph"]["status"] == "failed"


def test_rotation_and_morph_activity_prevent_false_freeze():
    samples = [frame(0), frame(.25, angle=.2), frame(.5, angle=.4), frame(.75, angle=.4, value=.2)]
    report = analyze(samples, usage(rules={"max_still_seconds": .1}))
    assert checks(report)["longest_low_activity_seconds"]["measured"] == 0


def test_event_and_boundary_neighbors_are_present_without_silent_budget_clamping():
    events = [{"name": "full_extension", "time_seconds": .37}]
    times = sample_times(0, 1, 10, 30, events)
    assert .37 in times and 0 in times and 1 in times
    assert any(abs(time - .27) < 1e-9 for time in times)
    with pytest.raises(ValueError, match="budget"):
        sample_times(0, 20, 30, 100, [])
    with pytest.raises(ValueError, match="outside"):
        sample_times(0, .2, 30, 100, events)


def test_float_near_event_and_grid_do_not_create_bad_velocity_intervals():
    times = sample_times(0, 1, 30, 100, [{"name": "event", "time_seconds": .3 + 1e-16}])
    assert min(b - a for a, b in pairwise(times)) > 1e-9


def test_keyframe_selection_generalizes_to_morph_and_both_motion_extremes():
    samples = [frame(i / 10, math.sin(i * math.pi / 5), value=1 if i == 7 else 0) for i in range(11)]
    events = [{"name": "custom_event", "time_seconds": .4}]
    report = analyze(samples, usage())
    frames = important_frames(samples, events, report)
    times = {sample["time_seconds"] for sample in frames}
    assert {0, 1, .1, .9, .4, .7}.issubset(times)
    assert any(time in times for time in (.2, .3)) and any(time in times for time in (.7, .8))
    assert frames[0]["reasons"][0] == "event:custom_event"


def test_float_noise_does_not_consume_critical_extrema_budget():
    samples = [frame(i / 10, x=1e-8 * i, value=math.sin(i * math.pi / 10)) for i in range(11)]
    report = analyze(samples, usage())
    chosen = important_frames(samples, [], report)
    assert .5 in {item["time_seconds"] for item in chosen[:3]}
    assert not any("object:root" in reason for item in chosen for reason in item["reasons"])


@pytest.mark.parametrize("change", [{"sample_rate": 0}, {"max_render_frames": -1}, {"clips": ["a", "a"]},
                                   {"usage": {"clips": {"a": {"events": [{"name": "bad", "time_seconds": float('nan')} ]}}}}])
def test_assessment_rejects_invalid_limits(change):
    with pytest.raises(ValidationError):
        AssessmentRequest.model_validate({"asset_id": "asset", "revision": "r1"} | change)
def test_multiview_budget_keeps_same_moment_angles_together():
    from asset_auto.motion_quality import render_schedule

    a, b = {"time_seconds": 0}, {"time_seconds": 1}
    reports = {"walk": {"frames": [a, b]}, "wave": {"frames": [b]}}
    schedule = render_schedule(reports, ["front", "right", "back"], 7)
    assert schedule[:3] == [("walk", a, view) for view in ("front", "right", "back")]
    assert schedule[3:6] == [("wave", b, view) for view in ("front", "right", "back")]
    assert schedule[6] == ("walk", b, "front")
    assert len(render_schedule(reports, ["front", "right"], 100)) == 6
    assert render_schedule(reports, ["front"], 0) == []
    assert render_schedule({}, ["front"], 20) == []
