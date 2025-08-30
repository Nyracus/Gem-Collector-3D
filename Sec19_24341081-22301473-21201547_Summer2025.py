import sys, random, time, math, os

from typing import List, Tuple

from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *

START_TIME = 300.0
GRID_SIZE = 20
CELL = 1.0

PLAYER_DIAM = 0.9
PLAYER_RADIUS = PLAYER_DIAM * 0.5
GEM_RADIUS = 0.4
OBSTACLE_SIZE = 1.0

BASE_SPEED = 7.0
BOOST_MULTIPLIER = 2.0
BOOST_DURATION = 5.0
BREAK_TTL = 0.6

JUMP_V0 = 9.5
GRAVITY = -18.0
CLIMB_MARGIN = 0.05

LAVA_SLOW_MULT = 0.5
LAVA_DPS = 20.0
MAX_LAVA = 6
LAVA_MIN_R = 2.5
LAVA_MAX_R = 4.0
LAVA_TTL = 8.0
LAVA_BASE = 2

LEVEL_GEMS = 5

GEM_TYPES = [
    ("Red",    (1.0, 0.2, 0.2), 10),
    ("Blue",   (0.2, 0.4, 1.0), 20),
    ("Yellow", (1.0, 0.9, 0.2), 30),
]
BOOST_CHANCE = 0.06
BOOST_TYPE = ("Boost", (0.1, 1.0, 0.1), 0)

cam_yaw = 0.0
cam_pitch = 12.0
cam_dist = 12.0
CAM_DIST_MIN = 6.0
CAM_DIST_MAX = 40.0
CAM_ZOOM_STEP = 1.0
FP_EYE_OFFSET = 0.35
camera_mode = 0

WIN_W, WIN_H = 1280, 720

player_x = 0.0
player_y = 0.0
player_z = PLAYER_RADIUS
vz = 0.0
on_ground = True

player_speed = BASE_SPEED
boost_until = 0.0

score = 0
level = 1
remaining = START_TIME
running = True
cheat_mode = False

gems: List[Tuple[float,float,Tuple[float,float,float],int,bool]] = []
obstacles: List[Tuple[float,float]] = []
breaking_obs: List[Tuple[float,float,float,float]] = []
obstacles_rect: List[Tuple[float,float,float,float,float]] = []
slopes: List[Tuple[float,float,str,float,float,int,float]] = []
treasure_boxes: List[Tuple[float,float,str]] = []
lava_pools: List[Tuple[float,float,float,float]] = []
lava_dmg_accum = 0.0



gems_collected = 0

keys = set()
_last_time = None

popup_msg = ""
popup_until = 0.0

def clamp(v, a, b):
    return max(a, min(b, v))

def aabb_overlap(ax, ay, asz, bx, by, bsz) -> bool:
    ha = asz * 0.5
    hb = bsz * 0.5
    return (abs(ax - bx) <= ha + hb) and (abs(ay - by) <= ha + hb)

def rect_overlap(ax, ay, asx, asy, bx, by, bsx, bsy) -> bool:
    return (abs(ax - bx) <= asx*0.5 + bsx*0.5) and (abs(ay - by) <= asy*0.5 + bsy*0.5)

def dist2(ax, ay, bx, by):
    dx, dy = ax - bx, ay - by
    return dx*dx + dy*dy

def rand_xy_avoiding_player(min_dist=1.0):
    for _ in range(200):
        x = random.randint(-GRID_SIZE, GRID_SIZE) * CELL
        y = random.randint(-GRID_SIZE, GRID_SIZE) * CELL
        if dist2(x, y, player_x, player_y) > (min_dist*min_dist):
            return x, y
    return 0.0, 0.0

def slope_height_at(s, x, y):
    sx, sy, sdir, length, width, steps, step_h = s
    if sdir == 'x':
        if abs(y - sy) > width*0.5: return 0.0
        t = (x - (sx - length*0.5)) / length
    else:
        if abs(x - sx) > width*0.5: return 0.0
        t = (y - (sy - length*0.5)) / length
    if t < 0.0 or t > 1.0: return 0.0
    idx = int(math.floor(t * steps))
    if idx < 0: idx = 0
    if idx >= steps: idx = steps - 1
    return (idx + 1) * step_h

