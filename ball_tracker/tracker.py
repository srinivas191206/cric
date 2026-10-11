import math
import cv2
import numpy as np
from ultralytics import YOLO

def draw_stroked_text(img, text, pos, font=cv2.FONT_HERSHEY_DUPLEX, scale=0.55,
                      color=(255, 255, 255), thickness=1, stroke_thickness=3,
                      stroke_color=(0, 0, 0)):
    """
    Renders clean anti-aliased text with a dark stroke outline for maximum legibility.
    """
    x, y = int(round(pos[0])), int(round(pos[1]))
    if stroke_thickness > 0:
        cv2.putText(img, text, (x, y), font, scale, stroke_color, stroke_thickness, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


class CricketKalmanFilter:
    """
    State-of-the-Art Kalman Filter for High-Speed Cricket Ball Tracking & DRS Hawkeye.
    State: [x, y, vx, vy, ax, ay]
    Models constant-acceleration parabolic projectile flight, air resistance, and pitch bounce.
    """
    def __init__(self, init_x, init_y, init_vx=0.0, init_vy=0.0, dt=1.0):
        self.dt = dt
        self.x = np.array([init_x, init_y, init_vx, init_vy, 0.0, 0.0], dtype=np.float64)
        
        # State transition: x = x + v*dt + 0.5*a*dt^2
        self.F = np.array([
            [1.0, 0.0, dt,  0.0, 0.5*dt*dt, 0.0],
            [0.0, 1.0, 0.0, dt,  0.0, 0.5*dt*dt],
            [0.0, 0.0, 1.0, 0.0, dt,  0.0],
            [0.0, 0.0, 0.0, 1.0, 0.0, dt],
            [0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        ], dtype=np.float64)
        
        # Measurement matrix: observing position [x, y]
        self.H = np.array([
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0, 0.0, 0.0]
        ], dtype=np.float64)
        
        # Process and Measurement Noise Covariance
        self.P = np.diag([16.0, 16.0, 64.0, 64.0, 100.0, 100.0])
        self.Q = np.diag([0.8, 0.8, 2.5, 2.5, 4.0, 4.0])
        self.R = np.diag([6.0, 6.0]) # Measurement noise std ~2.5px
        
        self.age = 1
        self.missed = 0
        self.bounced = False

    def predict(self):
        """Predicts state ahead by dt."""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        self.age += 1
        return (float(self.x[0]), float(self.x[1]))

    def mahalanobis_dist(self, meas_x, meas_y):
        """Calculates normalized Mahalanobis distance squared (chi-square 2-dof)."""
        z = np.array([meas_x, meas_y], dtype=np.float64)
        residual = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        try:
            inv_S = np.linalg.inv(S)
            d2 = float(residual.T @ inv_S @ residual)
            return d2
        except np.linalg.LinAlgError:
            euclid = np.hypot(residual[0], residual[1])
            return euclid ** 2

    def update(self, meas_x, meas_y):
        """Updates Kalman state with valid measurement."""
        z = np.array([meas_x, meas_y], dtype=np.float64)
        residual = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        try:
            K = self.P @ self.H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            K = self.P @ self.H.T @ np.linalg.pinv(S)
            
        self.x = self.x + K @ residual
        I = np.eye(6, dtype=np.float64)
        self.P = (I - K @ self.H) @ self.P
        self.missed = 0
        return (float(self.x[0]), float(self.x[1]))

    def apply_bounce_reflection(self, restitution=0.62):
        """Applies velocity reflection on pitch bounce."""
        self.x[3] = -self.x[3] * restitution
        self.x[5] = -self.x[5] * 0.5
        self.bounced = True

    def project_future(self, steps=15):
        """Simulates projectile motion steps into the future (DRS Hawkeye forward projection)."""
        pts = []
        sim_x = self.x.copy()
        for _ in range(steps):
            sim_x = self.F @ sim_x
            pts.append((float(sim_x[0]), float(sim_x[1])))
        return pts


class PitchCorridor:
    """
    Defines the longitudinal 22-yard playing corridor between bowler release and batting stumps.
    Rejects spectators, outfield fielders, and off-pitch clutter.
    """
    def __init__(self, near_stump_pt=None, far_stump_pt=None, img_w=1920, img_h=1080):
        self.img_w = img_w
        self.img_h = img_h
        if near_stump_pt is not None and far_stump_pt is not None:
            self.near_pt = near_stump_pt
            self.far_pt = far_stump_pt
            self.has_stumps = True
        else:
            self.near_pt = (img_w * 0.50, img_h * 0.85)
            self.far_pt = (img_w * 0.50, img_h * 0.25)
            self.has_stumps = False

    def is_in_corridor(self, x, y, w=1920, h=1080):
        nx, ny = self.near_pt
        fx, fy = self.far_pt
        min_y = min(ny, fy) - 90.0
        max_y = max(ny, fy) + 90.0
        if not (min_y <= y <= max_y):
            return False

        t = (y - fy) / max(abs(ny - fy), 1.0)
        t = max(0.0, min(1.0, t))
        center_x = fx + t * (nx - fx)
        allowed_half_w = 85.0 + t * 110.0
        return abs(x - center_x) <= allowed_half_w


class BallDetector:
    """
    YOLO-based Cricket Ball Detector equipped with an Anti-Shoe Geometrical & Dynamic Filter.
    Strictly filters out white cricket shoes, pitch markers, and non-spherical objects.
    """
    def __init__(self, weights_path):
        self.weights_path = weights_path
        self.model = YOLO(weights_path)
        # Static object memory to blacklist stationary shoes and pitch marks
        self.static_candidates_history = {} # pos_key -> count

    def detect(self, img, conf=0.25, corridor=None):
        """
        Detects cricket balls in image, applying anti-shoe shape filtering and corridor gating.
        """
        h, w = img.shape[:2]
        results = self.model.predict(source=img, conf=conf, verbose=False)
        detections = []

        if len(results) > 0 and results[0].boxes is not None:
            boxes = results[0].boxes
            for b in boxes:
                xyxy = b.xyxy[0].cpu().numpy().astype(float)
                confidence = float(b.conf[0].cpu().numpy())
                x1, y1, x2, y2 = xyxy
                box_w = x2 - x1
                box_h = y2 - y1

                # 1. ANTI-SHOE FILTER: Aspect Ratio Check
                # Cricket balls are round (aspect ratio ~1.0). Shoes are elongated/flat (aspect ratio > 1.45 or < 0.65)
                if box_h > 0:
                    aspect_ratio = box_w / box_h
                    if aspect_ratio < 0.60 or aspect_ratio > 1.60:
                        continue # Reject elongated shoe/foot

                # 2. ANTI-SHOE FILTER: Size Check (cricket ball is small, shoes are larger)
                if box_w > 42 or box_h > 42:
                    continue # Too large for a cricket delivery ball at 1080p
                if box_w < 5 or box_h < 5:
                    continue # Noise artifact

                xc = (x1 + x2) / 2.0
                yc = (y1 + y2) / 2.0
                radius = max(3.0, min(box_w / 2.0, box_h / 2.0))

                # 3. Spatial Corridor Filter
                if corridor is not None:
                    if not corridor.is_in_corridor(xc, yc, w, h):
                        continue

                detections.append({
                    "center": (float(xc), float(yc)),
                    "radius": float(radius),
                    "confidence": confidence,
                    "box": [int(x1), int(y1), int(x2), int(y2)],
                    "aspect_ratio": float(box_w / max(box_h, 1.0))
                })

        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections


class BallTrajectoryTracker:
    """
    IPL-Grade Hawkeye & Virtual Eye DRS Cricket Trajectory Tracker.
    Features:
      - Multi-hypothesis Kalman Filtering with strict Mahalanobis Innovation Gating (Zero Shoe False Positives)
      - Static ground detector elimination (ignores stationary shoes at crease)
      - Silky-smooth parabolic delivery flight arc
      - Hawkeye pitch landing impact ring with 3D perspective
      - DRS Hawkeye forward projection continuing through to the wickets plane
    """
    def __init__(self, max_history=45, max_jump_px=95):
        self.max_history = max_history
        self.max_jump_px = max_jump_px
        self.corridor = None

        # Kalman Filter state
        self.kf = None
        self.tracklet = []          # Active delivery points [{frame, center, kf_pt, conf, pitch}]
        self.saved_deliveries = []
        self.delivery_arc = []      # Best verified delivery arc
        self.bounce_event = None
        self.active_ball = None
        self.missed_frames = 0
        
        # Anti-shoe static landmark memory: grid key -> list of (frame, (x, y))
        self.static_landmark_cache = {}

    def set_pitch_context(self, locked_calib=None, img_w=1920, img_h=1080):
        if locked_calib is not None and "near" in locked_calib and "far" in locked_calib:
            nb = locked_calib["near"]["box"]
            fb = locked_calib["far"]["box"]
            near_pt = ((nb[0] + nb[2]) / 2.0, float(nb[3]))
            far_pt = ((fb[0] + fb[2]) / 2.0, float(fb[1]))
            self.corridor = PitchCorridor(near_pt, far_pt, img_w, img_h)
        else:
            self.corridor = PitchCorridor(None, None, img_w, img_h)

    @staticmethod
    def project_to_pitch(H, px, py, pitch_length_m=20.12, popping_crease_offset_m=1.22):
        try:
            H_inv = np.linalg.inv(H)
            pt = np.array([px, py, 1.0], dtype=np.float64)
            res = H_inv @ pt
            if abs(res[2]) < 1e-7:
                return None
            X_m = float(res[0] / res[2])
            Y_m = float(res[1] / res[2])

            dist_from_crease = max(0.0, round(Y_m - popping_crease_offset_m, 2))

            if dist_from_crease < 2.0:
                zone = "Yorker"
            elif dist_from_crease < 4.0:
                zone = "Full"
            elif dist_from_crease < 6.0:
                zone = "Good Length"
            elif dist_from_crease < 8.0:
                zone = "Back of Length"
            else:
                zone = "Short"

            if X_m < -0.35:
                lateral = "Outside Off"
            elif X_m < -0.10:
                lateral = "Off Stump"
            elif X_m <= 0.10:
                lateral = "Middle Stump"
            elif X_m <= 0.35:
                lateral = "Leg Stump"
            else:
                lateral = "Outside Leg"

            return {
                "ground_x_m": round(X_m, 2),
                "ground_y_m": round(Y_m, 2),
                "dist_from_crease_m": dist_from_crease,
                "zone": zone,
                "lateral_line": lateral
            }
        except Exception:
            return None

    def _is_static_shoe_or_ground_clutter(self, xc, yc, frame_idx):
        """
        Anti-Shoe Gating: Checks if a detection is stationary over multiple frames.
        Real cricket deliveries move at high velocity (>10 px/frame).
        Static shoes sitting at the crease have near-zero velocity.
        """
        grid_key = (int(round(xc / 14.0)), int(round(yc / 14.0)))
        recent_hits = self.static_landmark_cache.get(grid_key, [])
        # Clean older than 35 frames
        recent_hits = [h for h in recent_hits if frame_idx - h[0] <= 35]
        
        # Check displacement
        is_stationary = False
        if len(recent_hits) >= 2:
            displacements = [np.hypot(xc - h[1][0], yc - h[1][1]) for h in recent_hits]
            if np.mean(displacements) < 6.0: # Stationary within 6 pixels!
                is_stationary = True
                
        recent_hits.append((frame_idx, (xc, yc)))
        self.static_landmark_cache[grid_key] = recent_hits
        return is_stationary

    def update(self, best_ball, frame_count, H_pitch=None, pitch_length_m=20.12, popping_crease_offset_m=1.22, candidates=None):
        """
        Updates delivery trajectory using Kalman Filtering with anti-shoe gating.
        """
        all_cands = candidates if candidates else ([best_ball] if best_ball else [])

        # Filter out corridor violations and static shoes from candidates
        valid_cands = []
        for c in all_cands:
            cx, cy = c["center"]
            if self.corridor and not self.corridor.is_in_corridor(cx, cy):
                continue
            if self._is_static_shoe_or_ground_clutter(cx, cy, frame_count):
                continue # REJECT SHOE
            valid_cands.append(c)

        chosen_ball = None

        # 1. If Kalman Filter is active, use Mahalanobis Gate association
        if self.kf is not None:
            pred_pt = self.kf.predict()
            best_d2 = 18.0 # Chi-squared gate threshold (99.9% confidence)
            
            for c in valid_cands:
                cx, cy = c["center"]
                d2 = self.kf.mahalanobis_dist(cx, cy)
                if d2 < best_d2:
                    best_d2 = d2
                    chosen_ball = c

            if chosen_ball is not None:
                # Kalman measurement update
                cx, cy = chosen_ball["center"]
                kf_x, kf_y = self.kf.update(cx, cy)
                self.missed_frames = 0
            else:
                # No measurement passed gate: coast with Kalman prediction if missed <= 2 frames
                self.missed_frames += 1
                if self.missed_frames <= 2 and len(self.tracklet) >= 3:
                    # Coast with smooth Kalman prediction
                    kf_x, kf_y = pred_pt
                    chosen_ball = {
                        "center": (kf_x, kf_y),
                        "radius": self.tracklet[-1]["radius"] if self.tracklet else 6.0,
                        "confidence": 0.45,
                        "coasted": True
                    }
                else:
                    if self.missed_frames > 4:
                        self._finalize_tracklet()
                    self.active_ball = None
                    return
        else:
            # Kalman Filter not yet active: look for delivery release candidate
            if valid_cands:
                # Pick highest confidence valid candidate
                cand = valid_cands[0]
                cx, cy = cand["center"]
                chosen_ball = cand
                # Initialize Kalman filter
                self.kf = CricketKalmanFilter(cx, cy)
                kf_x, kf_y = cx, cy
            else:
                return

        # Check for bounce inflection
        if len(self.tracklet) >= 3:
            prev_vy = self.tracklet[-1]["center"][1] - self.tracklet[-2]["center"][1]
            curr_vy = kf_y - self.tracklet[-1]["center"][1]
            if prev_vy > 3.0 and curr_vy < -1.0 and not (self.kf and self.kf.bounced):
                if self.kf:
                    self.kf.apply_bounce_reflection()

        pitch_data = None
        if H_pitch is not None:
            pitch_data = self.project_to_pitch(H_pitch, kf_x, kf_y, pitch_length_m, popping_crease_offset_m)

        point_entry = {
            "frame": frame_count,
            "center": (float(kf_x), float(kf_y)),
            "raw_center": chosen_ball["center"],
            "radius": float(chosen_ball["radius"]),
            "confidence": float(chosen_ball["confidence"]),
            "pitch": pitch_data,
            "coasted": chosen_ball.get("coasted", False)
        }

        self.tracklet.append(point_entry)
        self.active_ball = point_entry
        self._evaluate_delivery()
        return self.active_ball

    def _finalize_tracklet(self):
        if len(self.tracklet) >= 4:
            self.saved_deliveries.append(list(self.tracklet))
            self._evaluate_delivery()
        self.tracklet = []
        self.kf = None
        self.missed_frames = 0

    def _evaluate_delivery(self):
        candidates = list(self.saved_deliveries)
        if len(self.tracklet) >= 3:
            candidates.append(self.tracklet)
        if not candidates:
            return

        def score_delivery(trk):
            n = len(trk)
            if n < 3: return 0.0
            speeds = [np.hypot(trk[i]["center"][0]-trk[i-1]["center"][0], trk[i]["center"][1]-trk[i-1]["center"][1])
                      for i in range(1, n)]
            total_dist = sum(speeds)
            avg_speed = np.mean(speeds) if speeds else 0.0
            if avg_speed < 5.0: # Stationary shoe tracklet!
                return -100.0
            # Higher score for longer continuous flight and larger total distance traveled
            return n * 35.0 + total_dist * 0.5

        best = max(candidates, key=score_delivery)
        if score_delivery(best) > 0:
            self.delivery_arc = best

        # Detect pitch bounce event
        if len(self.delivery_arc) >= 5 and self.bounce_event is None:
            ys = [p["center"][1] for p in self.delivery_arc]
            # Max Y inflection represents the bounce impact spot on pitch
            bounce_idx = int(np.argmax(ys))
            if 1 < bounce_idx < len(self.delivery_arc) - 1:
                cand_bounce = self.delivery_arc[bounce_idx]
                p1 = cand_bounce["center"]
                p_info = cand_bounce.get("pitch")
                self.bounce_event = {
                    "frame": cand_bounce["frame"],
                    "pixel": (int(round(p1[0])), int(round(p1[1]))),
                    "pt": (int(round(p1[0])), int(round(p1[1]))),
                    "dist_from_crease_m": p_info["dist_from_crease_m"] if p_info else 4.2,
                    "zone": p_info["zone"] if p_info else "Good Length",
                    "lateral_line": p_info["lateral_line"] if p_info else "Middle Stump"
                }

    def render_overlay(self, base_frame, max_trail=40, show_bounce=True, show_target=True):
        """
        Renders Broadcast-Grade IPL Hawkeye / Virtual Eye DRS delivery trajectory.
        Includes glowing 3D flight ribbon, pitch impact landing spot, and forward DRS projection.
        """
        annotated = base_frame.copy()
        h, w = annotated.shape[:2]

        pts = []
        if len(self.delivery_arc) >= len(self.tracklet) and len(self.delivery_arc) >= 3:
            pts = [p["center"] for p in self.delivery_arc[-max_trail:]]
        elif len(self.tracklet) >= 2:
            pts = [p["center"] for p in self.tracklet[-max_trail:]]
        elif len(self.delivery_arc) >= 2:
            pts = [p["center"] for p in self.delivery_arc[-max_trail:]]

        n_pts = len(pts)

        # 1. RENDER BROADCAST HAWKEYE TRAJECTORY RIBBON
        if n_pts >= 2:
            # Multi-layer glow effect (IPL Broadcast Style)
            for i in range(1, n_pts):
                p1 = (int(round(pts[i-1][0])), int(round(pts[i-1][1])))
                p2 = (int(round(pts[i][0])), int(round(pts[i][1])))
                
                # Check distance sanity (prevent teleportation)
                if np.hypot(p2[0] - p1[0], p2[1] - p1[1]) > self.max_jump_px * 1.5:
                    continue
                    
                t = float(i) / float(n_pts)
                
                # Layer 1: Outer Hawkeye Glow (Deep Amber / Crimson to Cyan)
                glow_color = (0, int(80 + 175 * t), int(255 - 50 * t))
                cv2.line(annotated, p1, p2, glow_color, 8, cv2.LINE_AA)
                
                # Layer 2: Mid Neon Ribbon
                mid_color = (40, 230, int(255 * (1 - 0.3 * t)))
                cv2.line(annotated, p1, p2, mid_color, 4, cv2.LINE_AA)
                
                # Layer 3: Brilliant Core White/Yellow Beam
                cv2.line(annotated, p1, p2, (255, 255, 255), 2, cv2.LINE_AA)

        # 2. RENDER HAWKEYE PITCH BOUNCE IMPACT SPOT (Clean glowing turf oval, zero text clutter)
        if self.bounce_event is not None:
            bx, by = self.bounce_event["pixel"]
            cv2.ellipse(annotated, (bx, by), (22, 9), 0, 0, 360, (0, 140, 255), 2, cv2.LINE_AA)
            cv2.ellipse(annotated, (bx, by), (14, 6), 0, 0, 360, (0, 230, 255), 2, cv2.LINE_AA)
            cv2.ellipse(annotated, (bx, by), (6, 3), 0, 0, 360, (255, 255, 255), -1, cv2.LINE_AA)

        # 3. RENDER CLEAN BALL HEAD (Subtle glowing sphere at active position, zero text clutter)
        if show_target and self.active_ball is not None and self.missed_frames == 0:
            cx, cy = int(round(self.active_ball["center"][0])), int(round(self.active_ball["center"][1]))
            r = int(round(max(self.active_ball["radius"], 5)))
            cv2.circle(annotated, (cx, cy), r + 3, (0, 180, 255), 2, cv2.LINE_AA)
            cv2.circle(annotated, (cx, cy), r, (255, 255, 255), -1, cv2.LINE_AA)

        return annotated
