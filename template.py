# GemRush3D — a small 3D grid collector built to match the CSE423-style PyOpenGL template
# UPDATE: First-person default camera, third-person orbit only when CHEAT (C) is ON.
# Player is now a RED ROLLING BALL, with jumping on SPACE. No new GL state calls added.

from __future__ import annotations
import random, time, math
from typing import List, Tuple

from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *

# ------------------------------
# Config
# ------------------------------
GRID_SIZE = 20               # grid spans from -GRID_SIZE..+GRID_SIZE in X and Y
CELL = 1.0
PLAYER_DIAM = 0.9            # ball diameter
PLAYER_RADIUS = PLAYER_DIAM * 0.5
GEM_RADIUS = 0.4
OBSTACLE_SIZE = 1.0

BASE_SPEED = 7.0             # world units per second
BOOST_MULTIPLIER = 2.0
BOOST_DURATION = 5.0         # seconds

JUMP_V0 = 6.5                # initial jump velocity (wu/s)
GRAVITY = -18.0              # gravity (wu/s^2)
EYE_OFFSET = 0.5             # camera eye above player center in FP

START_TIME = 60              # seconds
LEVEL_THRESHOLDS = [50, 120, 220, 360, 520]  # score gates
TIME_PENALTY_ON_LEVEL = 5    # seconds removed on each level-up

# Gem types: (name, (r,g,b), points)
GEM_TYPES = [
    ("Red",    (1.0, 0.2, 0.2), 10),
    ("Blue",   (0.2, 0.4, 1.0), 20),
    ("Yellow", (1.0, 0.9, 0.2), 30),
]
# Special speed-boost gem (spawns occasionally)
BOOST_CHANCE = 0.06
BOOST_TYPE = ("Boost", (0.1, 1.0, 0.1), 0)

# Camera parameters
cam_yaw = 0.0     # left/right in degrees (used by FP and TP)
cam_pitch = 10.0  # up/down for FP; limited
cam_dist = 32.0   # used only in cheat 3rd-person

# Player state
player_x = 0.0
player_y = 0.0
player_z = PLAYER_RADIUS     # sits on ground
vz = 0.0                     # vertical velocity
on_ground = True

# Rolling visuals
roll_angle = 0.0
roll_axis_x = 1.0
roll_axis_y = 0.0

player_speed = BASE_SPEED
boost_until = 0.0

# Game state
score = 0
level = 1
remaining = START_TIME
running = True
cheat_mode = False  # when ON: third-person orbit AND gem highlight

# Spawns
gems: List[Tuple[float,float,Tuple[float,float,float],int,bool]] = []
# gem tuple: (x, y, color, points, is_boost)

obstacles: List[Tuple[float,float]] = []  # list of (x, y) centers

# Input
keys = set()

# Timing
_last_time = None

# ------------------------------
# Utilities
# ------------------------------
def clamp(v, a, b):
    return max(a, min(b, v))

def aabb_overlap(ax, ay, asz, bx, by, bsz) -> bool:
    """Axis-aligned cube overlap in 2D (X/Y)."""
    ha = asz * 0.5
    hb = bsz * 0.5
    return (abs(ax - bx) <= ha + hb) and (abs(ay - by) <= ha + hb)

def dist2(ax, ay, bx, by):
    dx, dy = ax - bx, ay - by
    return dx*dx + dy*dy

# ------------------------------
# Spawning
# ------------------------------
def random_xy() -> Tuple[float,float]:
    return (
        random.randint(-GRID_SIZE, GRID_SIZE) * CELL,
        random.randint(-GRID_SIZE, GRID_SIZE) * CELL,
    )

