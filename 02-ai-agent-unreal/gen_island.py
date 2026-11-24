"""Generate a realistic island heightmap (505x505, 1 m/px) as .r16 + preview PNG.
World: landscape origin at (-252m,-252m), z scale 100 -> 1 unit = 0.78125 cm, 32768 = z 0 (sea level).
"""
import math, random, struct, zlib, sys, array

N = 505
HALF = 252.0
random.seed(7)

# ---------- value noise ----------
PERM = list(range(256)); random.shuffle(PERM); PERM += PERM
GRAD = [random.random() for _ in range(256)]

def _h(ix, iy):
    return GRAD[PERM[(PERM[ix & 255] + iy) & 255]]

def vnoise(x, y):
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    ux = fx * fx * (3 - 2 * fx); uy = fy * fy * (3 - 2 * fy)
    a = _h(ix, iy); b = _h(ix + 1, iy); c = _h(ix, iy + 1); d = _h(ix + 1, iy + 1)
    return (a + (b - a) * ux) * (1 - uy) + (c + (d - c) * ux) * uy  # 0..1

def fbm(x, y, oct=5, lac=2.03, gain=0.5):
    s = 0.0; amp = 1.0; f = 1.0; norm = 0.0
    for o in range(oct):
        s += amp * (vnoise(x * f + o * 17.3, y * f - o * 9.1) * 2 - 1)
        norm += amp; amp *= gain; f *= lac
    return s / norm  # ~-1..1

def ridged(x, y, oct=5):
    s = 0.0; amp = 0.5; f = 1.0; prev = 1.0
    for o in range(oct):
        n = 1 - abs(vnoise(x * f + o * 31.7, y * f + o * 7.7) * 2 - 1)
        n = n * n
        s += n * amp * prev
        prev = n; amp *= 0.5; f *= 2.1
    return s  # 0..~1

