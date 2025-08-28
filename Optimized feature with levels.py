import sys, random, math, time
from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *

# ======= Gem Catcher Game =======
# Features:
# - 300s game time
# - Bowl-shaped catcher (blue outside, white inside)
# - WASD movement + jump (space)
# - Inverted arrow keys for camera (as requested)
# - Zoom in/out with + / -
# - Gems spawn randomly; collect gems to score
# - Every 5 gems collected -> level up and player receives benefits
#   (bonus score, extra gems, extra obstacle, extra time, small speed bump, slight camera zoom)
# - Obstacles block movement
# - Cheat mode (C) highlights gems
# - Restart (R)
# - HUD and minimap

# ---------------- CONFIG ----------------
START_TIME = 300
GRID_SIZE = 20
CELL = 1.0
PLAYER_DIAM = 0.9
PLAYER_RADIUS = PLAYER_DIAM * 0.5
GEM_RADIUS = 0.4
OBSTACLE_SIZE = 1.0

BASE_SPEED = 7.0
ORIGINAL_BASE_SPEED = BASE_SPEED
BOOST_MULTIPLIER = 2.0
BOOST_DURATION = 5.0

JUMP_V0 = 6.5
GRAVITY = -18.0
EYE_OFFSET = 0.5

LEVEL_THRESHOLDS = [50, 120, 220, 360, 520]
TIME_PENALTY_ON_LEVEL = 5

GEM_TYPES = [
    ("Red",    (1.0, 0.2, 0.2), 10),
    ("Blue",   (0.2, 0.4, 1.0), 20),
    ("Yellow", (1.0, 0.9, 0.2), 30),
]

BOOST_CHANCE = 0.06
BOOST_TYPE = ("Boost", (0.1, 1.0, 0.1), 0)

# camera
cam_yaw = 0.0
cam_pitch = 10.0
cam_dist = 12.0
CAM_DIST_MIN = 6.0
CAM_DIST_MAX = 40.0
CAM_ZOOM_STEP = 1.0

# player state
player_x = 0.0
player_y = 0.0
player_z = PLAYER_RADIUS
vz = 0.0
on_ground = True

roll_angle = 0.0
roll_axis_x = 1.0
roll_axis_y = 0.0

player_speed = BASE_SPEED
boost_until = 0.0

# game state
score = 0
level = 1
remaining = START_TIME
running = True
cheat_mode = False

gems = [] 
obstacles = [] 

gems_collected = 0

keys = set()
_last_time = None

# window
WIN_W = 1280
WIN_H = 720

# ---------------- UTILITIES ----------------

def clamp(v, a, b):
    return max(a, min(b, v))

def aabb_overlap(ax, ay, asz, bx, by, bsz) -> bool:
    ha = asz * 0.5
    hb = bsz * 0.5
    return (abs(ax - bx) <= ha + hb) and (abs(ay - by) <= ha + hb)

def dist2(ax, ay, bx, by):
    dx, dy = ax - bx, ay - by
    return dx*dx + dy*dy

# ---------------- SPAWNING ----------------

def random_xy() -> tuple:
    return (
        random.randint(-GRID_SIZE, GRID_SIZE) * CELL,
        random.randint(-GRID_SIZE, GRID_SIZE) * CELL,
    )

def spawn_gem(force_boost: bool=False):
    global gems
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
    global gems, obstacles
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

# ---------------- LEVEL-UP ----------------

def on_level_up():
    global level, score, remaining, cam_dist, BASE_SPEED
    level += 1
    score += 50  # bonus
    remaining = remaining + 20  # reward extra time
    # spawn extra gems and an obstacle
    for _ in range(3):
        spawn_gem()
    ox, oy = random_xy()
    obstacles.append((ox, oy))
    # small player speed bump
    BASE_SPEED += 0.6
    # slight camera zoom in to reward player
    cam_dist = clamp(cam_dist - 1.0, CAM_DIST_MIN, CAM_DIST_MAX)

# ---------------- HUD / TEXT ----------------

def draw_text_ndc(x: float, y: float, s: str, font=GLUT_BITMAP_9_BY_15):
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    glRasterPos2f(x, y)
    glColor3f(1.0, 1.0, 1.0)
    for ch in s:
        glutBitmapCharacter(font, ord(ch))

    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