def ground_height_at(x, y):
    h = 0.0
    for (ox, oy) in obstacles:
        if aabb_overlap(x, y, PLAYER_DIAM, ox, oy, OBSTACLE_SIZE):
            h = max(h, 1.0)
    for (rx, ry, sx, sy, sz) in obstacles_rect:
        if rect_overlap(x, y, PLAYER_DIAM, PLAYER_DIAM, rx, ry, sx, sy):
            h = max(h, sz)
    for s in slopes:
        t = slope_height_at(s, x, y)
        h = max(h, t)
    return h



def pos_hits_any_obstacle(x, y):
    if any(aabb_overlap(x, y, GEM_RADIUS*2, ox, oy, OBSTACLE_SIZE) for (ox, oy) in obstacles): return True
    if any(rect_overlap(x, y, GEM_RADIUS*2, GEM_RADIUS*2, rx, ry, sx, sy) for (rx,ry,sx,sy,sz) in obstacles_rect): return True
    for s in slopes:
        sx, sy, sdir, length, width, steps, step_h = s
        if sdir == 'x':
            if abs(y - sy) <= width*0.5 and (sx - length*0.5) <= x <= (sx + length*0.5): return True
        else:
            if abs(x - sx) <= width*0.5 and (sy - length*0.5) <= y <= (sy + length*0.5): return True
    return False

def spawn_gem(force_boost: bool=False):
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
        x, y = rand_xy_avoiding_player(min_dist=1.0)
        if pos_hits_any_obstacle(x, y):
            continue
        gems.append((x, y, gtype[1], gtype[2], is_boost))
        return
    gems.append((0.0, 0.0, gtype[1], gtype[2], is_boost))

def spawn_gem_at(x, y, col, pts, is_boost=False):
    gems.append((x, y, col, pts, is_boost))


def spawn_lava_pool():
    for _ in range(200):
        x, y = rand_xy_avoiding_player(min_dist=5.0)
        r = random.uniform(LAVA_MIN_R, LAVA_MAX_R)
        if pos_hits_any_obstacle(x, y): continue
        t = random.uniform(LAVA_TTL*0.8, LAVA_TTL*1.2)
        lava_pools.append((x, y, r, t))
        return

def in_lava(x, y):
    for (lx, ly, lr, lt) in lava_pools:
        if dist2(x, y, lx, ly) <= (lr + PLAYER_RADIUS*0.2)**2:
            return True
    return False

def draw_lava():
    quad = gluNewQuadric()
    for (lx, ly, lr, lt) in lava_pools:
        glColor3f(0.9, 0.1, 0.1)
        glPushMatrix()
        glTranslatef(lx, ly, 0.06)
        gluDisk(quad, 0.0, lr, 64, 1)
        glPopMatrix()



def spawn_treasure_box():
    for _ in range(200):
        x = random.randint(-GRID_SIZE, GRID_SIZE) * CELL
        y = random.randint(-GRID_SIZE, GRID_SIZE) * CELL
        if dist2(x, y, player_x, player_y) < (2.0*2.0):
            continue
        if pos_hits_any_obstacle(x, y):
            continue
        effect = random.choice(["help", "harm"])
        treasure_boxes.append((x, y, effect))
        return
    treasure_boxes.append((0.0,0.0, random.choice(["help","harm"])))

def spawn_rect_obstacle():
    for _ in range(200):
        rx, ry = rand_xy_avoiding_player(min_dist=3.0)
        sx = random.uniform(1.2, 3.0)
        sy = random.uniform(0.8, 2.2)
        sz = random.uniform(1.0, 2.0)
        if pos_hits_any_obstacle(rx, ry): continue
        obstacles_rect.append((rx, ry, sx, sy, sz))
        return

