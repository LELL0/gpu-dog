#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the dog sprites for GPU Cat (resources/icons/dog/...).

The dog is assembled from filled primitives (tapered capsules, circles,
rotated ellipses). Every primitive is emitted as a <path> with a fill only:
GNOME Shell recolors symbolic icons by overriding `fill` on path/rect/circle,
so strokes or <ellipse> elements would keep their original color.

Usage: python3 tools/make-dog-sprites.py [--build NAME] [OUTPUT_ROOT]
OUTPUT_ROOT defaults to resources/icons/dog next to this script's parent.
NAME is one of BUILDS (default: DEFAULT_BUILD).
"""
import math
import os
import sys

SIZE = 388
FILL = '#bebebe'


def f(v):
	return f'{v:.1f}'.rstrip('0').rstrip('.')


def circle(cx, cy, r):
	return (f'M {f(cx + r)},{f(cy)} A {f(r)},{f(r)} 0 1 0 {f(cx - r)},{f(cy)} '
		f'A {f(r)},{f(r)} 0 1 0 {f(cx + r)},{f(cy)} Z')


def ellipse(cx, cy, rx, ry, rot=0.0):
	t = math.radians(rot)
	dx, dy = rx * math.cos(t), rx * math.sin(t)
	return (f'M {f(cx + dx)},{f(cy + dy)} A {f(rx)},{f(ry)} {f(rot)} 1 0 {f(cx - dx)},{f(cy - dy)} '
		f'A {f(rx)},{f(ry)} {f(rot)} 1 0 {f(cx + dx)},{f(cy + dy)} Z')


def capsule(x1, y1, r1, x2, y2, r2):
	"""Convex hull of two circles (a tapered, round-ended bar)."""
	dx, dy = x2 - x1, y2 - y1
	length = math.hypot(dx, dy)
	if length <= abs(r1 - r2) + 1e-6:  # one circle swallows the other
		return circle(x1, y1, r1) if r1 >= r2 else circle(x2, y2, r2)
	theta = math.atan2(dy, dx)
	phi = math.acos((r1 - r2) / length)

	def pt(cx, cy, r, a):
		return cx + r * math.cos(a), cy + r * math.sin(a)

	p1a = pt(x1, y1, r1, theta + phi)
	p2a = pt(x2, y2, r2, theta + phi)
	p2b = pt(x2, y2, r2, theta - phi)
	p1b = pt(x1, y1, r1, theta - phi)
	large2 = 1 if 2 * phi > math.pi else 0
	large1 = 1 if 2 * math.pi - 2 * phi > math.pi else 0
	return (f'M {f(p1a[0])},{f(p1a[1])} L {f(p2a[0])},{f(p2a[1])} '
		f'A {f(r2)},{f(r2)} 0 {large2} 0 {f(p2b[0])},{f(p2b[1])} '
		f'L {f(p1b[0])},{f(p1b[1])} '
		f'A {f(r1)},{f(r1)} 0 {large1} 0 {f(p1a[0])},{f(p1a[1])} Z')


def curve(p0, p1, p2, r0, r1, steps=6):
	"""Tapered thick quadratic curve, as overlapping capsules."""
	pts = []
	for i in range(steps + 1):
		t = i / steps
		x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
		y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
		pts.append((x, y, r0 + (r1 - r0) * t))
	return [capsule(*a, *b) for a, b in zip(pts, pts[1:])]


def rotate(px, py, cx, cy, deg):
	t = math.radians(deg)
	x, y = px - cx, py - cy
	return cx + x * math.cos(t) - y * math.sin(t), cy + x * math.sin(t) + y * math.cos(t)


def leg(jx, jy, upper, lower, l1, l2, r_top, r_knee, r_paw, paw_dir=1, paw_len=14):
	"""Two-segment leg. Angles in degrees from straight down, positive = forward (+x)."""
	a1, a2 = math.radians(upper), math.radians(lower)
	kx, ky = jx + l1 * math.sin(a1), jy + l1 * math.cos(a1)
	px, py = kx + l2 * math.sin(a2), ky + l2 * math.cos(a2)
	parts = [capsule(jx, jy, r_top, kx, ky, r_knee), capsule(kx, ky, r_knee * 0.85, px, py, r_paw)]
	# paw: short pad pointing forward, perpendicular-ish to the lower leg
	fx = px + paw_len * math.cos(a2) * paw_dir
	fy = py - paw_len * math.sin(a2) * paw_dir
	parts.append(capsule(px, py, r_paw, fx, fy, r_paw * 0.85))
	return parts


# Running poses: body tilt (deg, + = nose up), vertical offset, tail wag,
# then (upper, lower) angles for front-near, front-far, hind-near, hind-far.
POSES = [
	# 0: full extension, airborne
	dict(tilt=0, dy=-14, tail=-8, fn=(62, 78), ff=(48, 70), hn=(-58, -78), hf=(-44, -66)),
	# 1: front paw lands, hind legs swing forward
	dict(tilt=-4, dy=-2, tail=0, fn=(18, 8), ff=(40, 48), hn=(-30, -72), hf=(-12, -70)),
	# 2: gathered, all paws under the body
	dict(tilt=-2, dy=6, tail=8, fn=(-22, -40), ff=(-6, -18), hn=(42, -6), hf=(28, -22)),
	# 3: hind push off, front legs fold back
	dict(tilt=5, dy=0, tail=4, fn=(-12, -95), ff=(8, -80), hn=(-8, -20), hf=(-28, -40)),
	# 4: front legs reach forward, hind legs extend
	dict(tilt=3, dy=-10, tail=-4, fn=(42, -20), ff=(56, 30), hn=(-42, -62), hf=(-54, -74)),
]


# Body builds. 'lean' reproduces the original running sprites exactly; the others are
# variations in girth and breed. Unset keys fall back to BASE (the lean dog).
#   torso: (rx, ry) at torso_x; chest/rump: radius at chest_x/rump_x
#   belly: extra ellipse (dx, dy, rx, ry) under the torso, or None
#   leg_len/leg_w: scale leg length/thickness; leg_dy: lower the leg joints
#   drop: lower the whole body (short legs still reach the ground)
#   head_at: head center; head: radius; neck: (shoulder r, head r)
#   eye_at: eye offset from the head center; eye: radius
#   cheek: jowl circle (dx, dy, r) from the head center, or None
#   muzzle: (dx1, dy1, r1, dx2, dy2, r2), nose: (dx, dy, r) from the head center;
#   s_muzzle/s_nose: the same for the sleeping head
#   ear: ('floppy', r0, r1, dx, dy) | ('pointy', size)
#   tail: ('long',) | ('curl', radius) | ('stub', length)
#   view: (scale, cx, cy) zooms the canvas out around (cx, cy), or None
# Nothing may overlap the eye hole: shapes drawn under the head show through it.
BASE = dict(torso=(98, 44), torso_x=186, chest=48, chest_x=246, rump=44, rump_x=120, belly=None,
	leg_len=1.0, leg_w=1.0, leg_dy=0, drop=0, head_at=(312, 128), head=36, neck=(40, 24),
	eye_at=(10, -14), eye=8, cheek=None, muzzle=(28, 12, 21, 54, 22, 15), nose=(58, 15, 11),
	s_muzzle=(24, 14, 19, 60, 24, 14), s_nose=(64, 18, 10), muzzle_w=1.0,
	ear=('floppy', 16, 13, -54, -16), tail=('long',), tail_w=1.0, s_rx=0, view=None)

BUILDS = {name: {**BASE, **over} for name, over in {
	'lean': {},
	'plump': dict(torso=(100, 52), chest=54, rump=51, belly=(0, 16, 72, 36), leg_len=0.94, leg_w=1.15,
		drop=5, neck=(45, 26), head=38, cheek=(-8, 20, 22), eye=8.5, tail_w=1.1, muzzle_w=1.04),
	'round': dict(torso=(100, 60), chest=60, rump=58, belly=(-2, 24, 80, 42), leg_len=0.86, leg_w=1.28,
		drop=12, neck=(50, 27), head=40, cheek=(-10, 22, 25), eye=9, tail_w=1.2, muzzle_w=1.05),
	'chonk': dict(torso=(98, 70), chest=66, rump=64, belly=(-4, 30, 86, 48), leg_len=0.78, leg_w=1.4,
		drop=19, neck=(54, 28), head=42, cheek=(-12, 24, 28), eye=9.5, tail_w=1.3, muzzle_w=1.05),
	'puppy': dict(torso=(94, 56), chest=56, rump=54, belly=(-2, 20, 72, 38), leg_len=0.86, leg_w=1.3,
		drop=10, neck=(46, 26), head=46, cheek=(-8, 24, 26), eye=10.5, tail_w=1.15),
	# long low loaf, stubby legs, big upright ears, no tail to speak of
	'corgi': dict(torso=(112, 52), torso_x=180, chest=54, chest_x=262, rump=54, rump_x=104,
		belly=(0, 18, 92, 36), leg_len=0.58, leg_w=1.35, leg_dy=10, drop=16, head_at=(320, 136),
		head=40, neck=(48, 28), cheek=(-6, 20, 23), eye=9, muzzle=(28, 12, 19, 56, 22, 11),
		nose=(60, 16, 10), s_muzzle=(24, 14, 17, 58, 24, 11), s_nose=(62, 18, 9),
		ear=('pointy', 1.6), tail=('stub', 18), tail_w=1.2, s_rx=14, view=(0.9, 194, 184)),
	# fluffy round body, pointed ears, tail curled over the back
	'shiba': dict(torso=(98, 56), chest=56, rump=54, belly=(-2, 18, 74, 36), leg_len=0.88, leg_w=1.22,
		drop=8, neck=(48, 28), head=40, cheek=(-6, 20, 24), eye=8.5, muzzle=(28, 12, 20, 54, 22, 13),
		nose=(58, 15, 10), s_muzzle=(24, 14, 17, 58, 24, 11), s_nose=(62, 18, 9),
		ear=('pointy', 1.0), tail=('curl', 26), tail_w=1.1, view=(0.94, 194, 190)),
	# barrel body, big round head, flat face, button ears, corkscrew tail
	'pug': dict(torso=(86, 58), torso_x=192, chest=60, chest_x=248, rump=56, rump_x=134,
		belly=(-2, 20, 70, 40), leg_len=0.74, leg_w=1.32, drop=14, head_at=(302, 134), head=48,
		neck=(52, 26), cheek=(2, 24, 26), eye_at=(14, -12), eye=10.5, muzzle=(40, 14, 20, 52, 18, 17),
		nose=(58, 10, 9), s_muzzle=(38, 12, 18, 44, 16, 16), s_nose=(52, 10, 9),
		ear=('floppy', 13, 11, -44, -30), tail=('curl', 16), tail_w=0.8),
	# kawaii bean: one soft blob, head merged in, tiny legs
	'mochi': dict(torso=(92, 74), torso_x=180, chest=64, chest_x=232, rump=64, rump_x=128,
		belly=None, leg_len=0.46, leg_w=1.45, leg_dy=36, drop=6, head_at=(296, 140), head=52,
		neck=(60, 22), eye_at=(8, -12), eye=11, muzzle=(34, 16, 20, 46, 22, 16), nose=(52, 14, 10),
		s_muzzle=(30, 16, 18, 42, 22, 14), s_nose=(48, 14, 9), ear=('pointy', 0.55),
		tail=('stub', 16), tail_w=1.2),
	# chubby sausage: long belly, tiny legs, long ears, long nose
	'sausage': dict(torso=(124, 50), torso_x=184, chest=54, chest_x=272, rump=52, rump_x=100,
		belly=(0, 18, 96, 34), leg_len=0.52, leg_w=1.3, leg_dy=14, drop=6, head_at=(334, 150),
		head=38, neck=(46, 25), cheek=(-8, 20, 22), eye=8.5, muzzle=(28, 12, 20, 60, 22, 13),
		nose=(64, 15, 10), ear=('floppy', 17, 18, -50, 8), tail_w=0.9, s_rx=26,
		view=(0.86, 194, 200)),
}.items()}
DEFAULT_BUILD = 'plump'


def rpoly(pts, rad):
	"""Closed polygon with corners rounded by quadratic curves."""
	n = len(pts)
	d = []
	for i in range(n):
		(x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[(i + 1) % n]

		def toward(ax, ay, bx, by):
			length = math.hypot(bx - ax, by - ay)
			t = min(rad / length, 0.5)
			return ax + (bx - ax) * t, ay + (by - ay) * t

		a, c = toward(x1, y1, x0, y0), toward(x1, y1, x2, y2)
		d.append(f'{"M" if i == 0 else "L"} {f(a[0])},{f(a[1])} Q {f(x1)},{f(y1)} {f(c[0])},{f(c[1])}')
	return ' '.join(d) + ' Z'


def polar(cx, cy, r, deg):
	t = math.radians(deg)
	return cx + r * math.cos(t), cy + r * math.sin(t)


def ears(b, H, sway):
	"""Ear shapes for the head at H (a function mapping head-local offsets to
	canvas points, already rotated with the body)."""
	kind = b['ear'][0]
	r = b['head']
	if kind == 'floppy':
		_, r0, r1, ex, ey = b['ear']
		return [capsule(*H(-14, -28), r0, *H(ex, ey + sway), r1)]
	# pointy: (far, near) triangles standing up from the skull, given as
	# base angles on the head, tip angle and tip distance
	size = b['ear'][1]
	out = []
	for a1, a2, at, reach in ((-164, -116, -146, 0.62), (-134, -72, -108, 0.74)):
		base1 = polar(0, 0, r * 0.88, a1)
		base2 = polar(0, 0, r * 0.88, a2)
		tip = polar(0, 0, r * (1 + reach * size), at)
		out.append(rpoly([H(*base1), H(tip[0] - sway * 0.4, tip[1]), H(*base2)], 9))
	return out


def eye_pos(pose, b):
	tilt, dy = pose['tilt'], pose['dy'] + b['drop']
	hx, hy = b['head_at']
	return rotate(hx + b['eye_at'][0], hy + b['eye_at'][1] + dy, 190, 196 + dy, -tilt)


def running_dog(pose, b=BUILDS['lean']):
	tilt, dy = pose['tilt'], pose['dy'] + b['drop']
	cx, cy = 190, 196 + dy  # body center; everything rotates around it

	def R(x, y):
		return rotate(x, y + dy, cx, cy, -tilt)

	hx0, hy0 = b['head_at']

	def H(x, y):
		return R(hx0 + x, hy0 + y)

	L, W = b['leg_len'], b['leg_w']
	shapes = []
	# far legs first (same color, purely for overlap order clarity)
	sx, sy = R(b['chest_x'] + 6, 214 + b['leg_dy'])
	hx, hy = R(b['rump_x'] - 2, 206 + b['leg_dy'])
	shapes += leg(sx - 8, sy, *pose['ff'], 56 * L, 52 * L, 19 * W, 14 * W, 12 * W)
	shapes += leg(hx - 8, hy, *pose['hf'], 52 * L, 56 * L, 24 * W, 14 * W, 12 * W)

	# torso: deep chest, slimmer waist, round rump
	shapes.append(ellipse(*R(b['torso_x'], 196), *b['torso'], -tilt))
	shapes.append(circle(*R(b['chest_x'], 202), b['chest']))
	shapes.append(circle(*R(b['rump_x'], 192), b['rump']))
	if b['belly']:
		bdx, bdy, brx, bry = b['belly']
		shapes.append(ellipse(*R(b['torso_x'] + bdx, 196 + bdy), brx, bry, -tilt))

	# neck + head (eye is an evenodd hole, so nothing else may cover it)
	shapes.append(capsule(*R(b['chest_x'] + 12, 188), b['neck'][0], *H(-18, 12), b['neck'][1]))
	if b['cheek']:
		chx, chy, chr_ = b['cheek']
		shapes.append(circle(*H(chx, chy), chr_))
	shapes.append(circle(*H(0, 0), b['head']) + ' ' + circle(*H(*b['eye_at']), b['eye']))
	m1x, m1y, m1r, m2x, m2y, m2r = b['muzzle']
	mw = b['muzzle_w']
	shapes.append(capsule(*H(m1x, m1y), m1r * mw, *H(m2x, m2y), m2r * mw))  # muzzle
	shapes.append(circle(*H(b['nose'][0], b['nose'][1]), b['nose'][2]))  # nose
	shapes += ears(b, H, pose['tail'] * 0.8)

	# tail, wagging a little
	tw = b['tail_w']
	rx = b['rump_x']
	kind = b['tail'][0]
	if kind == 'long':  # curls up and back
		t0 = R(rx - 24, 178)
		t1 = R(rx - 68, 168 + pose['tail'])
		t2 = R(rx - 80, 116 + pose['tail'] * 2)
		shapes += curve(t0, t1, t2, 15 * tw, 9 * tw)
	elif kind == 'curl':  # ring resting on the back
		cr = b['tail'][1]
		ccx, ccy = rx + 2 - pose['tail'] * 0.3, 192 - b['rump'] - cr * 0.45 + pose['tail'] * 0.4
		pts = [polar(ccx, ccy, cr, a) for a in range(160, 501, 34)]
		pts.insert(0, (rx - b['rump'] * 0.55, 192 - b['rump'] * 0.6))
		w0, w1 = 16 * tw, 9 * tw
		for i in range(len(pts) - 1):
			t0, t1 = i / (len(pts) - 1), (i + 1) / (len(pts) - 1)
			shapes.append(capsule(*R(*pts[i]), w0 + (w1 - w0) * t0, *R(*pts[i + 1]), w0 + (w1 - w0) * t1))
	elif kind == 'stub':
		ln = b['tail'][1]
		bx, by = rx - b['rump'] * 0.7, 192 - b['rump'] * 0.55
		shapes.append(capsule(*R(bx, by), 14 * tw, *R(bx - ln, by - ln * 0.5 + pose['tail'] * 0.6), 11 * tw))

	# near legs
	shapes += leg(sx, sy, *pose['fn'], 56 * L, 52 * L, 20 * W, 15 * W, 13 * W)
	shapes += leg(hx, hy, *pose['hn'], 52 * L, 56 * L, 26 * W, 15 * W, 13 * W)
	return shapes


SLEEP_FRAMES = 8  # one slow breath per idle cycle (IDLE_ANIMATION_CYCLE_DURATION_MS)
GROUND = 334


def zee(cx, cy, size, tilt=-12):
	"""A soft 'Z' glyph of height `size` centered on (cx, cy)."""
	h, w = size / 2, size * 0.42
	t, d = size * 0.24, size * 0.34  # bar thickness, diagonal width
	pts = [(-w, -h), (w, -h), (w, -h + t), (-w + d, h - t), (w, h - t), (w, h),
		(-w, h), (-w, h - t), (w - d, -h + t), (-w, -h + t)]
	return rpoly([rotate(cx + x, cy + y, cx, cy, tilt) for x, y in pts], size * 0.07)


def closed_eye(cx, cy, size):
	"""Sleepy eye: a downward crescent, cut as an evenodd hole."""
	w = size * 1.4
	return (f'M {f(cx - w)},{f(cy)} Q {f(cx)},{f(cy + size * 1.5)} {f(cx + w)},{f(cy)} '
		f'Q {f(cx)},{f(cy + size * 0.6)} {f(cx - w)},{f(cy)} Z')


def sleeping_dog(b=BUILDS['lean'], i=0, n=1):
	"""Lying down, chin resting on the front paws. Frame i of n: the back
	rises and falls with a slow breath while Zs drift up from the head."""
	br = math.sin(2 * math.pi * i / n) if n > 1 else 0.0
	g = b['torso'][1] - 44  # extra girth over the lean build
	W, tw, sx = b['leg_w'], b['tail_w'], b['s_rx']
	shapes = []

	# far front paw, slightly behind the near one
	shapes.append(capsule(232, GROUND - 26, 13 * W, 334, GROUND - 24, 12 * W))
	# body: belly stays on the ground, the back breathes
	ry = 34 + g + 5 * br
	shapes.append(ellipse(164 + sx * 0.3, GROUND - 4 - ry, 104 + g * 0.3 + sx, ry))
	shapes.append(circle(236, GROUND - 40, 38 + g * 0.5 + br))  # chest
	hr = 52 + g * 0.7 + 2 * br
	hcx, hcy = 92 - sx * 0.4, GROUND - 6 - hr
	shapes.append(circle(hcx, hcy, hr))  # haunch
	shapes.append(capsule(hcx, GROUND - 14, 14 * W, hcx + 72, GROUND - 12, 13 * W))  # hind paw
	kind = b['tail'][0]
	if kind == 'long':  # wrapped around the front of the haunch
		shapes += curve((hcx - 42, GROUND - 38), (hcx - 88, GROUND - 6), (hcx - 4, GROUND - 6), 14 * tw, 9 * tw)
	elif kind == 'curl':  # ring on top of the haunch
		cr = b['tail'][1] * 0.9
		ccx, ccy = hcx + 6, hcy - hr - cr * 0.3
		pts = [(hcx - hr * 0.5, hcy - hr * 0.6)] + [polar(ccx, ccy, cr, a) for a in range(160, 501, 34)]
		w0, w1 = 15 * tw, 8 * tw
		for k in range(len(pts) - 1):
			t0, t1 = k / (len(pts) - 1), (k + 1) / (len(pts) - 1)
			shapes.append(capsule(*pts[k], w0 + (w1 - w0) * t0, *pts[k + 1], w0 + (w1 - w0) * t1))
	elif kind == 'stub':
		bx, by = hcx - hr * 0.8, hcy - hr * 0.3
		shapes.append(capsule(bx, by, 13 * tw, bx - b['tail'][1], by - 4, 10 * tw))

	# big round head resting on the paws, standing clear of the back
	hx, hy, r = 296, GROUND - 78, b['head'] + 8
	shapes.append(capsule(236, GROUND - 14, 15 * W, 350, GROUND - 12, 13 * W))  # near front paw
	if b['cheek']:
		chx, chy, chr_ = b['cheek']
		shapes.append(circle(hx + chx, hy + chy * 0.8, chr_ * 0.9))
	shapes.append(circle(hx, hy, r) + ' ' + closed_eye(hx + 10, hy - 8, b['eye']))
	m1x, m1y, m1r, m2x, m2y, m2r = b['s_muzzle']
	mw = b['muzzle_w']
	shapes.append(capsule(hx + m1x, hy + m1y, m1r * mw, hx + m2x, hy + m2y, m2r * mw))  # muzzle
	shapes.append(circle(hx + b['s_nose'][0], hy + b['s_nose'][1], b['s_nose'][2]))  # nose
	if b['ear'][0] == 'floppy':  # hanging down the back of the head
		k = b['ear'][1] / 16
		shapes.append(capsule(hx - 22, hy - 24, 16 * k, hx - 40, hy + 22 * k, 13 * k))
	else:
		shapes += ears({**b, 'head': r}, lambda x, y: (hx + x, hy + y), 0)

	# three Zs drifting up and growing; each frame moves them one step along
	for k in range(3):
		p = (i / n + k / 3) % 1
		shapes.append(zee(262 + 92 * p + 6 * math.sin(2 * math.pi * p), 196 - 158 * p, 24 + 36 * p))
	return shapes


def svg(title, shapes, view=None):
	paths = '\n'.join(
		f'    <path fill-rule="evenodd" style="fill:{FILL};" d="{d}"/>' for d in shapes)
	vb = ''
	if view:
		scale, vx, vy = view
		half = SIZE / 2 / scale
		vb = f' viewBox="{f(vx - half)} {f(vy - half)} {f(2 * half)} {f(2 * half)}"'
	return (f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
		f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{SIZE}" height="{SIZE}"{vb}>\n'
		f'    <title>{title}</title>\n{paths}\n</svg>\n')


def main():
	here = os.path.dirname(os.path.abspath(__file__))
	args = sys.argv[1:]
	build = DEFAULT_BUILD
	if '--build' in args:
		i = args.index('--build')
		build = args[i + 1]
		del args[i:i + 2]
	b = BUILDS[build]
	root = args[0] if args else os.path.join(here, '..', 'resources', 'icons', 'dog')
	os.makedirs(os.path.join(root, 'active'), exist_ok=True)
	os.makedirs(os.path.join(root, 'idle'), exist_ok=True)
	for state in ('active', 'idle'):  # drop stale frames from earlier runs
		for name in os.listdir(os.path.join(root, state)):
			if name.startswith('sprite-') and name.endswith('-symbolic.svg'):
				os.remove(os.path.join(root, state, name))
	for i, pose in enumerate(POSES):
		with open(os.path.join(root, 'active', f'sprite-{i}-symbolic.svg'), 'w') as fh:
			fh.write(svg(f'GPU Dog: Frame {i}', running_dog(pose, b), view=b['view']))
	for i in range(SLEEP_FRAMES):
		with open(os.path.join(root, 'idle', f'sprite-{i}-symbolic.svg'), 'w') as fh:
			fh.write(svg(f'GPU Dog: Sleeping {i}', sleeping_dog(b, i, SLEEP_FRAMES), view=b['view']))


if __name__ == '__main__':
	main()