def spawn_gem(force_boost: bool=False):
    global gems
    # decide type
    if force_boost:
        gtype = BOOST_TYPE
        is_boost = True
    else:
        if random.random() < BOOST_CHANCE:
            gtype = BOOST_TYPE
            is_boost = True
        else:
            gtype = random.choice(GEM_TYPES)
            is_boost = False
    # find a free location (not on obstacle or player)
    for _ in range(200):
        x, y = random_xy()
        if dist2(x, y, player_x, player_y) < (PLAYER_RADIUS + GEM_RADIUS + 0.2)**2:
            continue
        if any(aabb_overlap(x, y, GEM_RADIUS*2, ox, oy, OBSTACLE_SIZE) for (ox, oy) in obstacles):
            continue
        gems.append((x, y, gtype[1], gtype[2], is_boost))
        return
    gems.append((0.0, 0.0, gtype[1], gtype[2], is_boost))


def ensure_at_least_one_gem():
    if not gems:
        spawn_gem()


def setup_initial_spawns():
    gems.clear()
    obstacles.clear()
    for _ in range(18):
        ox, oy = random_xy()
        if dist2(ox, oy, 0.0, 0.0) < 9.0:
            continue
        obstacles.append((ox, oy))
    for _ in range(8):
        spawn_gem()
    ensure_at_least_one_gem()

# ------------------------------
# Level progression
# ------------------------------
def level_from_score(sc: int) -> int:
    lvl = 1
    for t in LEVEL_THRESHOLDS:
        if sc >= t:
            lvl += 1
    return lvl


def apply_level_changes(prev_level: int, new_level: int):
    global remaining
    if new_level <= prev_level:
        return
    add_obs = 6 + 2*(new_level-1)
    add_gem = 4 + 1*(new_level-1)
    for _ in range(add_obs):
        ox, oy = random_xy()
        if any(aabb_overlap(ox, oy, OBSTACLE_SIZE, px, py, PLAYER_DIAM) for (px, py) in [(player_x, player_y)]):
            continue
        obstacles.append((ox, oy))
    for _ in range(add_gem):
        spawn_gem()
    remaining = max(0, remaining - TIME_PENALTY_ON_LEVEL)

# ------------------------------
# HUD text helper — matches template vibe
# ------------------------------

def draw_text(x: float, y: float, s: str):
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    glRasterPos2f(x, y)
    glColor3f(1.0, 1.0, 1.0)
    for ch in s:
        glutBitmapCharacter(GLUT_BITMAP_9_BY_15, ord(ch))

# ------------------------------
# Rendering pieces
# ------------------------------

def draw_ground_grid():
    glColor3f(0.2, 0.2, 0.2)
    step = CELL
    for i in range(-GRID_SIZE, GRID_SIZE+1):
        glPushMatrix()
        glTranslatef(i*step, 0.0, -0.01)
        glScalef(0.05, (2*GRID_SIZE+1)*step, 0.02)
        glutSolidCube(1.0)
        glPopMatrix()
        glPushMatrix()
        glTranslatef(0.0, i*step, -0.01)
        glScalef((2*GRID_SIZE+1)*CELL, 0.05, 0.02)
        glutSolidCube(1.0)
        glPopMatrix()


def draw_player_ball():
    # rolling animation: rotate around axis perpendicular to motion
    glPushMatrix()
    glTranslatef(player_x, player_y, player_z)
    glRotatef(roll_angle, roll_axis_y, -roll_axis_x, 0.0)
    glColor3f(1.0, 0.2, 0.2)
    glutSolidSphere(PLAYER_RADIUS, 18, 14)
    glPopMatrix()


def draw_obstacles():
    glColor3f(0.6, 0.6, 0.6)
    for (ox, oy) in obstacles:
        glPushMatrix()
        glTranslatef(ox, oy, 0.5)
        glScalef(OBSTACLE_SIZE, OBSTACLE_SIZE, OBSTACLE_SIZE)
        glutSolidCube(1.0)
        glPopMatrix()


def draw_gems():
    for (x, y, col, pts, is_boost) in gems:
        r, g, b = (0.1, 1.0, 0.1) if (cheat_mode or is_boost) else col
        glColor3f(r, g, b)
        glPushMatrix()
        glTranslatef(x, y, 0.5)
        glutSolidSphere(GEM_RADIUS, 12, 10)
        glPopMatrix()


