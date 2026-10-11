import os
import time
import base64
import tempfile
import shutil
import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from ultralytics import YOLO

# Real-world pitch dimensions in meters (MCC Laws of Cricket)
PITCH_LENGTH_M = 20.12      # 22 yards
PITCH_WIDTH_M = 3.05        # 10 feet
BOWLING_CREASE_W_M = 2.64   # 8 ft 8 in
POPPING_CREASE_OFFSET_M = 1.22 # 4 ft
POPPING_CREASE_W_M = 3.66   # At least 12 ft
WICKET_WIDTH_M = 0.2286     # 9 inches

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
WEIGHTS_PATH = os.path.join(PROJECT_ROOT, "weights", "best.pt")
BALL_WEIGHTS_PATH = os.path.join(PROJECT_ROOT, "weights", "ball_best.pt")
STATIC_DIR = os.path.join(BASE_DIR, "static")
OUTPUTS_DIR = os.path.join(BASE_DIR, "static", "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# Load Stumps Model
print(f"Loading trained stump model from {WEIGHTS_PATH}...")
model = YOLO(WEIGHTS_PATH)
print("Stump model loaded successfully!")

# Load Ball Model
ball_model = None
if os.path.exists(BALL_WEIGHTS_PATH):
    print(f"Loading trained ball model from {BALL_WEIGHTS_PATH}...")
    ball_model = YOLO(BALL_WEIGHTS_PATH)
    print("Ball model loaded successfully!")

# Ball Tracker
import sys
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from ball_tracker.tracker import BallDetector, BallTrajectoryTracker, draw_stroked_text

app = FastAPI(title="Cricket Stump & Ball Vision AI")

def project_point(H, X, Y):
    pt = np.array([X, Y, 1.0], dtype=np.float64)
    res = H @ pt
    if abs(res[2]) < 1e-7:
        return None
    u = res[0] / res[2]
    v = res[1] / res[2]
    return (int(round(u)), int(round(v)))

def draw_three_black_stumps(annotated, x1, y1, x2, y2, color=(15, 15, 15), outline=(245, 245, 245), draw_bails=True):
    """
    Draw 3 realistic black cricket stumps (Off, Middle, Leg) with bails and top caps.
    """
    W = max(int(x2 - x1), 6)
    H = max(int(y2 - y1), 12)

    # Stump width proportional to bounding box
    sw = max(2, int(round(W * 0.16)))
    half_sw = max(1, sw // 2)

    # 3 stump horizontal centers: Left, Middle, Right
    c1 = x1 + half_sw + max(0, int(round(W * 0.04)))
    c2 = int(round((x1 + x2) / 2.0))
    c3 = x2 - half_sw - max(0, int(round(W * 0.04)))

    bail_h = max(2, int(round(H * 0.038)))
    top_y = y1 + bail_h
    bot_y = y2

    # Draw 3 vertical black stumps
    for cx in [c1, c2, c3]:
        sx1 = cx - half_sw
        sx2 = cx + half_sw
        # Crisp outline for clear visibility on grass / pitch
        cv2.rectangle(annotated, (sx1 - 1, top_y - 1), (sx2 + 1, bot_y + 1), outline, 1, cv2.LINE_AA)
        # Jet black stump core
        cv2.rectangle(annotated, (sx1, top_y), (sx2, bot_y), color, -1)
        # Top cap
        cv2.ellipse(annotated, (cx, top_y), (half_sw, max(1, half_sw // 2)), 0, 0, 360, outline, 1, cv2.LINE_AA)
        cv2.ellipse(annotated, (cx, top_y), (max(0, half_sw - 1), max(0, half_sw // 2 - 1)), 0, 0, 360, color, -1)

    if draw_bails:
        # Bail 1: Left to middle stump
        cv2.rectangle(annotated, (c1 - half_sw, y1), (c2 + half_sw // 2, y1 + bail_h), outline, 1, cv2.LINE_AA)
        cv2.rectangle(annotated, (c1 - half_sw + 1, y1 + 1), (c2 + half_sw // 2 - 1, y1 + bail_h - 1), color, -1)
        # Bail 2: Middle to right stump
        cv2.rectangle(annotated, (c2 - half_sw // 2, y1), (c3 + half_sw, y1 + bail_h), outline, 1, cv2.LINE_AA)
        cv2.rectangle(annotated, (c2 - half_sw // 2 + 1, y1 + 1), (c3 + half_sw - 1, y1 + bail_h - 1), color, -1)

def draw_pitch_zones(annotated, H, PITCH_LENGTH_M, POPPING_CREASE_OFFSET_M=1.22, PITCH_WIDTH_M=3.05, batting_end="far"):
    """
    Divide the pitch from the batting side popping crease (0m) into standard cricket length zones:
    - 0m - 2m: YORKER
    - 2m - 4m: FULL LENGTH
    - 4m - 6m: GOOD LENGTH
    - 6m - 8m: BACK OF A LENGTH
    - 8m+: SHORT / BOUNCER
    """
    def proj(X, Y):
        pt = np.array([X, Y, 1.0], dtype=np.float64)
        res = H @ pt
        if abs(res[2]) < 1e-7: return None
        return (int(round(res[0]/res[2])), int(round(res[1]/res[2])))

    overlay = annotated.copy()
    hw = PITCH_WIDTH_M / 2.0

    if batting_end == "far":
        y_base = PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M
        sign = -1.0
    else:
        y_base = POPPING_CREASE_OFFSET_M
        sign = 1.0

    # Official cricket bowling length zones
    zones = [
        (0.0, 2.0, "YORKER", (220, 60, 180)),
        (2.0, 4.0, "FULL LENGTH", (230, 150, 30)),
        (4.0, 6.0, "GOOD LENGTH", (40, 200, 50)),
        (6.0, 8.0, "BACK OF A LENGTH", (20, 190, 240)),
        (8.0, 10.5, "SHORT PITCH", (40, 50, 230))
    ]

    dividing_lines = [0.0, 2.0, 4.0, 6.0, 8.0]

    # 1. Fill pitch zone polygons with translucent tint
    for d_start, d_end, name, color in zones:
        y1 = y_base + sign * d_start
        y2 = y_base + sign * d_end
        p1 = proj(-hw, y1)
        p2 = proj(+hw, y1)
        p3 = proj(+hw, y2)
        p4 = proj(-hw, y2)

        if all([p1, p2, p3, p4]):
            poly = np.array([p1, p2, p3, p4], dtype=np.int32)
            cv2.fillPoly(overlay, [poly], color)

    cv2.addWeighted(overlay, 0.32, annotated, 0.68, 0, annotated)

    # 2. Draw white pitch boundary side edges & back boundary line
    p_top_l = proj(-hw, y_base)
    p_bot_l = proj(-hw, y_base + sign * 10.5)
    p_top_r = proj(+hw, y_base)
    p_bot_r = proj(+hw, y_base + sign * 10.5)
    if all([p_top_l, p_bot_l, p_top_r, p_bot_r]):
        cv2.line(annotated, p_top_l, p_bot_l, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.line(annotated, p_top_r, p_bot_r, (255, 255, 255), 1, cv2.LINE_AA)

    p_end_l = proj(-hw, y_base + sign * 10.5)
    p_end_r = proj(+hw, y_base + sign * 10.5)
    if p_end_l and p_end_r:
        cv2.line(annotated, p_end_l, p_end_r, (255, 255, 255), 1, cv2.LINE_AA)

    def draw_stroked_text(img, text, org, fontFace, fontScale, color=(255, 255, 255), thickness=2, stroke_color=(0, 0, 0), stroke_thickness=4):
        cv2.putText(img, text, org, fontFace, fontScale, stroke_color, stroke_thickness, cv2.LINE_AA)
        cv2.putText(img, text, org, fontFace, fontScale, color, thickness, cv2.LINE_AA)

    # 3. Draw dividing lines at 0m, 2m, 4m, 6m, 8m with distance markers on the right
    for d in dividing_lines:
        y_line = y_base + sign * d
        p_left = proj(-hw, y_line)
        p_right = proj(+hw, y_line)

        if p_left and p_right:
            # White boundary line across pitch
            cv2.line(annotated, p_left, p_right, (255, 255, 255), 2 if d == 0.0 else 1, cv2.LINE_AA)

            # Indicator tick extending to the right
            dx = p_right[0] - p_left[0]
            dy = p_right[1] - p_left[1]
            L = max(np.hypot(dx, dy), 1.0)
            ux, uy = dx / L, dy / L
            tick_len = 14
            p_tick_end = (int(round(p_right[0] + ux * tick_len)), int(round(p_right[1] + uy * tick_len)))
            cv2.line(annotated, p_right, p_tick_end, (255, 255, 255), 2, cv2.LINE_AA)

            # Large, crisp white distance text: "0m", "2m", "4m", "6m", "8m" (NO black box)
            dist_txt = f"{int(d)}m"
            font = cv2.FONT_HERSHEY_DUPLEX
            scale_dist = 0.58 if batting_end == "far" else 0.62
            thick_dist = 2
            (tw, th), bl = cv2.getTextSize(dist_txt, font, scale_dist, thick_dist)

            tag_x = p_tick_end[0] + 8
            tag_y = p_tick_end[1] + th // 2

            draw_stroked_text(annotated, dist_txt, (tag_x, tag_y), font, scale_dist,
                              color=(255, 255, 255), thickness=thick_dist,
                              stroke_color=(0, 0, 0), stroke_thickness=4)

    # 4. Large, visible white text for length zone names (to the left of 0m-8m right edge, NO black boxes)
    for d_start, d_end, name, color in zones:
        y1 = y_base + sign * d_start
        y2 = y_base + sign * d_end
        y_mid = (y1 + y2) / 2.0

        p_right_mid = proj(+hw, y_mid)
        p_top_r = proj(+hw, y1)
        p_bot_r = proj(+hw, y2)

        if p_right_mid and p_top_r and p_bot_r:
            box_h_px = abs(p_bot_r[1] - p_top_r[1])
            scale_name = 0.58 if box_h_px > 25 else 0.48
            thick_name = 2
            font = cv2.FONT_HERSHEY_DUPLEX
            (tw, th), bl = cv2.getTextSize(name, font, scale_name, thick_name)

            # Position to the left of the right edge (inside the box on the right)
            margin_left_of_edge = 16
            bx = p_right_mid[0] - tw - margin_left_of_edge
            by = p_right_mid[1] + th // 2

            draw_stroked_text(annotated, name, (bx, by), font, scale_name,
                              color=(255, 255, 255), thickness=thick_name,
                              stroke_color=(0, 0, 0), stroke_thickness=4)

def annotate_stump_detection_only(frame, boxes_data, render_mode="black_stumps"):
    annotated = frame.copy()
    h, w = frame.shape[:2]
    
    for item in boxes_data:
        x1, y1, x2, y2 = item["box"]
        conf = item["confidence"]
        
        if render_mode == "black_stumps":
            # 3 Realistic Black Stumps (Off, Middle, Leg)
            draw_three_black_stumps(annotated, x1, y1, x2, y2)
            
            # Sleek label banner above bails
            label = f"WICKET | {conf:.2f}"
            font = cv2.FONT_HERSHEY_DUPLEX
            font_scale = 0.44
            thickness = 1
            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            badge_y = max(th + 4, y1 - 6)
            badge_x = max(0, int((x1 + x2)/2 - tw/2 - 4))
            cv2.rectangle(annotated, (badge_x, badge_y - th - 3), (badge_x + tw + 8, badge_y + 3), (18, 22, 28), -1)
            cv2.rectangle(annotated, (badge_x, badge_y - th - 3), (badge_x + tw + 8, badge_y + 3), (0, 235, 120), 1)
            cv2.putText(annotated, label, (badge_x + 4, badge_y - 1), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
        else:
            box_color = (0, 235, 120)     # Emerald Green
            accent_color = (0, 255, 255)  # Bright Yellow
            label_bg = (18, 22, 28)
            text_color = (255, 255, 255)
            
            # Bounding Box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 3)
            
            # Corner highlight brackets
            c_len = min(int((x2 - x1) * 0.25), int((y2 - y1) * 0.25), 22)
            if c_len > 4:
                thick = 4
                cv2.line(annotated, (x1, y1), (x1 + c_len, y1), accent_color, thick)
                cv2.line(annotated, (x1, y1), (x1, y1 + c_len), accent_color, thick)
                cv2.line(annotated, (x2, y1), (x2 - c_len, y1), accent_color, thick)
                cv2.line(annotated, (x2, y1), (x2, y1 + c_len), accent_color, thick)
                cv2.line(annotated, (x1, y2), (x1 + c_len, y2), accent_color, thick)
                cv2.line(annotated, (x1, y2), (x1, y2 - c_len), accent_color, thick)
                cv2.line(annotated, (x2, y2), (x2 - c_len, y2), accent_color, thick)
                cv2.line(annotated, (x2, y2), (x2, y2 - c_len), accent_color, thick)

            # Label Banner
            label = f"WICKET / STUMPS | {conf:.2f}"
            font = cv2.FONT_HERSHEY_DUPLEX
            font_scale = 0.55
            thickness = 1
            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            
            badge_y1 = max(0, y1 - th - baseline - 8)
            badge_y2 = badge_y1 + th + baseline + 8
            badge_x1 = max(0, x1)
            badge_x2 = min(w, badge_x1 + tw + 12)
            
            cv2.rectangle(annotated, (badge_x1, badge_y1), (badge_x2, badge_y2), label_bg, -1)
            cv2.rectangle(annotated, (badge_x1, badge_y1), (badge_x2, badge_y2), box_color, 1)
            cv2.putText(annotated, label, (badge_x1 + 6, badge_y2 - baseline - 4),
                        font, font_scale, text_color, thickness, cv2.LINE_AA)
        
    return annotated

def compute_pitch_calibration_model(boxes_data, h_img):
    """
    Compute 4-point perspective homography and calibration model from 2 detected wickets.
    Requires vertical separation between near and far wickets (y_sep >= 10% frame height).
    """
    if len(boxes_data) < 2:
        return None

    # Extract reference points
    wicket_refs = []
    for item in boxes_data:
        x1, y1, x2, y2 = item["box"]
        conf = item["confidence"]
        xc = (x1 + x2) / 2.0
        yc_bottom = float(y2)
        w_box = x2 - x1
        h_box = y2 - y1
        wicket_refs.append({
            'box': (x1, y1, x2, y2),
            'conf': conf,
            'xc': xc,
            'yc': yc_bottom,
            'ground_ref': (xc, yc_bottom),
            'w_box': w_box,
            'h_box': h_box
        })

    # Sort by Y descending: near wicket is lower down (larger Y), far wicket is higher up (smaller Y)
    wicket_refs.sort(key=lambda item: item['yc'], reverse=True)
    near = wicket_refs[0]
    far = wicket_refs[1]

    # Verify vertical separation (near wicket in foreground, far wicket in background)
    y_sep = near['yc'] - far['yc']
    if y_sep < h_img * 0.10:
        return None

    P_near = near['ground_ref']
    P_far = far['ground_ref']

    dx_px = P_far[0] - P_near[0]
    dy_px = P_far[1] - P_near[1]
    dist_px = float(np.sqrt(dx_px**2 + dy_px**2))
    if dist_px < 1e-4:
        return None

    px_per_m = dist_px / PITCH_LENGTH_M
    perp_dx = -dy_px / dist_px
    perp_dy = dx_px / dist_px
    half_w_near = near['w_box'] / 2.0
    half_w_far = far['w_box'] / 2.0

    img_pt1 = (P_near[0] - perp_dx * half_w_near, P_near[1] - perp_dy * half_w_near)
    img_pt2 = (P_near[0] + perp_dx * half_w_near, P_near[1] + perp_dy * half_w_near)
    img_pt3 = (P_far[0] + perp_dx * half_w_far, P_far[1] + perp_dy * half_w_far)
    img_pt4 = (P_far[0] - perp_dx * half_w_far, P_far[1] - perp_dy * half_w_far)

    pts_src = np.array([
        [-WICKET_WIDTH_M / 2.0, 0.0],
        [+WICKET_WIDTH_M / 2.0, 0.0],
        [+WICKET_WIDTH_M / 2.0, PITCH_LENGTH_M],
        [-WICKET_WIDTH_M / 2.0, PITCH_LENGTH_M]
    ], dtype=np.float32)

    pts_dst = np.array([img_pt1, img_pt2, img_pt3, img_pt4], dtype=np.float32)
    H, _ = cv2.findHomography(pts_src, pts_dst)
    if H is None:
        return None

    calib_data = {
        "active": True,
        "status": "calibrated",
        "distance_px": round(dist_px, 1),
        "distance_m": PITCH_LENGTH_M,
        "px_per_meter": round(px_per_m, 2),
        "near_ground_ref": [round(P_near[0], 1), round(P_near[1], 1)],
        "far_ground_ref": [round(P_far[0], 1), round(P_far[1], 1)],
        "near_box_width": round(near['w_box'], 1),
        "far_box_width": round(far['w_box'], 1),
        "depth_ratio": round(far['w_box'] / max(near['w_box'], 1), 3)
    }

    return {
        "H": H,
        "near": near,
        "far": far,
        "dist_px": dist_px,
        "px_per_m": px_per_m,
        "P_near": P_near,
        "P_far": P_far,
        "calib_data": calib_data
    }

def render_calibrated_pitch_overlay(frame, calib_model, render_mode="black_stumps", show_pitch_zones=True, batting_end="far"):
    """
    Renders constant, rock-solid pitch creases, 5 length zones, and 3 black stumps on any frame using locked calibration model.
    """
    annotated = frame.copy()
    H = calib_model["H"]
    near = calib_model["near"]
    far = calib_model["far"]
    white = (255, 255, 255)
    RETURN_BACK_M = 0.7  # Extends 0.7m behind bowling crease

    # 0. Bowling Length Zones (0-2m Yorker, 2-4m Full, 4-6m Good, 6-8m Back of Length, 8m+ Short)
    if show_pitch_zones:
        draw_pitch_zones(annotated, H, PITCH_LENGTH_M, POPPING_CREASE_OFFSET_M, PITCH_WIDTH_M, batting_end=batting_end)

    # ==================== NEAR END (Bowling End) ====================
    # 1. Bowling Crease through near stumps (White)
    near_bc_l = project_point(H, -BOWLING_CREASE_W_M / 2.0, 0.0)
    near_bc_r = project_point(H, +BOWLING_CREASE_W_M / 2.0, 0.0)
    if near_bc_l and near_bc_r:
        cv2.line(annotated, near_bc_l, near_bc_r, white, 2, cv2.LINE_AA)

    # 2. Popping Crease (+1.22m forward towards pitch) (White)
    near_pc_l = project_point(H, -POPPING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
    near_pc_r = project_point(H, +POPPING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
    if near_pc_l and near_pc_r:
        cv2.line(annotated, near_pc_l, near_pc_r, white, 3, cv2.LINE_AA)

    # 3. Return Creases (Left & Right, perpendicular to popping crease) (White)
    near_rc_l_back = project_point(H, -BOWLING_CREASE_W_M / 2.0, -RETURN_BACK_M)
    near_rc_l_front = project_point(H, -BOWLING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
    if near_rc_l_back and near_rc_l_front:
        cv2.line(annotated, near_rc_l_back, near_rc_l_front, white, 2, cv2.LINE_AA)

    near_rc_r_back = project_point(H, +BOWLING_CREASE_W_M / 2.0, -RETURN_BACK_M)
    near_rc_r_front = project_point(H, +BOWLING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
    if near_rc_r_back and near_rc_r_front:
        cv2.line(annotated, near_rc_r_back, near_rc_r_front, white, 2, cv2.LINE_AA)

    # ==================== FAR END (Batsman End) ====================
    # 1. Bowling Crease through far stumps (White)
    far_bc_l = project_point(H, -BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M)
    far_bc_r = project_point(H, +BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M)
    if far_bc_l and far_bc_r:
        cv2.line(annotated, far_bc_l, far_bc_r, white, 2, cv2.LINE_AA)

    # 2. Popping Crease (-1.22m forward towards near end) (White)
    far_pc_l = project_point(H, -POPPING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
    far_pc_r = project_point(H, +POPPING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
    if far_pc_l and far_pc_r:
        cv2.line(annotated, far_pc_l, far_pc_r, white, 2, cv2.LINE_AA)

    # 3. Return Creases (Left & Right) (White)
    far_rc_l_front = project_point(H, -BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
    far_rc_l_back = project_point(H, -BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M + RETURN_BACK_M)
    if far_rc_l_front and far_rc_l_back:
        cv2.line(annotated, far_rc_l_front, far_rc_l_back, white, 2, cv2.LINE_AA)

    far_rc_r_front = project_point(H, +BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
    far_rc_r_back = project_point(H, +BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M + RETURN_BACK_M)
    if far_rc_r_front and far_rc_r_back:
        cv2.line(annotated, far_rc_r_front, far_rc_r_back, white, 2, cv2.LINE_AA)

    # 4. Re-render 3 black stumps on top of creases at both ends (Rock-solid constant)
    if render_mode == "black_stumps":
        for item in [near, far]:
            x1, y1, x2, y2 = item['box']
            draw_three_black_stumps(annotated, x1, y1, x2, y2)
            xc = (x1 + x2) / 2.0
            yc = float(y2)
            gx, gy = int(round(xc)), int(round(yc))
            cv2.circle(annotated, (gx, gy), 5, (0, 0, 255), -1)
            cv2.circle(annotated, (gx, gy), 8, (0, 235, 120), 2)
            cv2.drawMarker(annotated, (gx, gy), (255, 255, 255), cv2.MARKER_CROSS, 12, 1)

    return annotated

def annotate_pitch_geometry(frame, boxes_data, render_mode="black_stumps", show_pitch_zones=True, batting_end="far", locked_calibration=None):
    h_img, w_img = frame.shape[:2]

    # If persistent locked calibration is provided (e.g. video processing)
    if locked_calibration is not None:
        annotated = render_calibrated_pitch_overlay(
            frame, locked_calibration, render_mode=render_mode,
            show_pitch_zones=show_pitch_zones, batting_end=batting_end
        )
        return annotated, locked_calibration["calib_data"], locked_calibration

    # Otherwise compute calibration dynamically from current frame
    calib_model = compute_pitch_calibration_model(boxes_data, h_img)
    if calib_model is not None:
        annotated = render_calibrated_pitch_overlay(
            frame, calib_model, render_mode=render_mode,
            show_pitch_zones=show_pitch_zones, batting_end=batting_end
        )
        return annotated, calib_model["calib_data"], calib_model
    else:
        # Fall back to detection boxes if pitch cannot be calibrated
        annotated = annotate_stump_detection_only(frame, boxes_data, render_mode=render_mode)
        calib_data = {
            "active": False,
            "status": "insufficient_wickets",
            "message": "Only 1 wicket visible; 2 wickets required for pitch centerline calibration."
        }
        return annotated, calib_data, None

@app.get("/api/samples")
def list_samples(category: str = "all", media_type: str = "all"):
    samples_dir = os.path.join(STATIC_DIR, "samples")
    files = [f for f in os.listdir(samples_dir) if not f.startswith('.')]
    out = []
    for f in sorted(files):
        ext = os.path.splitext(f)[1].lower()
        is_vid = ext in ['.mp4', '.mov', '.avi']
        if media_type == "image" and is_vid:
            continue
        if media_type == "video" and not is_vid:
            continue
        is_ball = "ball" in f or "deliv" in f
        cat = "ball" if is_ball else "stumps"
        if category == "all" or category == cat:
            title = f.replace("sample_", "").replace(".png", "").replace(".jpg", "").replace(".mp4", "").replace("_", " ").title()
            out.append({
                "id": f,
                "title": title,
                "url": f"/static/samples/{f}",
                "category": cat,
                "media_type": "video" if is_vid else "image"
            })
    return out

@app.post("/api/detect")
async def detect_image(
    file: UploadFile = File(None),
    sample_id: str = Form(None),
    conf: float = Form(0.35),
    pitch_calibration: bool = Form(True),
    render_mode: str = Form("black_stumps"),
    show_pitch_zones: bool = Form(True),
    batting_end: str = Form("far")
):
    if file:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        filename = file.filename
    elif sample_id:
        sample_path = os.path.join(STATIC_DIR, "samples", sample_id)
        if not os.path.exists(sample_path):
            raise HTTPException(status_code=404, detail="Sample image not found")
        img = cv2.imread(sample_path)
        filename = sample_id
    else:
        raise HTTPException(status_code=400, detail="Either file or sample_id required")

    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    h, w = img.shape[:2]
    t0 = time.time()
    results = model.predict(source=img, conf=conf, verbose=False)
    infer_ms = (time.time() - t0) * 1000.0

    boxes_out = []
    if results[0].boxes is not None and len(results[0].boxes) > 0:
        for b in results[0].boxes:
            xyxy = b.xyxy[0].cpu().numpy().astype(int).tolist()
            confidence = float(b.conf[0].cpu().numpy())
            boxes_out.append({
                "box": xyxy,
                "confidence": round(confidence, 4),
                "width": xyxy[2] - xyxy[0],
                "height": xyxy[3] - xyxy[1],
                "label": "WICKET / STUMPS"
            })

    calib_info = None
    if pitch_calibration:
        annotated, calib_info, _ = annotate_pitch_geometry(
            img, boxes_out, render_mode=render_mode,
            show_pitch_zones=show_pitch_zones, batting_end=batting_end
        )
    else:
        annotated = annotate_stump_detection_only(img, boxes_out, render_mode=render_mode)
    
    # Save output image
    out_name = f"result_{int(time.time()*1000)}.jpg"
    out_path = os.path.join(OUTPUTS_DIR, out_name)
    cv2.imwrite(out_path, annotated)

    # Encode base64
    _, buf = cv2.imencode('.jpg', annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    base64_img = base64.b64encode(buf).decode('utf-8')

    return JSONResponse({
        "success": True,
        "filename": filename,
        "inference_ms": round(infer_ms, 1),
        "fps_estimate": round(1000.0 / max(infer_ms, 1), 1),
        "num_wickets": len(boxes_out),
        "image_size": {"width": w, "height": h},
        "boxes": boxes_out,
        "calibration": calib_info,
        "image_data": f"data:image/jpeg;base64,{base64_img}",
        "download_url": f"/static/outputs/{out_name}"
    })

@app.post("/api/detect-ball")
async def detect_ball_endpoint(
    file: UploadFile = File(None),
    sample_id: str = Form(None),
    ball_conf: float = Form(0.25),
    detect_stumps: bool = Form(True),
    pitch_calibration: bool = Form(True),
    render_mode: str = Form("black_stumps"),
    show_pitch_zones: bool = Form(True),
    batting_end: str = Form("far")
):
    if file:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        filename = file.filename
    elif sample_id:
        sample_path = os.path.join(STATIC_DIR, "samples", sample_id)
        if not os.path.exists(sample_path):
            raise HTTPException(status_code=404, detail="Sample image not found")
        img = cv2.imread(sample_path)
        filename = sample_id
    else:
        raise HTTPException(status_code=400, detail="Either file or sample_id required")

    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    h, w = img.shape[:2]
    t0 = time.time()

    # 1. Optionally detect stumps and calibrate pitch
    annotated = img.copy()
    calib_model = None
    calib_info = None
    if detect_stumps:
        stump_res = model.predict(source=img, conf=0.35, verbose=False)
        stump_boxes = []
        if stump_res[0].boxes is not None:
            for b in stump_res[0].boxes:
                xyxy = b.xyxy[0].cpu().numpy().astype(int).tolist()
                c = float(b.conf[0].cpu().numpy())
                stump_boxes.append({"box": xyxy, "confidence": c})
        if pitch_calibration:
            annotated, calib_info, calib_model = annotate_pitch_geometry(
                img, stump_boxes, render_mode=render_mode,
                show_pitch_zones=show_pitch_zones, batting_end=batting_end
            )
        else:
            annotated = annotate_stump_detection_only(img, stump_boxes, render_mode=render_mode)

    # 2. Detect Ball
    ball_detector = BallDetector(BALL_WEIGHTS_PATH)
    ball_detections = ball_detector.detect(img, conf=ball_conf)
    infer_ms = (time.time() - t0) * 1000.0

    # 3. Project to pitch coordinates if pitch is calibrated
    pitch_mapping = None
    H = calib_model["H"] if calib_model else None

    if len(ball_detections) > 0:
        best_ball = ball_detections[0]
        bxc, byc = best_ball["center"]
        br = best_ball["radius"]
        bconf = best_ball["confidence"]

        if H is not None:
            pitch_mapping = BallTrajectoryTracker.project_to_pitch(H, bxc, byc, PITCH_LENGTH_M, POPPING_CREASE_OFFSET_M)

        # Draw glowing ball target
        cr = int(round(max(br, 6)))
        cx, cy = int(round(bxc)), int(round(byc))
        cv2.circle(annotated, (cx, cy), cr + 8, (0, 140, 255), 2, cv2.LINE_AA)
        cv2.circle(annotated, (cx, cy), cr + 3, (0, 240, 255), 2, cv2.LINE_AA)
        cv2.circle(annotated, (cx, cy), cr, (0, 70, 255), -1, cv2.LINE_AA)
        cv2.circle(annotated, (cx, cy), max(cr - 2, 2), (255, 255, 255), -1, cv2.LINE_AA)

        label_txt = f"CRICKET BALL {int(round(bconf * 100))}%"
        if pitch_mapping:
            label_txt += f" | {pitch_mapping['dist_from_crease_m']}m ({pitch_mapping['zone'].upper()})"
        draw_stroked_text(annotated, label_txt, (cx + cr + 10, cy + 5), cv2.FONT_HERSHEY_DUPLEX, 0.52,
                          color=(255, 255, 255), thickness=1, stroke_thickness=3)

    # Save output image
    out_name = f"ball_result_{int(time.time()*1000)}.jpg"
    out_path = os.path.join(OUTPUTS_DIR, out_name)
    cv2.imwrite(out_path, annotated)

    # Encode base64
    _, buf = cv2.imencode('.jpg', annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    base64_img = base64.b64encode(buf).decode('utf-8')

    return JSONResponse({
        "success": True,
        "filename": filename,
        "inference_ms": round(infer_ms, 1),
        "fps_estimate": round(1000.0 / max(infer_ms, 1), 1),
        "ball_detected": len(ball_detections) > 0,
        "ball_detections": ball_detections,
        "pitch_mapping": pitch_mapping,
        "image_size": {"width": w, "height": h},
        "calibration": calib_info,
        "image_data": f"data:image/jpeg;base64,{base64_img}",
        "download_url": f"/static/outputs/{out_name}"
    })

@app.post("/api/track-ball-video")
async def track_ball_video(
    file: UploadFile = File(None),
    sample_id: str = Form(None),
    video_path: str = Form(None),
    ball_conf: float = Form(0.25),
    trail_length: int = Form(30),
    detect_stumps: bool = Form(True),
    pitch_calibration: bool = Form(True),
    render_mode: str = Form("black_stumps"),
    show_pitch_zones: bool = Form(True),
    batting_end: str = Form("far"),
    start_time: float = Form(0.0),
    end_time: float = Form(None)
):
    src_video_path = None
    is_temp = False
    input_filename = "video.mp4"

    if file and file.filename:
        input_filename = file.filename
        temp_in = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1])
        src_video_path = temp_in.name
        is_temp = True
        with open(src_video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    elif sample_id:
        sample_file = os.path.join(STATIC_DIR, "samples", sample_id)
        if not os.path.exists(sample_file):
            raise HTTPException(status_code=404, detail="Sample video not found")
        src_video_path = sample_file
        input_filename = sample_id
    elif video_path:
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail=f"Local video not found: {video_path}")
        src_video_path = video_path
        input_filename = os.path.basename(video_path)
    else:
        raise HTTPException(status_code=400, detail="Provide a video file, sample_id, or video_path")

    try:
        cap = cv2.VideoCapture(src_video_path)
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Cannot read video file")

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        start_frame = int(round(start_time * fps)) if start_time and start_time > 0 else 0
        end_frame = int(round(end_time * fps)) if end_time and end_time > 0 else total_frames
        start_frame = max(0, min(start_frame, total_frames - 1))
        end_frame = max(start_frame + 1, min(end_frame, total_frames))
        num_target_frames = end_frame - start_frame

        out_name = f"ball_track_{int(time.time())}.mp4"
        out_path = os.path.join(OUTPUTS_DIR, out_name)
        raw_out_path = os.path.join(OUTPUTS_DIR, f"raw_{out_name}")

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out_writer = cv2.VideoWriter(raw_out_path, fourcc, fps, (w, h))

        # 1. Pre-scan for locked constant pitch calibration within the delivery window
        locked_calib = None
        if pitch_calibration and detect_stumps:
            scan_cap = cv2.VideoCapture(src_video_path)
            scan_cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            scan_limit = min(num_target_frames, 90)
            best_score = -1.0
            idx = 0
            while idx < scan_limit:
                ret, sframe = scan_cap.read()
                if not ret: break
                if idx % 2 == 0:
                    sres = model.predict(source=sframe, conf=0.35, verbose=False)
                    sboxes = []
                    if sres[0].boxes is not None:
                        for b in sres[0].boxes:
                            xyxy = b.xyxy[0].cpu().numpy().astype(int).tolist()
                            c = float(b.conf[0].cpu().numpy())
                            sboxes.append({"box": xyxy, "confidence": c})
                    cmodel = compute_pitch_calibration_model(sboxes, h)
                    if cmodel is not None:
                        score = cmodel["near"]["conf"] + cmodel["far"]["conf"]
                        if score > best_score:
                            best_score = score
                            locked_calib = cmodel
                            if score > 1.6: break
                idx += 1
            scan_cap.release()

        ball_detector = BallDetector(BALL_WEIGHTS_PATH)
        tracker = BallTrajectoryTracker(max_history=trail_length)
        if locked_calib is not None:
            tracker.set_pitch_context(locked_calib, img_w=w, img_h=h)
        else:
            tracker.set_pitch_context(None, img_w=w, img_h=h)
        H_pitch = locked_calib["H"] if locked_calib else None

        frame_count = 0
        ball_frames = 0
        t0 = time.time()

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        for curr_frame_idx in range(start_frame, end_frame):
            ret, frame = cap.read()
            if not ret: break
            frame_count += 1

            # Base frame with pitch overlay
            if locked_calib is not None:
                base_frame = render_calibrated_pitch_overlay(
                    frame, locked_calib, render_mode=render_mode,
                    show_pitch_zones=show_pitch_zones, batting_end=batting_end
                )
            else:
                base_frame = frame.copy()

            # Detect ball in current frame restricted to pitch corridor
            dets = ball_detector.detect(frame, conf=ball_conf, corridor=tracker.corridor)
            best_ball = dets[0] if len(dets) > 0 else None
            if best_ball is not None:
                ball_frames += 1

            # Update trajectory tracker with Kalman Filter & anti-shoe gating
            tracker.update(best_ball, frame_count, H_pitch, PITCH_LENGTH_M, POPPING_CREASE_OFFSET_M, candidates=dets)

            # Render IPL-grade Hawkeye trajectory overlay with pitch impact mark & DRS projection
            annotated = tracker.render_overlay(base_frame, max_trail=trail_length, show_bounce=True, show_target=True)

            out_writer.write(annotated)

        cap.release()
        out_writer.release()
        total_time = time.time() - t0
        avg_fps = frame_count / total_time if total_time > 0 else 0

        # Convert to browser-compatible H.264
        try:
            import subprocess
            subprocess.run([
                "/usr/local/bin/ffmpeg", "-y", "-i", raw_out_path,
                "-vcodec", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                out_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(raw_out_path):
                os.remove(raw_out_path)
        except Exception:
            if os.path.exists(raw_out_path) and not os.path.exists(out_path):
                os.rename(raw_out_path, out_path)

        return JSONResponse({
            "success": True,
            "filename": input_filename,
            "frames_processed": frame_count,
            "ball_frames_tracked": ball_frames,
            "duration_sec": round(frame_count / fps, 2),
            "processing_time_sec": round(total_time, 2),
            "avg_fps": round(avg_fps, 1),
            "bounce_detected": tracker.bounce_event is not None,
            "bounce_event": tracker.bounce_event,
            "calibration_locked": locked_calib is not None,
            "video_url": f"/static/outputs/{out_name}"
        })
    finally:
        if is_temp and src_video_path and os.path.exists(src_video_path):
            os.remove(src_video_path)

@app.post("/api/detect-video")
async def detect_video(
    file: UploadFile = File(None),
    sample_id: str = Form(None),
    video_path: str = Form(None),
    conf: float = Form(0.35),
    pitch_calibration: bool = Form(True),
    render_mode: str = Form("black_stumps"),
    show_pitch_zones: bool = Form(True),
    batting_end: str = Form("far"),
    start_time: float = Form(0.0),
    end_time: float = Form(None)
):
    src_video_path = None
    is_temp = False
    input_filename = "video.mp4"

    if file and file.filename:
        input_filename = file.filename
        temp_in = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1])
        src_video_path = temp_in.name
        is_temp = True
        with open(src_video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    elif sample_id:
        sample_file = os.path.join(STATIC_DIR, "samples", sample_id)
        if not os.path.exists(sample_file):
            raise HTTPException(status_code=404, detail="Sample video not found")
        src_video_path = sample_file
        input_filename = sample_id
    elif video_path:
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail=f"Local video not found: {video_path}")
        src_video_path = video_path
        input_filename = os.path.basename(video_path)
    else:
        raise HTTPException(status_code=400, detail="Provide a video file, sample_id, or video_path")

    try:
        cap = cv2.VideoCapture(src_video_path)
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Cannot read video file")

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        start_frame = int(round(start_time * fps)) if start_time and start_time > 0 else 0
        end_frame = int(round(end_time * fps)) if end_time and end_time > 0 else total_frames
        start_frame = max(0, min(start_frame, total_frames - 1))
        end_frame = max(start_frame + 1, min(end_frame, total_frames))
        num_target_frames = end_frame - start_frame

        out_name = f"video_{int(time.time())}.mp4"
        out_path = os.path.join(OUTPUTS_DIR, out_name)
        raw_out_path = os.path.join(OUTPUTS_DIR, f"raw_{out_name}")
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out_writer = cv2.VideoWriter(raw_out_path, fourcc, fps, (w, h))

        # 1. Fast pre-scan upfront within delivery window to lock pitch calibration
        locked_calib = None
        if pitch_calibration:
            scan_cap = cv2.VideoCapture(temp_in.name)
            scan_cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            scan_limit = min(num_target_frames, 90)
            best_score = -1.0
            idx = 0
            while idx < scan_limit:
                ret, sframe = scan_cap.read()
                if not ret:
                    break
                if idx % 2 == 0:
                    sres = model.predict(source=sframe, conf=conf, verbose=False)
                    sboxes = []
                    if sres[0].boxes is not None:
                        for b in sres[0].boxes:
                            xyxy = b.xyxy[0].cpu().numpy().astype(int).tolist()
                            c = float(b.conf[0].cpu().numpy())
                            sboxes.append({"box": xyxy, "confidence": c})
                    cmodel = compute_pitch_calibration_model(sboxes, h)
                    if cmodel is not None:
                        score = cmodel["near"]["conf"] + cmodel["far"]["conf"]
                        if score > best_score:
                            best_score = score
                            locked_calib = cmodel
                            if score > 1.6:
                                break
                idx += 1
            scan_cap.release()

        frame_count = 0
        total_detections = 0
        t0 = time.time()

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        for curr_frame_idx in range(start_frame, end_frame):
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1
            
            if pitch_calibration:
                if locked_calib is not None:
                    # Locked constant pitch calibration across the whole video
                    annotated = render_calibrated_pitch_overlay(
                        frame, locked_calib, render_mode=render_mode,
                        show_pitch_zones=show_pitch_zones, batting_end=batting_end
                    )
                    total_detections += 2
                else:
                    # Dynamically detect on current frame and lock as soon as 2 wickets are detected
                    results = model.predict(source=frame, conf=conf, verbose=False)
                    boxes_data = []
                    if results[0].boxes is not None:
                        for b in results[0].boxes:
                            xyxy = b.xyxy[0].cpu().numpy().astype(int).tolist()
                            confidence = float(b.conf[0].cpu().numpy())
                            boxes_data.append({"box": xyxy, "confidence": confidence})
                            total_detections += 1
                    
                    cmodel = compute_pitch_calibration_model(boxes_data, h)
                    if cmodel is not None:
                        locked_calib = cmodel  # Constant lock from here on!
                        annotated = render_calibrated_pitch_overlay(
                            frame, locked_calib, render_mode=render_mode,
                            show_pitch_zones=show_pitch_zones, batting_end=batting_end
                        )
                    else:
                        annotated = annotate_stump_detection_only(frame, boxes_data, render_mode=render_mode)
            else:
                results = model.predict(source=frame, conf=conf, verbose=False)
                boxes_data = []
                if results[0].boxes is not None:
                    for b in results[0].boxes:
                        xyxy = b.xyxy[0].cpu().numpy().astype(int).tolist()
                        confidence = float(b.conf[0].cpu().numpy())
                        boxes_data.append({"box": xyxy, "confidence": confidence})
                        total_detections += 1
                annotated = annotate_stump_detection_only(frame, boxes_data, render_mode=render_mode)

            out_writer.write(annotated)

        cap.release()
        out_writer.release()
        total_time = time.time() - t0
        avg_fps = frame_count / total_time if total_time > 0 else 0

        # Convert to browser-compatible H.264 mp4 via ffmpeg if available
        try:
            import subprocess
            subprocess.run([
                "/usr/local/bin/ffmpeg", "-y", "-i", raw_out_path,
                "-vcodec", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                out_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(raw_out_path):
                os.remove(raw_out_path)
        except Exception:
            if os.path.exists(raw_out_path) and not os.path.exists(out_path):
                os.rename(raw_out_path, out_path)

        return JSONResponse({
            "success": True,
            "filename": input_filename,
            "frames_processed": frame_count,
            "duration_sec": round(frame_count / fps, 2),
            "processing_time_sec": round(total_time, 2),
            "avg_fps": round(avg_fps, 1),
            "total_stump_detections": total_detections,
            "calibration_locked": locked_calib is not None,
            "video_url": f"/static/outputs/{out_name}"
        })
    finally:
        if is_temp and src_video_path and os.path.exists(src_video_path):
            os.remove(src_video_path)

# Mount static directory
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def get_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
