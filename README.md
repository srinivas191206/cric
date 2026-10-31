# CricketVision AI: Real-Time Ball Tracking & Stump Detection

An AI-powered computer vision system for cricket analytics, featuring:
- **YOLO11 Ball Detector**: Custom-trained model with hard-negative background mining (eliminating shoe & ground false positives) and 94%+ detection mAP.
- **IPL Hawkeye Trajectory Tracker**: 6-state Kalman Filter (`[x, y, vx, vy, ax, ay]`) with Mahalanobis innovation gating, pitch bounce detection, and smooth parabolic trajectory rendering.
- **Stump & Wicket Detection**: Sub-pixel accurate localization of near and far cricket stumps.
- **Pitch Homography Calibration**: Metric mapping of pitch length zones (Yorker, Full, Good Length, Short) and lateral lines (Off, Middle, Leg Stump).
- **FastAPI Web Application**: Modern interactive UI with video streaming, sample delivery presets, and real-time visual telemetry.

---

## Architecture Overview

```
stumps/
├── ball_tracker/          # Kalman Filter & Ball Trajectory Tracker
│   └── tracker.py
├── stump_detector/        # Wicket and stump detection models
├── web/                   # FastAPI Web App & UI
│   ├── app.py             # Streaming API server
│   ├── static/            # Frontend assets (HTML, CSS, JS)
│   │   └── samples/       # Pre-loaded delivery video clips & test images
│   └── ball_tracker/      # Synchronized tracking module
├── weights/               # Production YOLO model weights
│   ├── ball_best.pt       # Retrained ball detector
│   └── best.pt            # Stump detector
├── ball_dataset_v2/       # Consolidated annotated dataset
├── new data/              # Stump calibration & ball annotations
├── requirements.txt       # Dependencies
└── train_ball_v3.py       # Fine-tuning script
```

---

## Quickstart

### 1. Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Launch Web Interface
```bash
uvicorn web.app:app --host 127.0.0.1 --port 8000
```
Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Models & Performance
- **Ball Detection**: Fine-tuned YOLO11s on Apple Silicon MPS with unified 797-image multi-source dataset and hard negative background mining.
  - Unseen Test set mAP@50: **98.54%**
  - Unseen Test set Precision: **98.32%**
  - Unseen Test set Recall: **95.95%**
  - Full delivery tracking continuity: **37 frames** per delivery
  - False positive shoe detections: **0**
- **Inference Speed**: ~6.3 ms / frame (150+ FPS)
