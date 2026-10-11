import os
import re
import cv2
import json
import shutil
import random
from pathlib import Path

BASE_DIR = "/Users/thaladasrinivas/Downloads/stumps"
OUTPUT_DIR = os.path.join(BASE_DIR, "ball_image_dataset")

VARUN_IMG_DIR = os.path.join(BASE_DIR, "ball!", "Ball Calib(Varun-04-10)")
VARUN_LBL_DIR = os.path.join(BASE_DIR, "ball!", "ball-", "labels", "train")

NAIMI_IMG_DIR = os.path.join(BASE_DIR, "new data", "StumpCalib(NAIMI)_7-10")
NAIMI_LBL_DIR = os.path.join(BASE_DIR, "new data", "naimi ball", "labels", "train")

def canon(name):
    return re.sub(r'\s+', '', os.path.splitext(name)[0])

def build_dataset():
    random.seed(42)
    print("=" * 70)
    print("BUILDING UNIFIED PURE IMAGE BALL DETECTION DATASET")
    print("=" * 70)

    # 1. Gather Varun pairs
    v_imgs = {os.path.splitext(f)[0]: f for f in os.listdir(VARUN_IMG_DIR) if not f.startswith('.')}
    v_lbls = {os.path.splitext(f)[0]: f for f in os.listdir(VARUN_LBL_DIR) if not f.startswith('.')}
    v_keys = sorted(set(v_imgs.keys()) & set(v_lbls.keys()))
    print(f"Varun annotated image pairs: {len(v_keys)}")

    # 2. Gather Naimi pairs
    n_imgs = {canon(f): f for f in os.listdir(NAIMI_IMG_DIR) if f.endswith(('.png', '.jpg', '.jpeg'))}
    n_lbls = {canon(f): f for f in os.listdir(NAIMI_LBL_DIR) if f.endswith('.txt')}
    n_keys = sorted(set(n_imgs.keys()) & set(n_lbls.keys()))
    print(f"Naimi annotated image pairs: {len(n_keys)}")

    # 3. Gather Naimi calibration background images (negative samples)
    n_unlabeled = [n_imgs[k] for k in sorted(n_imgs.keys()) if k not in n_lbls]
    # Select 45 clean background images
    random.shuffle(n_unlabeled)
    selected_bg = n_unlabeled[:45]
    print(f"Naimi clean calibration background images (negatives): {len(selected_bg)}")

    # Prepare output directory
    img_out_dir = os.path.join(OUTPUT_DIR, "images")
    lbl_out_dir = os.path.join(OUTPUT_DIR, "labels")
    os.makedirs(img_out_dir, exist_ok=True)
    os.makedirs(lbl_out_dir, exist_ok=True)

    records = []
    global_id = 1

    # Copy Varun images & labels
    for k in v_keys:
        src_img = os.path.join(VARUN_IMG_DIR, v_imgs[k])
        src_lbl = os.path.join(VARUN_LBL_DIR, v_lbls[k])
        ext = os.path.splitext(v_imgs[k])[1].lower()
        dst_img_name = f"ball_img_{global_id:04d}{ext}"
        dst_lbl_name = f"ball_img_{global_id:04d}.txt"

        dst_img_path = os.path.join(img_out_dir, dst_img_name)
        dst_lbl_path = os.path.join(lbl_out_dir, dst_lbl_name)

        shutil.copy2(src_img, dst_img_path)
        shutil.copy2(src_lbl, dst_lbl_path)

        records.append({
            "id": global_id,
            "filename": dst_img_name,
            "image_path": dst_img_path,
            "label_path": dst_lbl_path,
            "source": "varun_image",
            "is_background": False
        })
        global_id += 1

    # Copy Naimi images & labels
    for k in n_keys:
        src_img = os.path.join(NAIMI_IMG_DIR, n_imgs[k])
        src_lbl = os.path.join(NAIMI_LBL_DIR, n_lbls[k])
        ext = os.path.splitext(n_imgs[k])[1].lower()
        dst_img_name = f"ball_img_{global_id:04d}{ext}"
        dst_lbl_name = f"ball_img_{global_id:04d}.txt"

        dst_img_path = os.path.join(img_out_dir, dst_img_name)
        dst_lbl_path = os.path.join(lbl_out_dir, dst_lbl_name)

        shutil.copy2(src_img, dst_img_path)
        shutil.copy2(src_lbl, dst_lbl_path)

        records.append({
            "id": global_id,
            "filename": dst_img_name,
            "image_path": dst_img_path,
            "label_path": dst_lbl_path,
            "source": "naimi_image",
            "is_background": False
        })
        global_id += 1

    # Copy background images (empty label files)
    for bg_f in selected_bg:
        src_img = os.path.join(NAIMI_IMG_DIR, bg_f)
        ext = os.path.splitext(bg_f)[1].lower()
        dst_img_name = f"ball_img_{global_id:04d}{ext}"
        dst_lbl_name = f"ball_img_{global_id:04d}.txt"

        dst_img_path = os.path.join(img_out_dir, dst_img_name)
        dst_lbl_path = os.path.join(lbl_out_dir, dst_lbl_name)

        shutil.copy2(src_img, dst_img_path)
        with open(dst_lbl_path, "w") as f:
            pass  # empty label for negative image

        records.append({
            "id": global_id,
            "filename": dst_img_name,
            "image_path": dst_img_path,
            "label_path": dst_lbl_path,
            "source": "naimi_calibration_bg",
            "is_background": True
        })
        global_id += 1

    # Save manifest
    manifest_path = os.path.join(OUTPUT_DIR, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(records, f, indent=2)

    print(f"Total unified images assembled: {len(records)}")
    print(f"  - Varun annotated balls: {len(v_keys)}")
    print(f"  - Naimi annotated balls: {len(n_keys)}")
    print(f"  - Calibration negative backgrounds: {len(selected_bg)}")
    print(f"Saved manifest to {manifest_path}")

if __name__ == '__main__':
    build_dataset()
