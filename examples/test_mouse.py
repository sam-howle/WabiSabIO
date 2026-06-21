import time
import wabisabio

screen_w, screen_h = wabisabio.get_screen_resolution()
center_x, center_y = screen_w // 2, screen_h // 2

# Far apart - opposite corners of the usable screen area.
FAR = [
    (int(screen_w * 0.05), int(screen_h * 0.05)),
    (int(screen_w * 0.95), int(screen_h * 0.95)),
    (int(screen_w * 0.95), int(screen_h * 0.05)),
    (int(screen_w * 0.05), int(screen_h * 0.95)),
]

# Mid range - roughly quarter-screen hops around the center.
MID = [
    (center_x - screen_w // 4, center_y),
    (center_x + screen_w // 4, center_y),
    (center_x, center_y - screen_h // 4),
    (center_x, center_y + screen_h // 4),

]

# Close together - small movements around the center.
CLOSE = [
    (center_x, center_y),
    (center_x + 80, center_y + 40),
    (center_x - 60, center_y + 90),
    (center_x + 30, center_y - 70),
]

COORDS =  FAR + MID + CLOSE 

print(f"Screen resolution: {screen_w}x{screen_h}")
print("Starting in 3 seconds. Click into a window now.\n")
time.sleep(3)

for x, y in COORDS:
    wabisabio.move_mouse(x, y, speed_multiplier=1.0, jitter_intensity=12, friction=5)
    time.sleep(0.4)