def spawn_slope_with_top_gem():
    for _ in range(200):
        sx, sy = rand_xy_avoiding_player(min_dist=6.0)
        sdir = random.choice(['x','y'])
        length = random.uniform(4.0, 7.0)
        width = random.uniform(1.2, 2.0)
        steps = random.randint(4, 6)
        step_h = random.uniform(0.35, 0.55)
        if pos_hits_any_obstacle(sx, sy): continue
        slopes.append((sx, sy, sdir, length, width, steps, step_h))
        if sdir == 'x':
            tx = sx + length*0.5
            ty = sy
        else:
            tx = sx
            ty = sy + length*0.5
        spawn_gem_at(tx, ty, (1.0, 0.8, 0.2), 50, False)
        return

def setup_initial_spawns():
    gems.clear()
    obstacles.clear()
    obstacles_rect.clear()
    slopes.clear()
    treasure_boxes.clear()
    for _ in range(12):
        ox, oy = rand_xy_avoiding_player(min_dist=4.0)
        obstacles.append((ox, oy))
    for _ in range(4):
        spawn_rect_obstacle()
    spawn_slope_with_top_gem()
    for _ in range(8):
        spawn_gem()
    for _ in range(2):
        spawn_treasure_box()
    for _ in range(min(LAVA_BASE, MAX_LAVA)):
        spawn_lava_pool()


    if not gems:
        spawn_gem()

def on_level_up():
    global level, score, remaining, cam_dist, player_speed
    level += 1
    score += 50
    remaining = max(0.0, remaining + 20.0)
    for _ in range(2):
        spawn_gem()
    for _ in range(2):
        spawn_rect_obstacle()
    spawn_slope_with_top_gem()
    ox, oy = rand_xy_avoiding_player(min_dist=2.0)
    obstacles.append((ox, oy))
    player_speed += 0.6
    cam_dist = clamp(cam_dist - 1.0, CAM_DIST_MIN, CAM_DIST_MAX)

def draw_text_screen(x: float, y: float, s: str, font=GLUT_BITMAP_HELVETICA_18):
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity()
    glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
    glRasterPos2f(x, y)
    glColor3f(1.0, 1.0, 1.0)
    for ch in s:
        glutBitmapCharacter(font, ord(ch))
    glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

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

def draw_skybox():
    glDepthMask(GL_FALSE)
    glPushMatrix()
    glColor3f(0.04, 0.05, 0.09)
    size = (2*GRID_SIZE + 4)
    glTranslatef(0.0, 0.0, size * 0.5)
    glScalef(size*CELL, size*CELL, size)
    glutSolidCube(1.0)
    glPopMatrix()
    glDepthMask(GL_TRUE)

def draw_ground_tiles():
    tile = 1.0
    half = GRID_SIZE
    for i in range(-half, half+1):
        for j in range(-half, half+1):
            shade = 0.15 + 0.05 * ((i + j) & 1)
            glColor3f(shade, shade*1.05, shade*1.10)
            glPushMatrix()
            glTranslatef(i*tile, j*tile, -0.005)
            glScalef(tile*0.98, tile*0.98, 0.01)
            glutSolidCube(1.0)
            glPopMatrix()

def draw_perimeter_pillars():
    for i in range(-GRID_SIZE-2, GRID_SIZE+3):
        for j in (-GRID_SIZE-2, GRID_SIZE+2):
            h = 2.0 + (abs(i) % 5) * 0.7
            shade = 0.20 + 0.03*h
            glColor3f(shade, shade+0.02, shade+0.04)
            glPushMatrix()
            glTranslatef(i*CELL, j*CELL, h*0.5)
            glScalef(0.5, 0.5, h)
            glutSolidCube(1.0)
            glPopMatrix()
    for j in range(-GRID_SIZE-1, GRID_SIZE+2):
        for i in (-GRID_SIZE-2, GRID_SIZE+2):
            h = 2.0 + (abs(j) % 5) * 0.7
            shade = 0.20 + 0.03*h
            glColor3f(shade, shade+0.02, shade+0.04)
            glPushMatrix()
            glTranslatef(i*CELL, j*CELL, h*0.5)
            glScalef(0.5, 0.5, h)
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
    glColor3f(0.10, 0.45, 0.95)
    gluDisk(quad, 0.0, outer_r, 32, 1)
    glPushMatrix()
    gluCylinder(quad, outer_r, outer_r*0.98, height, 32, 1)
    glPopMatrix()
    glColor3f(1.0, 1.0, 1.0)
    glPushMatrix()
    glTranslatef(0.0, 0.0, 0.02)
    gluDisk(quad, 0.0, inner_r, 32, 1)
    gluCylinder(quad, inner_r, inner_r*0.98, max(0.01, height - 0.02), 32, 1)
    glPopMatrix()
    glPopMatrix()

