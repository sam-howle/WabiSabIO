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