def smooth(e0, e1, v):
    t = max(0.0, min(1.0, (v - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)

# ---------- design (meters) ----------
LAKE = (-42.0, 38.0, 30.0, 22.0)   # cx, cy, rx, ry
LAKE_LEVEL = 9.0
MTN = (62.0, -48.0)

H = [[0.0] * N for _ in range(N)]
for j in range(N):
    y = j - HALF
    for i in range(N):
        x = i - HALF
        # domain-warped coastline
        wx = x + 28 * fbm(x / 90 + 3.1, y / 90 - 1.7, 4)
        wy = y + 28 * fbm(x / 90 - 5.2, y / 90 + 2.4, 4)
        r = math.sqrt((wx / 140) ** 2 + (wy / 118) ** 2)
        r += 0.10 * fbm(x / 35, y / 35, 4)
        c = 1.0 - r  # >0 land
        if c < 0:
            depth = 1.0 + 26 * smooth(0.0, 0.45, -c)
            h = -depth + 1.2 * fbm(x / 20, y / 20, 3)
        else:
            beach = 1.4 * smooth(0.0, 0.08, c)
            inland = smooth(0.07, 0.55, c)
            rolling = (9 + 6 * fbm(x / 55 + 9, y / 55 - 4, 5)) * inland
            dx, dy = x - MTN[0], y - MTN[1]
            m = math.exp(-(dx * dx + dy * dy) / (2 * 48.0 ** 2))
            mountain = m * (34 + 26 * ridged(x / 60 + 2, y / 60 + 5, 5))
            detail = 2.2 * fbm(x / 12, y / 12, 4) * inland
            h = beach + rolling + mountain * smooth(0.05, 0.35, c) + detail
        H[j][i] = h
    if j % 100 == 0:
        print('base row', j, flush=True)

# ---------- hydraulic erosion (droplets) ----------
def grad_h(px, py):
    ix, iy = int(px), int(py)
    fx, fy = px - ix, py - iy
    h00 = H[iy][ix]; h10 = H[iy][ix + 1]; h01 = H[iy + 1][ix]; h11 = H[iy + 1][ix + 1]
    gx = (h10 - h00) * (1 - fy) + (h11 - h01) * fy
    gy = (h01 - h00) * (1 - fx) + (h11 - h10) * fx
    h = h00 * (1 - fx) * (1 - fy) + h10 * fx * (1 - fy) + h01 * (1 - fx) * fy + h11 * fx * fy
    return h, gx, gy

def deposit(px, py, amt):
    ix, iy = int(px), int(py); fx, fy = px - ix, py - iy
    H[iy][ix] += amt * (1 - fx) * (1 - fy); H[iy][ix + 1] += amt * fx * (1 - fy)
    H[iy + 1][ix] += amt * (1 - fx) * fy; H[iy + 1][ix + 1] += amt * fx * fy

def erode_at(px, py, amt):
    # 3x3 brush
    ix, iy = int(px), int(py)
    w = []
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            qx, qy = ix + ox, iy + oy
            if 1 <= qx < N - 1 and 1 <= qy < N - 1:
                d = math.hypot(qx - px, qy - py)
                w.append((qx, qy, max(0.0, 1.6 - d)))
    tot = sum(v for _, _, v in w) or 1.0
    for qx, qy, v in w:
        H[qy][qx] -= amt * v / tot

INERTIA, CAP, MINSLOPE, DEP, ERO, EVAP, GRAV = 0.05, 4.0, 0.01, 0.3, 0.3, 0.02, 4.0
DROPS = int(sys.argv[1]) if len(sys.argv) > 1 else 60000
for d in range(DROPS):
    # spawn on land only
    px = random.uniform(110, 395); py = random.uniform(120, 385)
    if H[int(py)][int(px)] < 5.0:
        continue
    dx = dy = 0.0; speed = 1.0; water = 1.0; sed = 0.0
    for step in range(45):
        h, gx, gy = grad_h(px, py)
        dx = dx * INERTIA - gx * (1 - INERTIA); dy = dy * INERTIA - gy * (1 - INERTIA)
        l = math.hypot(dx, dy)
        if l < 1e-9:
            break
        dx /= l; dy /= l
        nx, ny = px + dx, py + dy
        if not (1 <= nx < N - 2 and 1 <= ny < N - 2):
            break
        nh = grad_h(nx, ny)[0]
        dh = nh - h
        cap = max(-dh, MINSLOPE) * speed * water * CAP
        if sed > cap or dh > 0:
            amt = min(dh, sed) if dh > 0 else (sed - cap) * DEP
            sed -= amt; deposit(px, py, amt)
        else:
            amt = min((cap - sed) * ERO, -dh)
            erode_at(px, py, amt); sed += amt
        speed = math.sqrt(max(0.0, speed * speed - dh * GRAV))
        water *= (1 - EVAP)
        px, py = nx, ny
        if nh < 2.5:  # reached beach: stop
            break
    if d % 10000 == 0:
        print('drop', d, flush=True)

# ---------- thermal smoothing (talus) ----------
TALUS = 1.1
for it in range(6):
    for j in range(1, N - 1):
        row = H[j]
        for i in range(1, N - 1):
            h = row[i]
            for (qi, qj) in ((i + 1, j), (i, j + 1)):
                d = h - H[qj][qi]
                if d > TALUS:
                    mv = (d - TALUS) * 0.25
                    row[i] -= mv; H[qj][qi] += mv; h = row[i]
                elif -d > TALUS:
                    mv = (-d - TALUS) * 0.25
                    row[i] += mv; H[qj][qi] -= mv; h = row[i]

# ---------- lake: raise rim/plateau, carve basin ----------
lcx, lcy, lrx, lry = LAKE
samp = sorted(H[int(lcy + HALF + dy)][int(lcx + HALF + dx)] for dx in range(-25, 26, 5) for dy in range(-18, 19, 6))
LAKE_LEVEL = samp[len(samp) // 3]
print('lake level m', round(LAKE_LEVEL, 2))
for j in range(N):
    y = j - HALF
    for i in range(N):
        x = i - HALF
        wx = x + 6 * fbm(x / 25 + 40, y / 25, 3)
        wy = y + 6 * fbm(x / 25, y / 25 + 40, 3)
        q = math.sqrt(((wx - lcx) / lrx) ** 2 + ((wy - lcy) / lry) ** 2)
        if q < 2.2:
            h = H[j][i]
            rim = LAKE_LEVEL + 0.5 + 2.0 * smooth(1.0, 1.8, q)
            blend = 1 - smooth(1.15, 1.8, q)
            h = h + (max(h, rim) - h) * blend          # make sure the rim holds water
            if q < 1.0:
                bed = LAKE_LEVEL - 0.4 - 5.5 * (1 - q * q) ** 0.7
                h = bed
            elif q < 1.25:
                t = smooth(1.0, 1.25, q)
                h = (LAKE_LEVEL - 0.4) * (1 - t) + h * t
            H[j][i] = h

# ---------- write r16 + stats ----------
mn = min(min(r) for r in H); mx = max(max(r) for r in H)
print('height range m', round(mn, 2), round(mx, 2))
out = array.array('H')
for j in range(N):
    for i in range(N):
        v = int(round(32768 + H[j][i] * 100 * 128 / 100))
        out.append(max(0, min(65535, v)))
dst = sys.argv[2] if len(sys.argv) > 2 else 'island.r16'
with open(dst, 'wb') as f:
    if sys.byteorder != 'little':
        out.byteswap()
    out.tofile(f)

# ---------- preview: hillshade + color ----------
def png(path, w, h, rows):
    raw = b''.join(b'\x00' + bytes(r) for r in rows)
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))
rows = []
for j in range(N - 1, -1, -1):  # flip so +Y is up in the image
    r = []
    for i in range(N):
        h = H[j][i]
        hx = H[j][min(i + 1, N - 1)] - H[j][max(i - 1, 0)]
        hy = H[min(j + 1, N - 1)][i] - H[max(j - 1, 0)][i]
        shade = max(0.0, min(1.0, 0.6 + 0.35 * (-hx + hy) / 2))
        if h < 0:
            col = (30, 70 + int(60 * max(0, 1 + h / 27)), 120)
        elif h < 2.0:
            col = (205, 185, 140)
        elif h < 30:
            col = (70, 115, 55)
        else:
            col = (120, 110, 100)
        r += [int(c * shade) for c in col]
    rows.append(r)
png(dst.replace('.r16', '_preview.png'), N, N, rows)
print('done', dst)