def draw_obstacles():
    glColor3f(0.6, 0.6, 0.6)
    for ox, oy in obstacles:
        glPushMatrix()
        glTranslatef(ox, oy, 0.5)
        glScalef(OBSTACLE_SIZE, OBSTACLE_SIZE, OBSTACLE_SIZE)
        glutSolidCube(1.0)
        glPopMatrix()
    for (bx, by, bscale, bttl) in breaking_obs:
        glPushMatrix()
        glTranslatef(bx, by, 0.5 * max(0.0, bscale))
        glScalef(OBSTACLE_SIZE * max(0.0, bscale), OBSTACLE_SIZE * max(0.0, bscale), OBSTACLE_SIZE * max(0.0, bscale))
        f = max(0.0, bttl / BREAK_TTL)
        glColor3f(0.6 * f, 0.6 * f, 0.6 * f)
        glutSolidCube(1.0)
        glPopMatrix()


def draw_gems():
    for x, y, col, pts, is_boost in gems:
        r, g, b = (0.1, 1.0, 0.1) if (cheat_mode or is_boost) else col
        glColor3f(r, g, b)
        glPushMatrix()
        glTranslatef(x, y, 0.5)
        glutSolidSphere(GEM_RADIUS, 12, 10)
        glPopMatrix()

def draw_treasure_boxes():
    for x, y, _effect in treasure_boxes:
        glColor3f(0.8, 0.5, 0.0)
        glPushMatrix()
        glTranslatef(x, y, 0.5)
        glutSolidCube(0.9)
        glPopMatrix()

MM_LEFT = 0.60; MM_RIGHT = 0.98; MM_BOTTOM = -0.18; MM_TOP = 0.36
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
    glBegin(GL_QUADS); glVertex2f(x0, y0); glVertex2f(x1, y0); glVertex2f(x1, y1); glVertex2f(x0, y1); glEnd()
def _mm_draw_disc_ndc(cx, cy, r, segments=18):
    glBegin(GL_TRIANGLE_FAN); glVertex2f(cx, cy)
    for i in range(segments+1):
        ang = (i/segments) * 2.0 * math.pi
        glVertex2f(cx + r*math.cos(ang), cy + r*math.sin(ang))
    glEnd()