def draw_minimap():
    draw_text(0.62, 0.90, "MiniMap")
    draw_text(0.62, 0.86, f"P: ({int(player_x)}, {int(player_y)}) z={player_z:.1f}")
    draw_text(0.62, 0.82, f"Gems: {len(gems)}  Obs: {len(obstacles)}")


def draw_hud():
    draw_text(-0.95, 0.92, f"Score: {score}")
    draw_text(-0.20, 0.92, f"Time: {int(max(0, remaining))}s")
    draw_text(0.35, 0.92, f"Level: {level}")
    if not running:
        draw_text(-0.18, 0.00, "TIME UP — Press R to Restart")
    if cheat_mode:
        draw_text(-0.95, -0.95, "CHEAT: 3rd-person + Gem highlight")
    if time.time() < boost_until:
        draw_text(-0.20, -0.95, "SPEED BOOST!")

# ------------------------------
# Main render
# ------------------------------

# In GemRush3D, adjust only the camera logic to be a third-person follow camera (a.k.a. "chase camera").
# It follows the red ball from behind, at a fixed offset.

# ... (rest of the file unchanged up to display()) ...

def display():
    glClearColor(0.05, 0.06, 0.08, 1.0)
    glClear(GL_COLOR_BUFFER_BIT)

    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(60.0, 16/9, 0.1, 1000.0)

    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    # Third-person chase camera, always behind the player
    # Compute direction from cam_yaw
    yaw_rad = math.radians(cam_yaw)
    dirx = math.cos(yaw_rad)
    diry = math.sin(yaw_rad)
    # Camera sits some distance behind and above the player
    cam_back = 10.0
    cam_up = 6.0
    eye_x = player_x - dirx * cam_back
    eye_y = player_y - diry * cam_back
    eye_z = player_z + cam_up

    gluLookAt(
        eye_x, eye_y, eye_z,
        player_x, player_y, player_z,
        0.0, 0.0, 1.0,
    )

    # Ground plane
    glColor3f(0.08, 0.10, 0.12)
    glPushMatrix()
    glTranslatef(0.0, 0.0, -0.01)
    glScalef((2*GRID_SIZE+1)*CELL, (2*GRID_SIZE+1)*CELL, 0.02)
    glutSolidCube(1.0)
    glPopMatrix()

    draw_ground_grid()
    draw_obstacles()
    draw_gems()
    draw_player_ball()

    draw_hud()
    draw_minimap()

    glutSwapBuffers()

# ... rest of file unchanged ...


# ------------------------------
# Update
# ------------------------------

def try_move(dx: float, dy: float):
    global player_x, player_y
    nx = player_x + dx
    ny = player_y + dy
    nx = clamp(nx, -GRID_SIZE*CELL, GRID_SIZE*CELL)
    ny = clamp(ny, -GRID_SIZE*CELL, GRID_SIZE*CELL)

    blocked_x = any(aabb_overlap(nx, player_y, PLAYER_DIAM, ox, oy, OBSTACLE_SIZE) for (ox, oy) in obstacles)
    blocked_y = any(aabb_overlap(player_x, ny, PLAYER_DIAM, ox, oy, OBSTACLE_SIZE) for (ox, oy) in obstacles)
    if not blocked_x:
        player_x = nx
    if not blocked_y:
        player_y = ny


def collect_overlaps():
    global score, boost_until
    to_remove = []
    for i, (x, y, col, pts, is_boost) in enumerate(gems):
        if dist2(x, y, player_x, player_y) <= (PLAYER_RADIUS + GEM_RADIUS)**2:
            if is_boost:
                boost_until = time.time() + BOOST_DURATION
            else:
                score += pts
            to_remove.append(i)
    for i in reversed(to_remove):
        gems.pop(i)
        spawn_gem()


