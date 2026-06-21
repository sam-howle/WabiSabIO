from __future__ import annotations

import random
import threading
import time
from math import sqrt

import numpy as np

from scanput import (
    KEY_ALIASES,
    get_cursor_position,
    get_toggle_key_state,
    get_screen_resolution,
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
    "type_string",
    "set_cursor_position",
    "start_jitter",
    "stop_jitter",
]

_mouse_lock = threading.Lock()
_jitter_stop_event = threading.Event()
_jitter_thread: threading.Thread | None = None


# "Borrowed" from https://en.wikipedia.org/wiki/De_Casteljau%27s_algorithm#Python
# Using this is probably better than manually piecing together several different bezier curves, as it can be used to create complex motions with a single curve.
def _de_casteljau(t: float, coefs: list[np.ndarray]) -> np.ndarray:
    """Computes a single point on a Bezier curve via De Casteljau's algorithm given normalized t and a points array."""
    beta = coefs.copy()  # values in this list are overridden
    n = len(beta)
    for j in range(1, n):
        for k in range(n - j):
            beta[k] = beta[k] * (1 - t) + beta[k + 1] * t
    return beta[0]


def __compute_de_casteljau_curve(total_steps: int, points_array: list[np.ndarray]) -> list[np.ndarray]:
    # points_array contains the 'magnetic' control points. p0 and p_final are anchored endpoints.
    full_curve = []

    # t=0 returns p0 (already at start), t=1 returns p_final (appended manually below) — no need to compute either.
    for step in range(1, total_steps):
        t = step / total_steps
        full_curve.append(_de_casteljau(t, points_array))

    full_curve.append(points_array[-1])
    return full_curve


# Basic idea is, at points that are between 5% from the beginning and 15% from the end, there is a small chance that the midpoints "reshuffle" at any given point in that range
# Meaning: for some of the curves, the points that manipulate angle and speed of the curve reshuffle, causing sharp edges / changes in direction and/or speed.
# This is likely a lot closer-looking to real human input for it to sometimes do this.
def __compute_de_casteljau_curve_with_rerolls(total_steps: int, points_array: list[np.ndarray], min_radius: int) -> list[np.ndarray]:
    # points_array contains the 'magnetic' control points. p0 and p_final are anchored endpoints.
    full_curve = []

    # t=0 returns p0 (already at start), t=1 returns p_final (appended manually below) — no need to compute either.

    # Variables we need for magnetic rerolls.
    # Avoid rerolls at the fitst 5% and last 15% of the points on the curve to prevent jankiness
    initial_lockout = int(round(total_steps * 0.05))
    final_lockout = int(round(total_steps * 0.85)) # last 15%

    # 1 / reroll_chance_denominator is the chance that each individual step can result in a reroll.
    # Doing this in two steps for reability. The base denominator is (1 - initial_lockout - final_lockout) - or 1 in n where n is total steps where lockout isnt possible.
    # At base, the odds of this occuring at least once is ~63% (if we dont backoff odds of it happening twice)
    # We will then tune that chance (likely down) in the subsequent line. This makes it more readable.
    base_reroll_chance_denominator = total_steps * 0.80 
    reroll_chance_denominator = int(round( base_reroll_chance_denominator * 1.25)) # bigger denominator = lower base chance.

    # magnetic midpoints
    total_midpoints = len(points_array) - 2
    
    # Copy made for in case a reroll is triggered, we can change the remaining t values based on rerolled curve without afftecting the total loop steps.
    local_total_steps = total_steps
    
    # Allows resetting t without interfereing with the loop set by `step`
    step_normalizer = 0
    for step in range(1, total_steps):


        t = (step - step_normalizer) / local_total_steps
        
        # If outside lockout range.
        if step > initial_lockout and step < final_lockout:
            
            # If reroll. (1 in total reroll_chance_denominator)
            if random.randint(1, reroll_chance_denominator) == 1:
                # set new p0 to current pos in curve.
                current_point = _de_casteljau(t, points_array)
                shuffled_points_array = [current_point]
                destination = points_array[-1]

                midpoint_x, midpoint_y = (current_point + destination) // 2 # rounds down if odd-numbered.

                # Keep the rerolled control-point area two-dimensional for perfectly
                # horizontal/vertical remaining paths, just as the initial curve does.
                radius_x, radius_y = np.maximum(
                    min_radius,
                    np.abs(current_point - np.array([midpoint_x, midpoint_y])),
                )

                # Decrement midpoints. This will make reroll curves progressively less complex.
                total_midpoints = max(1, total_midpoints - 1) 

                # Create correct amount of random points.
                for point in range(1, total_midpoints + 1): 
                    random_x, random_y = randomize_coordinate_within_range(midpoint_x, midpoint_y, radius_x, radius_y, sigmas_to_edge_x=2, sigmas_to_edge_y=2)
                    random_point = np.array([random_x, random_y])
                    shuffled_points_array.append(random_point)
                
                # Add last point.
                shuffled_points_array.append(points_array[-1])
                
                # Overwrite original points array to continue the loop.
                points_array = shuffled_points_array

                # Set new t denominator for computing rerolled curve.
                local_total_steps = total_steps - step
               
                # this is subtracted from step before doing computation. 
                # This lets us continue the curve at a new t numerator without messing with loop position at `step`
                step_normalizer = step

                # Every time we reroll points, make it less likely to occur again.
                reroll_chance_denominator = int(round(reroll_chance_denominator * 1.35))





        full_curve.append(_de_casteljau(t, points_array))

    full_curve.append(points_array[-1])
    return full_curve