def draw_minimap():
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity()
    glMatrixMode(GL_MODELVIEW);  glPushMatrix();  glLoadIdentity()
    glColor3f(0.06, 0.08, 0.10); _mm_draw_quad_ndc(MM_LEFT, MM_BOTTOM, MM_RIGHT, MM_TOP)
    glColor3f(0.8, 0.8, 0.85)
    glBegin(GL_LINE_LOOP); glVertex2f(MM_LEFT, MM_BOTTOM); glVertex2f(MM_RIGHT, MM_BOTTOM); glVertex2f(MM_RIGHT, MM_TOP); glVertex2f(MM_LEFT, MM_TOP); glEnd()
    for ox, oy in obstacles:
        u, v = _mm_world_to_uv(ox, oy); cx, cy = _mm_uv_to_ndc(u, v)
        side = (OBSTACLE_SIZE/(2.0*GRID_SIZE*CELL))*(MM_RIGHT-MM_LEFT)
        side_ndc_x = side*2.0; side_ndc_y = side*2.0*((MM_TOP-MM_BOTTOM)/(MM_RIGHT-MM_LEFT))
        glColor3f(0.45,0.45,0.45); _mm_draw_quad_ndc(cx-side_ndc_x*0.6, cy-side_ndc_y*0.6, cx+side_ndc_x*0.6, cy+side_ndc_y*0.6)
    for (rx, ry, sx, sy, sz) in obstacles_rect:
        u, v = _mm_world_to_uv(rx, ry); cx, cy = _mm_uv_to_ndc(u, v)
        wx = (sx/(2.0*GRID_SIZE*CELL))*(MM_RIGHT-MM_LEFT)*2.0
        wy = (sy/(2.0*GRID_SIZE*CELL))*(MM_TOP-MM_BOTTOM)*2.0
        glColor3f(0.55,0.55,0.6); _mm_draw_quad_ndc(cx-wx*0.5, cy-wy*0.5, cx+wx*0.5, cy+wy*0.5)
    for (sx, sy, sdir, length, width, steps, step_h) in slopes:
        u, v = _mm_world_to_uv(sx, sy); cx, cy = _mm_uv_to_ndc(u, v)
        lx = (length/(2.0*GRID_SIZE*CELL))*(MM_RIGHT-MM_LEFT)*2.0
        wy = (width /(2.0*GRID_SIZE*CELL))*(MM_TOP-MM_BOTTOM)*2.0
        if sdir == 'x':
            _mm_draw_quad_ndc(cx-lx*0.5, cy-wy*0.5, cx+lx*0.5, cy+wy*0.5)
        else:
            _mm_draw_quad_ndc(cx-wy*0.5, cy-lx*0.5, cx+wy*0.5, cy+lx*0.5)
    for gx, gy, col, pts, is_boost in gems:
        r,g,b = (0.1,1.0,0.1) if (cheat_mode or is_boost) else col
        u,v = _mm_world_to_uv(gx,gy); x,y = _mm_uv_to_ndc(u,v)
        glColor3f(r,g,b); _mm_draw_disc_ndc(x,y,0.012)
    u,v = _mm_world_to_uv(player_x, player_y); px,py = _mm_uv_to_ndc(u,v)
    glColor3f(0.98,0.4,0.4); _mm_draw_disc_ndc(px,py,0.018)
    for tx, ty, _ in treasure_boxes:
        u,v = _mm_world_to_uv(tx,ty); x,y = _mm_uv_to_ndc(u,v)
        glColor3f(0.8,0.5,0.0); _mm_draw_disc_ndc(x,y,0.01)
    draw_text_screen((MM_LEFT+0.02)*2.0-1.0, (MM_TOP-0.02)*2.0-1.0, "MiniMap")
    draw_text_screen((MM_LEFT+0.02)*2.0-1.0, (MM_TOP-0.06)*2.0-1.0, f"P: ({int(player_x)},{int(player_y)}) z={player_z:.1f}")
    total_obs = len(obstacles)+len(obstacles_rect)+len(slopes)
    draw_text_screen((MM_LEFT+0.02)*2.0-1.0, (MM_TOP-0.10)*2.0-1.0, f"Gems: {len(gems)} Obs: {total_obs}")
    glMatrixMode(GL_MODELVIEW); glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

def _apply_camera():
    yaw = math.radians(cam_yaw); pitch = math.radians(cam_pitch)
    dirx = math.cos(pitch)*math.cos(yaw); diry = math.cos(pitch)*math.sin(yaw); dirz = math.sin(pitch)
    if camera_mode == 0:
        eye_x = player_x - dirx * cam_dist; eye_y = player_y - diry * cam_dist; eye_z = player_z + dirz * cam_dist
        gluLookAt(eye_x, eye_y, eye_z, player_x, player_y, player_z, 0.0, 0.0, 1.0)
    else:
        eye_x = player_x; eye_y = player_y; eye_z = player_z + FP_EYE_OFFSET
        cx = eye_x + dirx; cy = eye_y + diry; cz = eye_z + dirz
        gluLookAt(eye_x, eye_y, eye_z, cx, cy, cz, 0.0, 0.0, 1.0)