def update():
    global _last_time, remaining, running, player_speed, level
    global player_z, vz, on_ground, roll_angle, roll_axis_x, roll_axis_y
    now = time.time()
    if _last_time is None:
        _last_time = now
        return
    dt = now - _last_time
    _last_time = now

    if running:
        remaining = max(0.0, remaining - dt)
        if remaining <= 0.0:
            running = False

    player_speed = BASE_SPEED
    if now < boost_until:
        player_speed *= BOOST_MULTIPLIER

    # movement relative to camera yaw
    if running:
        move_x = 0.0
        move_y = 0.0
        if b"w" in keys: move_y += 1
        if b"s" in keys: move_y -= 1
        if b"a" in keys: move_x += 1
        if b"d" in keys: move_x -= 1
        if move_x != 0.0 or move_y != 0.0:
            mag = math.sqrt(move_x*move_x + move_y*move_y)
            move_x /= mag
            move_y /= mag
            # rotate move by camera yaw so W moves forward in view direction
            yaw = math.radians(cam_yaw)
            fwdx = math.cos(yaw); fwdy = math.sin(yaw)
            leftx = -fwdy; lefty = fwdx
            dirx = fwdx*move_y + leftx*move_x
            diry = fwdy*move_y + lefty*move_x
            oldx, oldy = player_x, player_y
            try_move(dirx * player_speed * dt, diry * player_speed * dt)
            # rolling angle update by distance traveled / radius (in degrees)
            dx = player_x - oldx; dy = player_y - oldy
            dist = math.sqrt(dx*dx + dy*dy)
            if dist > 0.0:
                roll_axis_x, roll_axis_y = dirx, diry
                roll_angle = (roll_angle + (dist / PLAYER_RADIUS) * (180.0 / math.pi)) % 360.0
        collect_overlaps()

    # jumping & gravity
    if not on_ground:
        vz += GRAVITY * dt
        player_z = max(PLAYER_RADIUS, player_z + vz * dt)
        if player_z <= PLAYER_RADIUS + 1e-4:
            player_z = PLAYER_RADIUS
            vz = 0.0
            on_ground = True

    # level progression
    new_level = level_from_score(score)
    if new_level != level:
        prev = level
        level = new_level
        apply_level_changes(prev, new_level)

    glutPostRedisplay()

# ------------------------------
# Input
# ------------------------------

def on_key(key: bytes, x: int, y: int):
    global cheat_mode, running, vz, on_ground
    keys.add(key)
    if key == b"c":
        cheat_mode = not cheat_mode
    elif key == b"r":
        restart_game()
    elif key == b" ":  # SPACE to jump
        if running and on_ground:
            on_ground = False
            vz = JUMP_V0
    elif key == b"q":
        import sys; sys.exit(0)


def on_key_up(key: bytes, x: int, y: int):
    if key in keys:
        keys.remove(key)


def on_special(key: int, x: int, y: int):
    global cam_yaw, cam_pitch
    if key == 100:  # left
        cam_yaw -= 4
    elif key == 102:  # right
        cam_yaw += 4
    elif key == 101:  # up
        cam_pitch = clamp(cam_pitch + 3, -35.0, 70.0)
    elif key == 103:  # down
        cam_pitch = clamp(cam_pitch - 3, -35.0, 70.0)

# ------------------------------
# Reset
# ------------------------------

def restart_game():
    global player_x, player_y, player_z, vz, on_ground
    global player_speed, boost_until
    global score, level, remaining, running
    global cam_yaw, cam_pitch

    player_x = 0.0
    player_y = 0.0
    player_z = PLAYER_RADIUS
    vz = 0.0
    on_ground = True

    # reset roll
    global roll_angle
    roll_angle = 0.0

    player_speed = BASE_SPEED
    boost_until = 0.0

    score = 0
    level = 1
    remaining = START_TIME
    running = True

    cam_yaw = 0.0
    cam_pitch = 10.0

    setup_initial_spawns()

# ------------------------------
# Bootstrap
# ------------------------------

def main():
    glutInit()
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGBA)
    glutInitWindowSize(1280, 720)
    glutCreateWindow(b"GemRush3D")

    restart_game()

    glutDisplayFunc(display)
    glutIdleFunc(update)
    glutKeyboardFunc(on_key)
    try:
        from OpenGL.GLUT import glutKeyboardUpFunc
        glutKeyboardUpFunc(on_key_up)
    except Exception:
        pass
    glutSpecialFunc(on_special)

    glutMainLoop()

if __name__ == "__main__":
    main()
