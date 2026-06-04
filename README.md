# WabiSabIO
"Perfect" your input automation through injected imperfections

`wabisabio` is an input automation Python library for Windows keyboard and mouse inputs with the specific goal of making inputs appear more human-like. The framework features pixel coordinate & timing delay randomization done using (clamped) gaussian distributions, human-like mouse movement curves that closely mimick the way a human hand would control a mouse (and idle mouse jitter to go with it).

The library utilizes the [scanput](https://github.com/sam-howle/scanput) `sendInput` wrapper which sends inputs via hardware scan codes.

## Installation
`wabisabio` requiures Python 3.9 or higher.
```
pip install wabisabio
```
Alternatively, clone this repo and build it locally:
```
git clone https://github.com/sam-howle/WabiSabIO.git
cd wabisabio
pip install .
```

## Usage

`wabisabio` offers 3 main functions: mouse movement to an `X, Y` pixel coordinate, `X, Y` coordinate randomization within a range, and randomized timing delays. Coordinate & timing randomization is done on a gaussian/normal distribution, which creates a center-biased grouping (the same way a human would).

| Function    | Description |
| ----------- | ----------- |
| `move_mouse(dest_x, dest_y)`  | Move mouse from current position to the supplied `(x, y)` screen coordinates taking a curved path    |
| `press_key(key)` | Presses the supplied `key` and releases after a short, randomized delay       |
| `left_click()` | performs a left click and releases after a short, randomized delay        |
| `right_click()` | performs a right click and releases after a short, randomized delay        |
| `lagged_press_key(key)` | Same as `press_key()`, but with randomized delays before and/or after the event        |
| `lagged_left_click()` | Same as `left_click()`, but with randomized delays before and/or after the event       |
| `lagged_right_click()` | Same as `right_click()`, but with randomized delays before and/or after the event       |
| `randomize_coordinate_within_range(x, y, radius_x, radius_y)` | Returns a gaussian-randomized `(x, y)` screen coordinate based on a center pixel `(x, y)` screen coordinates of an area-of-interest (e.g., a UI button), as well as an `x` and `y` "radius" (total pixels from center on the `x` and `y` axises, respectively) |
| `randomize_coordinate_within_square(x, y, radius)` | Same as `randomize_coordinate_within_range()`, but intended for use on square-shaped UI elements where the `x` and `y` distance from center are equal. Only has one required `radius` input parameter as a result. |
| `start_jitter()` | Causes mouse cursor to periodically 'jitter' back and forth 1-3 pixels, similar to the way a human hand resting on a physical mouse would behave. Shares a mouse-control mutex with `move_mouse()` will not interfere with it as a result. Does not need to be disabled to call `move_mouse()` and will automatically resume after the cursor is no longer in-motion. Idle jitter continues indefinately unless `stop_jtter()` is called|
| `stop_jitter()` | Disables jitter thread. `start_jitter()` needs be called again if you wish to resume idle mouse jitter. |
| `rsleep(min_time, max_time)` | Delays script execution for a random duration between the `min_time` and `max_time` value. Sleep values are randomized over a clamped gaussian distribution, causing center-values to be more common. | 
| `resleep(min_time)` | Calling `rsleep()` with just the `min_time` input parameter sets the max time to be 40% higher than the supplied payment. |


### Mouse Movement

Mouse movement is performed using the `move_mouse()` function. It works by moving along a precalculated curve starting at the mouse cursor's current position:
```python
move_mouse(dest_x, dest_y, speed_multiplier=1.0, mouse_hz=500, speed_sigmas_to_edge=3, speed_bias=0.0)
```
Example:
```python
destination_x = 750
destination_y = 300

# Move mouse to (x,y) coordinate (750,300)
move_mouse(destination_x, destination_y)
```
#### Optional parameters
* **`speed_multiplier`** `float` - used to modify mouse movement speed. A value of `1.2` will be 20% faster (120% speed), whereas a value of `0.35` will travel at a rate of 35% speed. Note that deviating too far from the default value of `1.0` may produce visually unnatural movement. Also take note that you **do not** need to modify speed based on the total distance traveled from the current cusor position -> final cursor destination - this scales automatically within the function itself, as humans have a natural tendency to favor slow movements for short distances, and fast movements for long distances.
* **`mouse_hz`** `int` - how often the simulated mouse is 'polled'. This will only affect the total amount of points the cursor travels to along the movement curve, not the speed at which it travels. It is recommended to only use common mouse polling rates such as `125`, `250`, `500` and `1000`. Only supply this parameter if you know what you're doing.

