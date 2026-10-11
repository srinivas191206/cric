import os
import shutil
import random
import json
import yaml

BASE = "/Users/thaladasrinivas/Downloads/stumps"
RAW_IMG_DIR = os.path.join(BASE, "ball!", "Ball Calib(Varun-04-10)")
RAW_LBL_DIR = os.path.join(BASE, "ball!", "ball-", "labels", "train")
DATASET_DIR = os.path.join(BASE, "ball_dataset")

def main():
    random.seed(42)
    print("=" * 70)
    print("BUILDING STANDARDIZED BALL DATASET (80% Train, 10% Val, 10% Test)")
    print("=" * 70)

    if os.path.exists(DATASET_DIR):
        shutil.rmtree(DATASET_DIR)

    for split in ['train', 'val', 'test']:
        os.makedirs(os.path.join(DATASET_DIR, "images", split), exist_ok=True)
        os.makedirs(os.path.join(DATASET_DIR, "labels", split), exist_ok=True)

    img_files = sorted([f for f in os.listdir(RAW_IMG_DIR) if not f.startswith('.')])
    lbl_files = sorted([f for f in os.listdir(RAW_LBL_DIR) if not f.startswith('.')])

    img_map = {os.path.splitext(f)[0]: f for f in img_files}
    lbl_map = {os.path.splitext(f)[0]: f for f in lbl_files}

    pairs = []
    for stem in sorted(img_map.keys()):
        if stem in lbl_map:
            pairs.append((img_map[stem], lbl_map[stem]))

    print(f"Total matched annotated pairs: {len(pairs)}")
    random.shuffle(pairs)

    n_tot = len(pairs)
    n_train = int(n_tot * 0.80)
    n_val = int(n_tot * 0.10)
    n_test = n_tot - n_train - n_val

    splits_data = {
        'train': pairs[:n_train],
        'val': pairs[n_train:n_train + n_val],
        'test': pairs[n_train + n_val:]
    }

    manifest = {"train": [], "val": [], "test": []}
    global_id = 1

    # Number test, then val, then train consecutively without repeating numbers
    for split_name in ['test', 'val', 'train']:
        for img_f, lbl_f in splits_data[split_name]:
            ext = os.path.splitext(img_f)[1].lower()
            num_img = f"{global_id}{ext}"
            num_lbl = f"{global_id}.txt"

            src_img = os.path.join(RAW_IMG_DIR, img_f)
            src_lbl = os.path.join(RAW_LBL_DIR, lbl_f)

            dst_img = os.path.join(DATASET_DIR, "images", split_name, num_img)
            dst_lbl = os.path.join(DATASET_DIR, "labels", split_name, num_lbl)

            shutil.copy2(src_img, dst_img)
            shutil.copy2(src_lbl, dst_lbl)

            manifest[split_name].append({
                "id": global_id,
                "original_image": img_f,
                "original_label": lbl_f,
                "numbered_image": num_img,
                "numbered_label": num_lbl
            })
            global_id += 1

    # Save manifest
    manifest_path = os.path.join(DATASET_DIR, "rename_manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    # Save data.yaml
    yaml_content = {
        'path': DATASET_DIR,
        'train': 'images/train',
        'val': 'images/val',
        'test': 'images/test',
        'names': {0: 'ball'}
    }
    yaml_path = os.path.join(DATASET_DIR, "data.yaml")
    with open(yaml_path, 'w') as f:
        yaml.dump(yaml_content, f, sort_keys=False)

    print(f"Created ball_dataset:")
    print(f"  - Train: {len(splits_data['train'])} pairs")
    print(f"  - Val:   {len(splits_data['val'])} pairs")
    print(f"  - Test:  {len(splits_data['test'])} pairs")
    print(f"  - Total: {global_id - 1} pairs consecutively numbered 1 to {global_id - 1}")
    print(f"  - YAML:  {yaml_path}")
    print(f"  - Manifest: {manifest_path}")

if __name__ == '__main__':
    main()