def display():
    global WIN_W, WIN_H, popup_msg, popup_until
    glClearColor(0.05,0.06,0.08,1.0); glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
    glViewport(0,0,WIN_W,WIN_H); glMatrixMode(GL_PROJECTION); glLoadIdentity(); gluPerspective(60.0,float(WIN_W)/float(WIN_H),0.1,1000.0)
    glMatrixMode(GL_MODELVIEW); glLoadIdentity()
    draw_skybox()
    _apply_camera()
    draw_lava()

    glColor3f(0.08,0.10,0.12); glPushMatrix(); glTranslatef(0.0,0.0,-0.01); glScalef((2*GRID_SIZE+1)*CELL,(2*GRID_SIZE+1)*CELL,0.02); glutSolidCube(1.0); glPopMatrix()
    draw_ground_grid(); draw_obstacles(); draw_gems(); draw_treasure_boxes(); draw_player_bowl()
    draw_ground_tiles()
    draw_perimeter_pillars()
    draw_hud()
    draw_minimap()
    if popup_msg and time.time() < popup_until:
        draw_text_screen(-0.15, -0.2, popup_msg)
    glutSwapBuffers()

def draw_hud():
    draw_text_screen(-0.95, 0.92, f"Score: {score}")
    draw_text_screen(-0.20, 0.92, f"Time: {int(max(0, remaining))}s")
    draw_text_screen(0.35, 0.92, f"Level: {level}")
    if not running:
        draw_text_screen(-0.18, 0.00, "TIME UP — Press R to Restart")
    if cheat_mode:
        draw_text_screen(-0.95, -0.95, "CHEAT: GEM HIGHLIGHT + GHOST")
    if time.time() < boost_until:
        draw_text_screen(-0.20, -0.95, "SPEED BOOST!")

def try_move(dx: float, dy: float):
    global player_x, player_y
    nx = clamp(player_x + dx, -GRID_SIZE*CELL, GRID_SIZE*CELL)
    ny = clamp(player_y + dy, -GRID_SIZE*CELL, GRID_SIZE*CELL)

    if cheat_mode:
        player_x = nx
        player_y = ny
        return

    blocked_x = False
    blocked_y = False

    i = 0
    while i < len(obstacles):
        ox, oy = obstacles[i]
        top = 1.0
        hit_x = aabb_overlap(nx, player_y, PLAYER_DIAM, ox, oy, OBSTACLE_SIZE)
        hit_y = aabb_overlap(player_x, ny, PLAYER_DIAM, ox, oy, OBSTACLE_SIZE)
        if hit_x or hit_y:
            if time.time() < boost_until:
                breaking_obs.append((ox, oy, 1.0, BREAK_TTL))
                obstacles.pop(i)
                continue
            else:
                if hit_x and player_z < top + PLAYER_RADIUS - CLIMB_MARGIN:
                    blocked_x = True
                if hit_y and player_z < top + PLAYER_RADIUS - CLIMB_MARGIN:
                    blocked_y = True
        i += 1

    for (rx, ry, sx, sy, sz) in obstacles_rect:
        hit_x = rect_overlap(nx, player_y, PLAYER_DIAM, PLAYER_DIAM, rx, ry, sx, sy)
        hit_y = rect_overlap(player_x, ny, PLAYER_DIAM, PLAYER_DIAM, rx, ry, sx, sy)
        if hit_x:
            if player_z < sz + PLAYER_RADIUS - CLIMB_MARGIN:
                blocked_x = True
        if hit_y:
            if player_z < sz + PLAYER_RADIUS - CLIMB_MARGIN:
                blocked_y = True

    for s in slopes:
        sx, sy, sdir, length, width, steps, step_h = s
        if sdir == 'x':
            fx = rect_overlap(nx, player_y, PLAYER_DIAM, PLAYER_DIAM, sx, sy, length, width)
            fy = rect_overlap(player_x, ny, PLAYER_DIAM, PLAYER_DIAM, sx, sy, length, width)
        else:
            fx = rect_overlap(nx, player_y, PLAYER_DIAM, PLAYER_DIAM, sx, sy, width, length)
            fy = rect_overlap(player_x, ny, PLAYER_DIAM, PLAYER_DIAM, sx, sy, width, length)
        if fx:
            hloc = slope_height_at(s, nx, player_y)
            if player_z < hloc + PLAYER_RADIUS - CLIMB_MARGIN:
                blocked_x = True
        if fy:
            hloc = slope_height_at(s, player_x, ny)
            if player_z < hloc + PLAYER_RADIUS - CLIMB_MARGIN:
                blocked_y = True

    if not blocked_x:
        player_x = nx
    if not blocked_y:
        player_y = ny