# ---------------- RENDERING ----------------

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

def draw_player_bowl():
    quad = gluNewQuadric()
    glPushMatrix()
    glTranslatef(player_x, player_y, player_z)
    glTranslatef(0.0, 0.0, -PLAYER_RADIUS)

    outer_r = PLAYER_RADIUS * 1.15
    inner_r = PLAYER_RADIUS * 0.78
    height = PLAYER_RADIUS * 0.9

    # outer base
    glColor3f(0.10, 0.45, 0.95)
    gluDisk(quad, 0.0, outer_r, 32, 1)

    # outer wall
    glPushMatrix()
    glTranslatef(0.0, 0.0, 0.0)
    gluCylinder(quad, outer_r, outer_r*0.98, height, 32, 1)
    glPopMatrix()

    # inner (white)
    glColor3f(1.0, 1.0, 1.0)
    glPushMatrix()
    glTranslatef(0.0, 0.0, 0.02)
    gluDisk(quad, 0.0, inner_r, 32, 1)
    gluCylinder(quad, inner_r, inner_r*0.98, max(0.01, height - 0.02), 32, 1)
    glPopMatrix()

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

# ---------------- MINIMAP ----------------
MM_LEFT = 0.60
MM_RIGHT = 0.98
MM_BOTTOM = -0.18
MM_TOP = 0.36

def _mm_world_to_uv(wx: float, wy: float):
    span = GRID_SIZE * CELL
    u = (wx / (2.0*span)) + 0.5
    v = (wy / (2.0*span)) + 0.5
    return clamp(u, 0.0, 1.0), clamp(v, 0.0, 1.0)

def _mm_uv_to_ndc(u: float, v: float):
    x = (MM_LEFT + u * (MM_RIGHT - MM_LEFT)) * 2.0 - 1.0
    y = (MM_BOTTOM + v * (MM_TOP - MM_BOTTOM)) * 2.0 - 1.0
    return x, y

def _mm_draw_quad_ndc(x0, y0, x1, y1):
    glBegin(GL_QUADS)
    glVertex2f(x0, y0)
    glVertex2f(x1, y0)
    glVertex2f(x1, y1)
    glVertex2f(x0, y1)
    glEnd()

def _mm_draw_disc_ndc(cx, cy, r, segments=18):
    glBegin(GL_TRIANGLE_FAN)
    glVertex2f(cx, cy)
    for i in range(segments+1):
        ang = (i/segments) * 2.0 * math.pi
        glVertex2f(cx + r*math.cos(ang), cy + r*math.sin(ang))
    glEnd()

def draw_minimap():
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity()
    glMatrixMode(GL_MODELVIEW);  glPushMatrix();  glLoadIdentity()

    # background
    glColor3f(0.06, 0.08, 0.10)
    _mm_draw_quad_ndc(MM_LEFT, MM_BOTTOM, MM_RIGHT, MM_TOP)

    # border
    glColor3f(0.8, 0.8, 0.85)
    glBegin(GL_LINE_LOOP)
    glVertex2f(MM_LEFT, MM_BOTTOM)
    glVertex2f(MM_RIGHT, MM_BOTTOM)
    glVertex2f(MM_RIGHT, MM_TOP)
    glVertex2f(MM_LEFT, MM_TOP)
    glEnd()

    # obstacles
    for (ox, oy) in obstacles:
        u, v = _mm_world_to_uv(ox, oy)
        cx, cy = _mm_uv_to_ndc(u, v)
        side = (OBSTACLE_SIZE / (2.0*GRID_SIZE*CELL)) * (MM_RIGHT - MM_LEFT)
        side_ndc_x = side * 2.0
        side_ndc_y = side * 2.0 * ((MM_TOP - MM_BOTTOM) / (MM_RIGHT - MM_LEFT))
        glColor3f(0.45, 0.45, 0.45)
        _mm_draw_quad_ndc(cx - side_ndc_x*0.6, cy - side_ndc_y*0.6, cx + side_ndc_x*0.6, cy + side_ndc_y*0.6)

    # gems
    for (gx, gy, col, pts, is_boost) in gems:
        r, g, b = (0.1, 1.0, 0.1) if (cheat_mode or is_boost) else col
        u, v = _mm_world_to_uv(gx, gy)
        x, y = _mm_uv_to_ndc(u, v)
        glColor3f(r, g, b)
        _mm_draw_disc_ndc(x, y, 0.012)

    # player
    u, v = _mm_world_to_uv(player_x, player_y)
    px, py = _mm_uv_to_ndc(u, v)
    glColor3f(0.98, 0.4, 0.4)
    _mm_draw_disc_ndc(px, py, 0.018)

    # text
    draw_text_ndc((MM_LEFT + 0.02)*2.0 - 1.0, (MM_TOP - 0.02)*2.0 - 1.0, "MiniMap")
    draw_text_ndc((MM_LEFT + 0.02)*2.0 - 1.0, (MM_TOP - 0.06)*2.0 - 1.0, f"P: ({int(player_x)}, {int(player_y)}) z={player_z:.1f}")
    draw_text_ndc((MM_LEFT + 0.02)*2.0 - 1.0, (MM_TOP - 0.10)*2.0 - 1.0, f"Gems: {len(gems)}  Obs: {len(obstacles)}")

    glMatrixMode(GL_MODELVIEW);  glPopMatrix()
    glMatrixMode(GL_PROJECTION); glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

