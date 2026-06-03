from __future__ import annotations

import random
import threading
import time
from math import sqrt

import numpy as np

from scanput import (
    KEY_ALIASES,
    get_cursor_position,
    key_down,
    key_up,
    left_down,
    left_up,
    right_down,
    right_up,
    set_cursor_position,
)

__all__ = [
    "KEY_ALIASES",
    "bezier_curve",
    "clamped_gauss_randint",
    "clamped_gauss_randfloat",
    "lagged_left_click",
    "lagged_press_key",
    "lagged_right_click",
    "left_click",
    "left_down",
    "left_up",
    "modifier_key_press",
    "modifier_left_click",
    "modifier_right_click",
    "move_mouse",
    "press_key",
    "randomize_coordinate_within_range",
    "randomize_coordinate_within_square",
    "right_click",
    "right_down",
    "right_up",
    "rsleep",
    "set_cursor_position",
    "start_jitter",
    "stop_jitter",
]

_mouse_lock = threading.Lock()
_jitter_stop_event = threading.Event()
_jitter_thread: threading.Thread | None = None


# Reference: https://en.wikipedia.org/wiki/B%C3%A9zier_curve#Quadratic_curves
def bezier_curve(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, steps: int) -> np.ndarray:
    """Generate a quadratic Bezier curve through p0, p1, p2 with the given number of steps."""
    t_values = np.linspace(0, 1, steps)
    curve = np.array([
        (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2
        for t in t_values
    ])
    return curve


def clamped_gauss_randint(min_int: int, max_int: int, sigmas_to_edge: float = 3, bias: float = 0.0) -> int:
    if min_int > max_int:
        raise ValueError("empty range for clamped_gauss_randint()")
    return int(round(clamped_gauss_randfloat(min_int, max_int, sigmas_to_edge, bias)))


def clamped_gauss_randfloat(min_val: float, max_val: float, sigmas_to_edge: float = 3, bias: float = 0.0) -> float:
    half_range = (max_val - min_val) / 2
    mean = (min_val + max_val) / 2 + bias * half_range
    std_dev = half_range / sigmas_to_edge

    # Old method - clamps outliers to edge, causes detectable edge spikes.
    # value = random.gauss(mean, std_dev)
    # value = max(min_val, min(max_val, value))

    value = random.gauss(mean, std_dev)
    while not (min_val <= value <= max_val):
        value = random.gauss(mean, std_dev)

    return value


def randomize_coordinate_within_range(
    x: int, y: int,
    radius_x: int, radius_y: int,
    sigmas_to_edge_x: float = 3, sigmas_to_edge_y: float = 3,
    bias_x: float = 0.0, bias_y: float = 0.0,
) -> tuple[int, int]:
    randomized_x = clamped_gauss_randint(x - radius_x, x + radius_x, sigmas_to_edge=sigmas_to_edge_x, bias=bias_x)
    randomized_y = clamped_gauss_randint(y - radius_y, y + radius_y, sigmas_to_edge=sigmas_to_edge_y, bias=bias_y)
    return randomized_x, randomized_y


# Less typing for when X == Y.
def randomize_coordinate_within_square(
    x: int, y: int, radius: int,
    sigmas_to_edge: float = 3,
    bias_x: float = 0.0, bias_y: float = 0.0,
) -> tuple[int, int]:
    return randomize_coordinate_within_range(
        x, y, radius, radius,
        sigmas_to_edge_x=sigmas_to_edge, sigmas_to_edge_y=sigmas_to_edge,
        bias_x=bias_x, bias_y=bias_y,
    )


def _do_jitter_action() -> None:
    x, y = get_cursor_position()

    action = random.choices(['tiny', 'nudge', 'burst'], weights=[25, 45, 30])[0]

    if action == 'tiny':
        set_cursor_position(x + random.choice([-1, 0, 1]), y + random.choice([-1, 0, 1]))

    elif action == 'nudge':
        set_cursor_position(x + random.randint(-2, 2), y + random.randint(-2, 2))

    elif action == 'burst':
        num_moves = random.randint(2, 3)
        dir_x = random.choice([-1, 1])
        dir_y = random.choice([-1, 1])
        for i in range(num_moves):
            x += dir_x + random.randint(-1, 1)
            y += dir_y + random.randint(-1, 1)
            set_cursor_position(x, y)
            if i < num_moves - 1:
                time.sleep(clamped_gauss_randfloat(0.03, 0.08))


def _jitter_worker() -> None:
    while not _jitter_stop_event.wait(timeout=clamped_gauss_randfloat(0.4, 1.2)):
        if random.random() < 0.65:
            with _mouse_lock:
                _do_jitter_action()


def start_jitter() -> None:
    global _jitter_thread
    _jitter_stop_event.clear()
    if _jitter_thread is None or not _jitter_thread.is_alive():
        _jitter_thread = threading.Thread(target=_jitter_worker, daemon=True)
        _jitter_thread.start()


def stop_jitter() -> None:
    global _jitter_thread
    _jitter_stop_event.set()
    if _jitter_thread is not None:
        _jitter_thread.join(timeout=2.0)
        _jitter_thread = None


def move_mouse(
    dest_x: int, dest_y: int,
    speed_multiplier: float = 1.0,
    mouse_hz: int = 500,
    speed_sigmas_to_edge: float = 3,
    speed_bias: float = 0.0,
) -> None:
    """Move the mouse to (dest_x, dest_y) using human-like Bezier motion with overshoot."""

    with _mouse_lock:
        start_x, start_y = get_cursor_position()

        distance = sqrt((dest_x - start_x) ** 2 + (dest_y - start_y) ** 2)

        curve_direction = random.choice([-1, 1])
        mid_x = (start_x + dest_x) // 2
        # Scale the arc offset with distance — a fixed offset on a short move produces
        # a comically exaggerated U-shape relative to the actual travel distance.
        curve_offset = clamped_gauss_randint(
            max(5, int(distance * 0.05)),
            max(10, min(150, int(distance * 0.35))),
        )
        mid_y = ((start_y + dest_y) // 2) + (curve_direction * curve_offset)

        full_curve = bezier_curve(
            np.array([start_x, start_y]),
            np.array([mid_x, mid_y]),
            np.array([dest_x, dest_y]),
            steps=1000,
        )

        last_point = full_curve[-1]
        prev_point = full_curve[-5]
        movement_angle = np.arctan2(last_point[1] - prev_point[1], last_point[0] - prev_point[0])
        overshoot_magnitude = clamped_gauss_randfloat(0.3 * sqrt(distance), 0.8 * sqrt(distance))
        overshoot_x = dest_x + (overshoot_magnitude * np.cos(movement_angle))
        overshoot_y = dest_y + (overshoot_magnitude * np.sin(movement_angle))

        if distance < 75:
            num_subcurves = 1
        else:
            curve_bias = max(-1.0, min(1.0, distance / 1000.0 - 1.0))
            num_subcurves = clamped_gauss_randint(1, 3, bias=curve_bias)

        if num_subcurves == 1:
            segment_points = [full_curve[0], np.array([overshoot_x, overshoot_y])]
        else:
            indices = sorted(random.sample(range(100, 900), num_subcurves - 1))
            segment_points = [full_curve[0]] + [full_curve[i] for i in indices] + [np.array([overshoot_x, overshoot_y])]

        # For speed normalization. If someone wants to pass 125 hz for example, they will be 4x slower.
        # Therefore, we divide total steps by the ratio of default hz to user-defined hz.
        default_hz = 500
        hz_normalization_multiplier = mouse_hz / default_hz

        # Total amount of points along the entire multi-curve path. Less steps = higher speed.
        total_steps = int(round(clamped_gauss_randint(42, 67, sigmas_to_edge=speed_sigmas_to_edge, bias=speed_bias) / speed_multiplier * hz_normalization_multiplier))
        sub_steps = [total_steps // num_subcurves] * num_subcurves

        for i in range(total_steps % num_subcurves):
            sub_steps[i] += 1

        sub_curves = []
        for i in range(len(segment_points) - 1):
            p0 = segment_points[i]
            p2 = segment_points[i + 1]
            p1 = np.array([(p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2]) + random.randint(-20, 20)
            sub_curves.append(bezier_curve(p0, p1, p2, steps=sub_steps[i]))

        refresh_rate = 1 / mouse_hz
        for sub_curve in sub_curves:
            for point in sub_curve:
                set_cursor_position(point[0], point[1])
                time.sleep(refresh_rate)

        rsleep(0.015, 0.04)

        correction_steps = clamped_gauss_randint(3, 6)
        p0 = np.array([overshoot_x, overshoot_y])
        p2 = np.array([dest_x, dest_y], dtype=float)
        correction_curve = bezier_curve(p0, (p0 + p2) / 2, p2, steps=correction_steps)
        for point in correction_curve:
            set_cursor_position(point[0], point[1])
            time.sleep(refresh_rate)


def left_click(sigmas_to_edge: float = 3, bias: float = 0.0) -> None:
    hold_time = clamped_gauss_randfloat(0.05, 0.12, sigmas_to_edge=sigmas_to_edge, bias=bias)
    left_down()
    time.sleep(hold_time)
    left_up()


def right_click(sigmas_to_edge: float = 3, bias: float = 0.0) -> None:
    hold_time = clamped_gauss_randfloat(0.05, 0.12, sigmas_to_edge=sigmas_to_edge, bias=bias)
    right_down()
    time.sleep(hold_time)
    right_up()


def press_key(key: str | int, sigmas_to_edge: float = 3, bias: float = 0.0) -> None:
    hold_time = clamped_gauss_randfloat(0.04, 0.10, sigmas_to_edge=sigmas_to_edge, bias=bias)
    key_down(key)
    time.sleep(hold_time)
    key_up(key)


def rsleep(min_time: float, max_time: float | None = None, sigmas_to_edge: float = 3, bias: float = 0.0) -> None:
    if max_time is None:
        max_time = min_time * 1.4
    time.sleep(clamped_gauss_randfloat(min_time, max_time, sigmas_to_edge=sigmas_to_edge, bias=bias))


def lagged_left_click(
    prelag: float | tuple[float, float] | None = 0.1,
    postlag: float | tuple[float, float] | None = 0.1,
    sigmas_to_edge: float = 3, bias: float = 0.0,
    prelag_sigmas_to_edge: float = 3, prelag_bias: float = 0.0,
    postlag_sigmas_to_edge: float = 3, postlag_bias: float = 0.0,
) -> None:
    if prelag is not None:
        if isinstance(prelag, tuple):
            rsleep(prelag[0], prelag[1], sigmas_to_edge=prelag_sigmas_to_edge, bias=prelag_bias)
        else:
            rsleep(prelag, prelag + 0.1, sigmas_to_edge=prelag_sigmas_to_edge, bias=prelag_bias)

    left_click(sigmas_to_edge=sigmas_to_edge, bias=bias)

    if postlag is not None:
        if isinstance(postlag, tuple):
            rsleep(postlag[0], postlag[1], sigmas_to_edge=postlag_sigmas_to_edge, bias=postlag_bias)
        else:
            rsleep(postlag, postlag + 0.1, sigmas_to_edge=postlag_sigmas_to_edge, bias=postlag_bias)


def lagged_right_click(
    prelag: float | tuple[float, float] | None = 0.1,
    postlag: float | tuple[float, float] | None = 0.1,
    sigmas_to_edge: float = 3, bias: float = 0.0,
    prelag_sigmas_to_edge: float = 3, prelag_bias: float = 0.0,
    postlag_sigmas_to_edge: float = 3, postlag_bias: float = 0.0,
) -> None:
    if prelag is not None:
        if isinstance(prelag, tuple):
            rsleep(prelag[0], prelag[1], sigmas_to_edge=prelag_sigmas_to_edge, bias=prelag_bias)
        else:
            rsleep(prelag, prelag + 0.1, sigmas_to_edge=prelag_sigmas_to_edge, bias=prelag_bias)

    right_click(sigmas_to_edge=sigmas_to_edge, bias=bias)

    if postlag is not None:
        if isinstance(postlag, tuple):
            rsleep(postlag[0], postlag[1], sigmas_to_edge=postlag_sigmas_to_edge, bias=postlag_bias)
        else:
            rsleep(postlag, postlag + 0.1, sigmas_to_edge=postlag_sigmas_to_edge, bias=postlag_bias)


def modifier_left_click(
    modifier: str | list[str],
    min_time: float = 0.03,
    max_time: float = 0.08,
    sigmas_to_edge: float = 3,
    bias: float = 0.0,
) -> None:
    modifiers = [modifier] if isinstance(modifier, str) else list(modifier)
    if len(modifiers) > 3:
        raise ValueError("modifier_left_click() accepts at most 3 modifier keys")
    for mod in modifiers:
        key_down(mod)
        rsleep(min_time, max_time, sigmas_to_edge=sigmas_to_edge, bias=bias)
    left_click()
    rsleep(min_time, max_time, sigmas_to_edge=sigmas_to_edge, bias=bias)
    for mod in reversed(modifiers):
        key_up(mod)
        rsleep(min_time, max_time, sigmas_to_edge=sigmas_to_edge, bias=bias)


def modifier_right_click(
    modifier: str | list[str],
    min_time: float = 0.03,
    max_time: float = 0.08,
    sigmas_to_edge: float = 3,
    bias: float = 0.0,
) -> None:
    modifiers = [modifier] if isinstance(modifier, str) else list(modifier)
    if len(modifiers) > 3:
        raise ValueError("modifier_right_click() accepts at most 3 modifier keys")
    for mod in modifiers:
        key_down(mod)
        rsleep(min_time, max_time, sigmas_to_edge=sigmas_to_edge, bias=bias)
    right_click()
    rsleep(min_time, max_time, sigmas_to_edge=sigmas_to_edge, bias=bias)
    for mod in reversed(modifiers):
        key_up(mod)
        rsleep(min_time, max_time, sigmas_to_edge=sigmas_to_edge, bias=bias)


def modifier_key_press(
    key: str | int,
    modifier: str | list[str],
    min_time: float = 0.03,
    max_time: float = 0.08,
    sigmas_to_edge: float = 3,
    bias: float = 0.0,
) -> None:
    modifiers = [modifier] if isinstance(modifier, str) else list(modifier)
    if len(modifiers) > 3:
        raise ValueError("modifier_key_press() accepts at most 3 modifier keys")
    for mod in modifiers:
        key_down(mod)
        rsleep(min_time, max_time, sigmas_to_edge=sigmas_to_edge, bias=bias)
    press_key(key)
    rsleep(min_time, max_time, sigmas_to_edge=sigmas_to_edge, bias=bias)
    for mod in reversed(modifiers):
        key_up(mod)
        rsleep(min_time, max_time, sigmas_to_edge=sigmas_to_edge, bias=bias)


def lagged_press_key(
    key: str | int,
    prelag: float | tuple[float, float] | None = 0.1,
    postlag: float | tuple[float, float] | None = 0.1,
    sigmas_to_edge: float = 3, bias: float = 0.0,
    prelag_sigmas_to_edge: float = 3, prelag_bias: float = 0.0,
    postlag_sigmas_to_edge: float = 3, postlag_bias: float = 0.0,
) -> None:
    if prelag is not None:
        if isinstance(prelag, tuple):
            rsleep(prelag[0], prelag[1], sigmas_to_edge=prelag_sigmas_to_edge, bias=prelag_bias)
        else:
            rsleep(prelag, prelag + 0.1, sigmas_to_edge=prelag_sigmas_to_edge, bias=prelag_bias)

    press_key(key, sigmas_to_edge=sigmas_to_edge, bias=bias)

    if postlag is not None:
        if isinstance(postlag, tuple):
            rsleep(postlag[0], postlag[1], sigmas_to_edge=postlag_sigmas_to_edge, bias=postlag_bias)
        else:
            rsleep(postlag, postlag + 0.1, sigmas_to_edge=postlag_sigmas_to_edge, bias=postlag_bias)