def collect_overlaps():
    global score, boost_until, gems_collected, popup_msg, popup_until
    to_remove = []
    for i, (x,y,col,pts,is_boost) in enumerate(gems):
        if dist2(x,y,player_x,player_y) <= (PLAYER_RADIUS+GEM_RADIUS)**2:
            if is_boost:
                boost_until = time.time() + BOOST_DURATION
            else:
                score += pts
            to_remove.append(i)
    for i in reversed(to_remove):
        gems.pop(i)
        gems_collected += 1
        spawn_gem()
        if gems_collected % LEVEL_GEMS == 0:
            on_level_up()
    t_remove = []
    for i, (tx, ty, effect) in enumerate(treasure_boxes):
        if dist2(tx, ty, player_x, player_y) <= (PLAYER_RADIUS + 0.8)**2:
            t_remove.append(i)
            if effect == "help":
                score += 50
                popup_msg = "+50 (treasure)"
            else:
                score = max(0, score - 30)
                remaining_reduction = 10
                globals()['remaining'] = max(0.0, remaining - remaining_reduction)
                popup_msg = "-30 & -10s (trap)"
            popup_until = time.time() + 2.0
    for i in reversed(t_remove):
        treasure_boxes.pop(i)
        if random.random() < 0.8:
            spawn_treasure_box()