# ---------------- HUD ----------------

def draw_hud():
    draw_text_ndc(-0.95, 0.92, f"Score: {score}")
    draw_text_ndc(-0.20, 0.92, f"Time: {int(max(0, remaining))}s")
    draw_text_ndc(0.35, 0.92, f"Level: {level}")
    if not running:
        draw_text_ndc(-0.18, 0.00, "TIME UP — Press R to Restart")
    if cheat_mode:
        draw_text_ndc(-0.95, -0.95, "CHEAT: 3rd-person + Gem highlight")
    if time.time() < boost_until:
        draw_text_ndc(-0.20, -0.95, "SPEED BOOST!")

# ---------------- CAMERA & RENDER ----------------

def _apply_camera():
    yaw = math.radians(cam_yaw)
    pitch = math.radians(cam_pitch)
    dirx = math.cos(pitch) * math.cos(yaw)
    diry = math.cos(pitch) * math.sin(yaw)
    dirz = math.sin(pitch)

    eye_x = player_x - dirx * cam_dist
    eye_y = player_y - diry * cam_dist
    eye_z = player_z + dirz * cam_dist

    gluLookAt(eye_x, eye_y, eye_z, player_x, player_y, player_z, 0.0, 0.0, 1.0)

def display():
    global WIN_W, WIN_H
    glClearColor(0.05, 0.06, 0.08, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    glViewport(0, 0, WIN_W, WIN_H)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(60.0, float(WIN_W)/float(WIN_H), 0.1, 1000.0)

    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    _apply_camera()

    # draw world
    glColor3f(0.08, 0.10, 0.12)
    glPushMatrix()
    glTranslatef(0.0, 0.0, -0.01)
    glScalef((2*GRID_SIZE+1)*CELL, (2*GRID_SIZE+1)*CELL, 0.02)
    glutSolidCube(1.0)
    glPopMatrix()

    draw_ground_grid()
    draw_obstacles()
    draw_gems()
    draw_player_bowl()

    draw_hud()
    draw_minimap()

    glutSwapBuffers()

# ---------------- UPDATE ----------------

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
    global score, boost_until, gems_collected
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
        gems_collected += 1
        spawn_gem()
        # level up every 5 collected gems
        if gems_collected % 5 == 0:
            on_level_up()

def update():
    global _last_time, remaining, running, player_speed, level
    global player_z, vz, on_ground, roll_angle, roll_axis_x, roll_axis_y
    now = time.time()
    if _last_time is None:
        globals()['_last_time'] = now
        return
    dt = now - _last_time
    globals()['_last_time'] = now

    if running:
        remaining = max(0.0, remaining - dt)
        if remaining <= 0.0:
            running = False

    # boost handling
    player_speed = BASE_SPEED
    if now < boost_until:
        player_speed *= BOOST_MULTIPLIER

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

            yaw = math.radians(cam_yaw)
            fwdx = math.cos(yaw); fwdy = math.sin(yaw)
            leftx = -fwdy; lefty = fwdx
            dirx = fwdx*move_y + leftx*move_x
            diry = fwdy*move_y + lefty*move_x
            oldx, oldy = player_x, player_y
            try_move(dirx * player_speed * dt, diry * player_speed * dt)

            dx = player_x - oldx; dy = player_y - oldy
            dist = math.sqrt(dx*dx + dy*dy)
            if dist > 0.0:
                roll_axis_x, roll_axis_y = dirx, diry
                roll_angle = (roll_angle + (dist / PLAYER_RADIUS) * (180.0 / math.pi)) % 360.0
        collect_overlaps()

    # jump physics
    if not on_ground:
        vz += GRAVITY * dt
        player_z = max(PLAYER_RADIUS, player_z + vz * dt)
        if player_z <= PLAYER_RADIUS + 1e-4:
            player_z = PLAYER_RADIUS
            vz = 0.0
            on_ground = True

    ng = 1
    for t in LEVEL_THRESHOLDS:
        if score >= t:
            ng += 1

    glutPostRedisplay()

# ---------------- INPUT ----------------

def on_key(key: bytes, x: int, y: int):
    global cheat_mode, running, vz, on_ground, cam_dist, BASE_SPEED, score, remaining
    keys.add(key)
    if key == b"c":
        cheat_mode = not cheat_mode
    elif key == b"r":
        restart_game()
    elif key == b" ":
        if running and on_ground:
            on_ground = False
            vz = JUMP_V0
    elif key in (b'+', b'=',):
        cam_dist = clamp(cam_dist - CAM_ZOOM_STEP, CAM_DIST_MIN, CAM_DIST_MAX)
    elif key in (b'-', b'_',):
        cam_dist = clamp(cam_dist + CAM_ZOOM_STEP, CAM_DIST_MIN, CAM_DIST_MAX)
    elif key == b'q':
        import sys; sys.exit(0)

def on_key_up(key: bytes, x: int, y: int):
    if key in keys:
        keys.remove(key)

def on_special(key: int, x: int, y: int):
    global cam_yaw, cam_pitch
    # inverted controls
    if key == GLUT_KEY_LEFT:
        cam_yaw += 4
    elif key == GLUT_KEY_RIGHT:
        cam_yaw -= 4
    elif key == GLUT_KEY_UP:
        cam_pitch = clamp(cam_pitch - 3, -35.0, 70.0)
    elif key == GLUT_KEY_DOWN:
        cam_pitch = clamp(cam_pitch + 3, -35.0, 70.0)

# ---------------- RESTART ----------------

def restart_game():
    global player_x, player_y, player_z, vz, on_ground
    global player_speed, boost_until
    global score, level, remaining, running, gems_collected, BASE_SPEED, _last_time
    global cam_yaw, cam_pitch, cam_dist

    player_x = 0.0
    player_y = 0.0
    player_z = PLAYER_RADIUS
    vz = 0.0
    on_ground = True

    global roll_angle
    roll_angle = 0.0

    player_speed = ORIGINAL_BASE_SPEED
    BASE_SPEED = ORIGINAL_BASE_SPEED
    boost_until = 0.0

    score = 0
    level = 1
    remaining = START_TIME
    running = True
    gems_collected = 0

    cam_yaw = 0.0
    cam_pitch = 10.0
    cam_dist = 12.0

    _last_time = None
    setup_initial_spawns()

# ---------------- RESHAPE / INIT ----------------

def reshape(w: int, h: int):
    global WIN_W, WIN_H
    WIN_W = max(200, w)
    WIN_H = max(200, h)
    glViewport(0, 0, WIN_W, WIN_H)

def init_gl():
    glEnable(GL_DEPTH_TEST)
    glDepthFunc(GL_LEQUAL)
    glClearDepth(1.0)
    glShadeModel(GL_SMOOTH)

# ---------------- BOOTSTRAP ----------------

def main():
    glutInit()
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGBA | GLUT_DEPTH)
    glutInitWindowSize(WIN_W, WIN_H)
    glutInitWindowPosition(50, 50)
    glutCreateWindow(b"Gem Catcher - Level Every 5 Gems")

    init_gl()
    restart_game()

    glutDisplayFunc(display)
    glutIdleFunc(update)
    glutKeyboardFunc(on_key)
    try:
        glutKeyboardUpFunc(on_key_up)
    except Exception:
        pass
    glutSpecialFunc(on_special)
    glutReshapeFunc(reshape)

    glutMainLoop()

if __name__ == "__main__":
    main()