def move_mouse(
    dest_x: int, dest_y: int,
    speed_multiplier: float = 1.0,
    mouse_hz: int = 500,
    speed_sigmas_to_edge: float = 3,
    speed_bias: float = 0.0,
    jitter_intensity: int = 10,
    friction = 5
) -> None:

    # For speed normalization. If someone wants to pass 125 hz for example, they will be 4x slower.
    # Therefore, we divide total steps by the ratio of default hz to user-defined hz to prevent user-supplied hz values from affecting speed.
    default_hz = 500
    hz_normalization_multiplier = mouse_hz / default_hz

    start_x, start_y = get_cursor_position()

    # Initialize p array, starting with starting point.
    p_array = [np.array([start_x, start_y])]

    # Get screen res.
    screen_resolution_x, screen_resolution_y = get_screen_resolution()

    # Diagonal of the screen resolution. c^2 = a^2 + b^2. Shoutouts to Pythagarus
    screen_resolution_hypotenuse = sqrt(screen_resolution_x ** 2 + screen_resolution_y ** 2)

    mouse_movement_straight_line_distance_x = abs(start_x - dest_x)
    mouse_movement_straight_line_distance_y = abs(start_y - dest_y)

    mouse_movement_straight_line_distance = sqrt(mouse_movement_straight_line_distance_x ** 2 + mouse_movement_straight_line_distance_y ** 2)

    # An objective measurement of mouse movement length that works regardless of screen res or aspect ratios.
    movement_distance_to_screen_res_ratio = mouse_movement_straight_line_distance / screen_resolution_hypotenuse


    # Logamrithmic backoff on how much shorter distances back off on speed.
    # While shorter pulls are often slower, the real-life scaling doesn't elegantly match 1:1 relative to distance.
    # So, backing off by a factor relative to the objective normalization value for distnace makes sense
    # But we want greatly control how much we increase the speed for short pulls. So ratio^0.1 for ex only slightly reduces the speed more. Using the raw ratio as a backoff looks even more goofy in the opposite direction. short moves become far too quick.
    distance_step_factor = movement_distance_to_screen_res_ratio ** 0.1

    # These constants look "pretty good" as a good default speed.
    base_min_steps = 136 * distance_step_factor
    base_max_steps = 217 * distance_step_factor
    # Total amount of points along the entire multi-curve path. Less steps = higher speed.
    total_steps = int(round(clamped_gauss_randint(base_min_steps, base_max_steps, sigmas_to_edge=speed_sigmas_to_edge, bias=speed_bias) / speed_multiplier * hz_normalization_multiplier))

    # Find midpoint of the valid X,Y area to randomly select p points from. (truncates 1 pixel for odd-valued pixel ranges - sue me ;))
    midpoint_x = (start_x + dest_x) // 2
    midpoint_y = (start_y + dest_y) // 2

    # Creates a "general floor" for radius_x/radius_y. Each is ~distance/2 * cos/sin(theta), so near-perpendicular
    # angles shrink that axis's radius toward zero (perfectly vertical/horizontal being the extreme case).
    # A floor smooths this out continuously rather than branching on the exact edge case.
    min_radius = max(int(round(screen_resolution_hypotenuse * 0.015)), int(mouse_movement_straight_line_distance * 0.14))

    radius_x = max(min_radius, abs(start_x - midpoint_x))
    radius_y = max(min_radius, abs(start_y - midpoint_y))


    # Max total amount of "magnets"
    # longer distances allow more points.
    max_intermediate_p = max(4, int(movement_distance_to_screen_res_ratio * 12))
    intermediate_p = clamped_gauss_randint(1, max_intermediate_p, sigmas_to_edge=2.5, bias=-0.5) # high magnets rare but possible.

    # Create correct amount of random points. (indexing at 1 feels more 'true' to the algorithm)
    for point in range(1, intermediate_p + 1):
        random_x, random_y = randomize_coordinate_within_range(midpoint_x, midpoint_y, radius_x, radius_y, sigmas_to_edge_x=2, sigmas_to_edge_y=2)
        random_point = np.array([random_x, random_y])
        p_array.append(random_point)

    # append p_final to array.
    p_final = np.array([dest_x, dest_y])
    p_array.append(p_final)


    # Speed multiplier has already been applied as intended. Now we will use it to modify the overshoot points & dist per point
    # That said, slower speeds *should* affect it far more than higher speeds. High speed flicks typically come with a tighter hand grip that limits the overshoot magnitude. Therefore, with faster values we want to *really* stop scaling this 1:1.

    speed_scalar = speed_multiplier
    # We want diminishing returns > 1.0. This formula was kinda brute forced with testing.
    if speed_scalar > 1.0:
        speed_scalar = 1.0 + (speed_multiplier / 10)

    # Compute initial curve before overshoot, including possible mid-curve magnet rerolls.
    full_curve = _apply_mouse_jitter_filter(
        __compute_de_casteljau_curve_with_rerolls(total_steps, p_array, min_radius),
        movement_distance_to_screen_res_ratio,
        jitter_intensity=jitter_intensity,
        speed_scalar=speed_scalar
  )

    # if very short distance with respect to speed, or very low speed, no overshoot.

    if speed_scalar <= 0.05 or (movement_distance_to_screen_res_ratio * speed_scalar < 0.02):
        with _mouse_lock:
            __run_mouse_movement_curve(full_curve, mouse_hz, friction, screen_resolution_hypotenuse)
        return


    # Compute total overshoot points.
    overshoot_points = min(4, max(1, round(movement_distance_to_screen_res_ratio * speed_scalar * 4)))


    for i in range(1, overshoot_points + 1):
        # t > 1.0. Technically, doing this is out of the algorithm's intended scope.
        # But going past 1.0 allows us to overshoot our destination naturally without computing any angles.
        t = (total_steps + (total_steps * (i/(130 / speed_scalar)))) / total_steps
        point_at_t = _de_casteljau(t, p_array)
        full_curve.append(point_at_t)

    # Start at last overcorrection point
    correction_p_array = [full_curve[-1]]

    # 1 point added? Do later.

    correction_p_array.append(p_final)

    # Compute correction curve.
    correction_curve_total_steps = max(1, overshoot_points - 1)
    correction_curve = __compute_de_casteljau_curve(correction_curve_total_steps, correction_p_array)

    with _mouse_lock:
        __run_mouse_movement_curve(full_curve, mouse_hz, friction, screen_resolution_hypotenuse)

        # Hold overshoot.
        rsleep(0.015, 0.035)

        # Correct back.
        __run_mouse_movement_curve(correction_curve, mouse_hz, friction, screen_resolution_hypotenuse)