def update():
    global _last_time, remaining, running, player_speed, player_z, vz, on_ground
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
    player_speed = BASE_SPEED
    if now < boost_until:
        player_speed *= BOOST_MULTIPLIER
    if running:
        move_x = 0.0; move_y = 0.0
        if b"w" in keys: move_y += 1
        if b"s" in keys: move_y -= 1
        if b"a" in keys: move_x += 1
        if b"d" in keys: move_x -= 1
        if move_x != 0 or move_y != 0:
            mag = math.sqrt(move_x*move_x + move_y*move_y)
            move_x /= mag; move_y /= mag
            yaw = math.radians(cam_yaw)
            fwdx = math.cos(yaw); fwdy = math.sin(yaw)
            leftx = -fwdy; lefty = fwdx
            dirx = fwdx*move_y + leftx*move_x
            diry = fwdy*move_y + lefty*move_x
            try_move(dirx * player_speed * dt, diry * player_speed * dt)
    if in_lava(player_x, player_y):
        player_speed *= LAVA_SLOW_MULT
        globals()['lava_dmg_accum'] = lava_dmg_accum + LAVA_DPS * dt
        dec = int(lava_dmg_accum)
        if dec > 0:
            globals()['score'] = max(0, score - dec)
            globals()['lava_dmg_accum'] = lava_dmg_accum - dec

    k = len(lava_pools) - 1
    while k >= 0:
        lx, ly, lr, lt = lava_pools[k]
        lt -= dt
        if lt <= 0.0:
            lava_pools.pop(k)
        else:
            lava_pools[k] = (lx, ly, lr, lt)
        k -= 1

    target_lava = min(MAX_LAVA, LAVA_BASE + level//2)
    while len(lava_pools) < target_lava:
        spawn_lava_pool()


    if not on_ground:
        vz += GRAVITY * dt
        player_z = player_z + vz * dt
        gh = 0.0 if cheat_mode else ground_height_at(player_x, player_y)


        if player_z <= gh + PLAYER_RADIUS + 1e-4:
            player_z = gh + PLAYER_RADIUS
            vz = 0.0
            on_ground = True
    else:
        gh = 0.0 if cheat_mode else ground_height_at(player_x, player_y)


        player_z = gh + PLAYER_RADIUS
    
    collect_overlaps()
    if random.random() < 0.008 and len(treasure_boxes) < 4:
        spawn_treasure_box()
    

    j = len(breaking_obs) - 1
    while j >= 0:
        bx, by, bs, ttl = breaking_obs[j]
        ttl -= dt
        bs = max(0.0, ttl / BREAK_TTL)
        breaking_obs[j] = (bx, by, bs, ttl)
        if ttl <= 0.0:
            breaking_obs.pop(j)
        j -= 1
    glutPostRedisplay()


def on_key(key: bytes, x: int, y: int):
    global cheat_mode, running, vz, on_ground, cam_dist, camera_mode
    keys.add(key)
    if key == b"c":
        globals()['cheat_mode'] = not globals()['cheat_mode']
    elif key == b"r":
        restart_game()
    elif key == b" ":
        if running and on_ground:
            globals()['on_ground'] = False
            globals()['vz'] = JUMP_V0
    elif key == b"p":
        reset_player_position()
    elif key == b"v":
        camera_mode = 1 - camera_mode
    elif key in (b'+', b'=',):
        globals()['cam_dist'] = clamp(globals()['cam_dist'] - CAM_ZOOM_STEP, CAM_DIST_MIN, CAM_DIST_MAX)
    elif key in (b'-', b'_',):
        globals()['cam_dist'] = clamp(globals()['cam_dist'] + CAM_ZOOM_STEP, CAM_DIST_MIN, CAM_DIST_MAX)
    elif key == b'q':
        os._exit(0)



def on_key_up(key: bytes, x: int, y: int):
    if key in keys:
        keys.remove(key)

def on_special(key: int, x: int, y: int):
    global cam_yaw, cam_pitch
    if key == GLUT_KEY_LEFT:
        cam_yaw += 4
    elif key == GLUT_KEY_RIGHT:
        cam_yaw -= 4
    elif key == GLUT_KEY_UP:
        cam_pitch = clamp(cam_pitch - 3, -35.0, 70.0)
    elif key == GLUT_KEY_DOWN:
        cam_pitch = clamp(cam_pitch + 3, -35.0, 70.0)

def restart_game():
    global player_x, player_y, player_z, vz, on_ground, player_speed, boost_until
    global score, level, remaining, running, gems_collected, _last_time, cam_yaw, cam_pitch, cam_dist
    player_x = 0.0; player_y = 0.0; player_z = PLAYER_RADIUS; vz = 0.0; on_ground = True
    player_speed = BASE_SPEED; boost_until = 0.0
    score = 0; level = 1; remaining = START_TIME; running = True; gems_collected = 0
    cam_yaw = 0.0; cam_pitch = 10.0; cam_dist = 12.0
    _last_time = None
    setup_initial_spawns()

def reset_player_position():
    global player_x, player_y, player_z, vz, on_ground
    player_x = 0.0
    player_y = 0.0
    player_z = PLAYER_RADIUS
    vz = 0.0
    on_ground = True


def reshape(w: int, h: int):
    global WIN_W, WIN_H
    WIN_W = max(200, w); WIN_H = max(200, h)
    glViewport(0, 0, WIN_W, WIN_H)

def init_gl():
    glEnable(GL_DEPTH_TEST); glDepthFunc(GL_LEQUAL); glClearDepth(1.0); glShadeModel(GL_SMOOTH)

def main():
    glutInit()
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGBA | GLUT_DEPTH)
    glutInitWindowSize(WIN_W, WIN_H)
    glutInitWindowPosition(50, 50)
    glutCreateWindow(b"Gem Catcher - Full Feature Build")
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