# Runs mouse teleportion to curves..
def __run_mouse_movement_curve(curve: list[np.ndarray], mouse_hz: int, friction: float, screen_resolution_hypotenuse: float) -> None:

    mouse_polling_sleep_time = 1 / mouse_hz
    prev_point = np.array(get_cursor_position())

    curve_length = len(curve)
    snag_step_cutoff = curve_length - 6 # If past snag cutoff, we lockout snag.
    snag_cycles = 0
    snag_cycles_cooldown = 0 # Cooldown for how many cycles we must complete before allowing snag again.
    snag_probability_multiplier = 1.0

    for i in range(0, curve_length):
        additional_snag_sleep_time = 0.0
        point = np.asarray(curve[i])
        local_speed = np.linalg.norm(point - prev_point) / (mouse_polling_sleep_time * screen_resolution_hypotenuse)
        
        if i < snag_step_cutoff and not snag_cycles and not snag_cycles_cooldown:
            candidate_snag_cycles = __calc_snag_chance(friction, local_speed) # Can still roll 0.

            # random.random() ret's uniform 0-1 float. 
            # Idea is: the and statement sort of works as an additional 'gate' for the probability. 
            if candidate_snag_cycles and random.random() < snag_probability_multiplier:
                snag_cycles = candidate_snag_cycles
                snag_probability_multiplier *= 0.9 # Diminishing backoff.
             
        if not snag_cycles:
            set_cursor_position(point[0], point[1])
            prev_point = point
            if snag_cycles_cooldown:
                snag_cycles_cooldown -= 1
        else:
            
            # Additional "sleep" caused by the real time that the mouse spent 'snagging'
            # Only do this once, at the end of snagging
            if snag_cycles == 1:
                additional_snag_sleep_time = clamped_gauss_randfloat(0.01, 0.08, bias=-0.5)
                additional_snag_sleep_time = round(additional_snag_sleep_time / mouse_polling_sleep_time) * mouse_polling_sleep_time

                # Prevent snag for several cycles, as objects that just escaped a state of friction-based 'snag' are typically moving quick / less likely to snag immediately after
                snag_cycles_cooldown = clamped_gauss_randint(3, 7)

            snag_cycles -= 1
        time.sleep(mouse_polling_sleep_time + additional_snag_sleep_time) # Sleep regardless of if we're skipping a cycle or not.
    return

# Friction default val = 5. Returns 0 (no snag) the vast majority of the time.
# local_speed is resolution-normalized (fraction of screen diagonal per second).
# Large sigmas_to_edge = tight dist around 0 = mostly no snag. Small = wide = snags with hold cycles.
def __calc_snag_chance(friction: float, local_speed: float) -> int:
    if friction <= 0:
        return 0
    # High speed or low friction == large sigmas_to_edge == distribution pinched at 0 == rarely snags.
    # Low speed or high friction == small sigmas_to_edge == wide spread == -> snags.
    # 400 is a tuning knob: raise it to snag less overall, lower it to snag more.
    sigmas_to_edge = max(1.0, local_speed * 250.0 / friction)
    snag_cycles = abs(clamped_gauss_randint(-5, 5, sigmas_to_edge=sigmas_to_edge))
    return (snag_cycles + 1) // 2

def _apply_mouse_jitter_filter(full_curve: list[np.ndarray], movement_distance_to_screen_res_ratio: float, jitter_intensity: int = 10, speed_scalar: float = 1.0) -> list[np.ndarray]:
    """Applies small hand tremor position offsets the *every* point of the mouse movement curve."""

    # Don't this to final pt in curve, could cause misclicks
    noise_filtered_curve = []

    # Dont round until after we apply arctan.
    max_jitter = max(1, movement_distance_to_screen_res_ratio * jitter_intensity * speed_scalar)

    for i in range(0, len(full_curve) - 1):

        # dont take abs() on dy / dx, arctan2 needs signed int for directions.
        if i == 0:
            dy = full_curve[1][1] - full_curve[0][1]
            dx = full_curve[1][0] - full_curve[0][0]
        else:
            dy = full_curve[i][1] - full_curve[i-1][1]
            dx = full_curve[i][0] - full_curve[i-1][0]
        theta = np.arctan2(dy, dx) # Inverse tanget to get angle.

        # Swap sin/cos to orient most jitter perpendicular to travel. These are
        # radii, so direction comes from sampling around the point, not their sign.
        # The one-pixel floor also adds slight along-path speed variation.
        max_jitter_x = max(1, int(round(abs(max_jitter * np.sin(theta)))))
        max_jitter_y = max(1, int(round(abs(max_jitter * np.cos(theta)))))

        # Tighter gaussian grouping than most calls. Pixel offsets >= 2 should be rare. 
        sigmas_to_edge = 3.5
        filtered_point = np.array(randomize_coordinate_within_range(full_curve[i][0], full_curve[i][1], max_jitter_x, max_jitter_y, sigmas_to_edge_x=sigmas_to_edge, sigmas_to_edge_y=sigmas_to_edge))
        noise_filtered_curve.append(filtered_point)

    # Add last point unfiltered. As promised 3000 processor instructions ago. 
    noise_filtered_curve.append(full_curve[-1])
    return noise_filtered_curve


def clamped_gauss_randint(min_int: int, max_int: int, sigmas_to_edge: float = 3, bias: float = 0.0) -> int:
    if min_int > max_int:
        raise ValueError("empty range for clamped_gauss_randint()")
    if bias < -1.0 or bias > 1.0:
        raise ValueError("Bias value outside of valid [-1.0, 1.0] range in clamped_gauss_randint()")
    return int(round(clamped_gauss_randfloat(min_int, max_int, sigmas_to_edge, bias)))

# All normal distribution-based calculations call this function, directly or indirectly.
def clamped_gauss_randfloat(min_val: float, max_val: float, sigmas_to_edge: float = 3, bias: float = 0.0) -> float:
    if min_val > max_val:
        raise ValueError("empty range for clamped_gauss_randfloat()")
    if bias < -1.0 or bias > 1.0:
        raise ValueError("Bias value outside of valid [-1.0, 1.0] range in clamped_gauss_randfloat()")
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
    x: int, radius: int,
    sigmas_to_edge: float = 3,
    bias_x: float = 0.0, bias_y: float = 0.0,
) -> tuple[int, int]:
    return randomize_coordinate_within_range(
        x, x, radius, radius,
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
    hold_time = clamped_gauss_randfloat(0.03, 0.06, sigmas_to_edge=sigmas_to_edge, bias=bias)
    key_down(key)
    time.sleep(hold_time)
    key_up(key)


def type_string(
      input_string: str,
      sleep_sigmas_to_edge: float = 1.5,
      sleep_bias: float = -0.3,
      speed_multiplier: float = 1.0,
      hold_sigmas_to_edge: float = 3,
      hold_bias: float = 0.0,
) -> None:
    
    min_next_key_delay = 0.02 / speed_multiplier
    max_next_key_delay = 0.08 / speed_multiplier

    # Use separate shift-delay variables, (Previous behavior caused compoundingly longer key press delays every time shift was touched.)
    shift_min_next_key_delay = min_next_key_delay * 1.05 
    shift_max_next_key_delay = max_next_key_delay * 1.05

    # If a shift_char is typed, we should manually press shift first.
    # Otherwise, scanput will press shift and the required key simultanously.
    shift_charset='~!@#$%^&*()_+{}|:"<>?'
    with _mouse_lock:
        for char in input_string:
            # Press shift manually for special chars & caps chars to avoid same-frame modifier+key press quirk of the scanput library.
            if char in shift_charset or char.isupper():
                modifier_key_press("shift", char, bias=hold_bias, sigmas_to_edge=hold_sigmas_to_edge)
                next_min, next_max = shift_min_next_key_delay, shift_max_next_key_delay
            else:
                # If lower-case. (Capslock must be handled by users, as stated in README.md)
                press_key(char, bias=hold_bias, sigmas_to_edge=hold_sigmas_to_edge)
                next_min, next_max = min_next_key_delay, max_next_key_delay
            rsleep(next_min, next_max, bias=sleep_bias, sigmas_to_edge=sleep_sigmas_to_edge)
        

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
    modifier: str | list[str],
    key: str | int,
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


def toggle_key_preflight_check(capslock: bool = False, scrolllock: bool = False, numlock: bool = False) -> None:
        
    # if cur toggle key state XOR target toggle key state, then we're in the wrong state. 
    # Press the toggle key to invert it.
    if get_toggle_key_state("capslock") ^ capslock:
        press_key("capslock")
        rsleep(0.1, 0.25)

    if get_toggle_key_state("scrolllock") ^ scrolllock:
        press_key("scrolllock")
        rsleep(0.1, 0.25)
    
    if get_toggle_key_state("numlock") ^ numlock:
        press_key("numlock")
        rsleep(0.1, 0.25)
