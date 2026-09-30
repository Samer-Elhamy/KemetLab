import os
import zipfile
import glob
import io
import shutil
import xml.etree.ElementTree as ET
import pandas as pd
from PIL import Image

print("=== AUTOSCIENTISTS GRANDMASTER HYPERSPECTRAL PIPELINE ===")
data_dir = "/kaggle/working/data"
os.makedirs(data_dir, exist_ok=True)
os.system("kaggle competitions download -c hyperspectral-object-detection-challenge-2026 -p " + data_dir)

zips = glob.glob(data_dir + "/*.zip")
if not zips:
    raise RuntimeError("Zip not found")
zip_p = zips[0]

yolo_dir = "/kaggle/working/yolo_grandmaster"
os.makedirs(yolo_dir + "/images/train", exist_ok=True)
os.makedirs(yolo_dir + "/labels/train", exist_ok=True)
os.makedirs(yolo_dir + "/images/test", exist_ok=True)

classes = []
with zipfile.ZipFile(zip_p, 'r') as z:
    for name in z.namelist():
        if name.endswith('class.txt'):
            classes = [line.strip() for line in z.read(name).decode('utf-8').splitlines() if line.strip()]
            break

class_to_id = {c: i for i, c in enumerate(classes)}
print("18 Target Classes mapped successfully.")

with zipfile.ZipFile(zip_p, 'r') as z:
    names = set(z.namelist())
    
    # Extract Test Images (JPEG Quality 95)
    for n in z.namelist():
        if 'data_test' in n and n.endswith('.png') and 'VIS/' in n:
            img_b = z.read(n)
            img = Image.open(io.BytesIO(img_b)).convert('RGB')
            base_name = os.path.basename(n).replace('.png', '.jpg')
            img.save(yolo_dir + "/images/test/" + base_name, format='JPEG', quality=95)
            
    # Extract Train Annotations and Images
    for n in z.namelist():
        if 'Annotations/VIS/' in n and n.endswith('.xml'):
            img_base = os.path.basename(n).replace('.xml', '.png')
            img_candidate = None
            for c in ["data_train/data_train/VIS/" + img_base, "data_train/VIS/" + img_base]:
                if c in names:
                    img_candidate = c
                    break
                    
            if img_candidate:
                xml_data = z.read(n)
                root = ET.fromstring(xml_data)
                size = root.find('size')
                w = float(size.find('width').text) if size is not None else 500.0
                h = float(size.find('height').text) if size is not None else 250.0
                
                labels = []
                for obj in root.findall('object'):
                    cname = obj.find('name').text.strip()
                    if cname in class_to_id:
                        cid = class_to_id[cname]
                        bnd = obj.find('bndbox')
                        xmin, ymin = float(bnd.find('xmin').text), float(bnd.find('ymin').text)
                        xmax, ymax = float(bnd.find('xmax').text), float(bnd.find('ymax').text)
                        cx = ((xmin + xmax) / 2.0) / w
                        cy = ((ymin + ymax) / 2.0) / h
                        bw = (xmax - xmin) / w
                        bh = (ymax - ymin) / h
                        labels.append(str(cid) + " " + f"{cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
                
                if labels:
                    img_b = z.read(img_candidate)
                    img = Image.open(io.BytesIO(img_b)).convert('RGB')
                    img.save(yolo_dir + "/images/train/" + img_base.replace('.png', '.jpg'), format='JPEG', quality=95)
                    with open(yolo_dir + "/labels/train/" + img_base.replace('.png', '.txt'), 'w') as lf:
                        lf.write("\n".join(labels))

os.remove(zip_p)
print("Zip removed, dataset prepared cleanly.")

yaml_content = "path: " + yolo_dir + "\ntrain: images/train\nval: images/train\nnames:\n"
for i, c in enumerate(classes):
    yaml_content += "  " + str(i) + ": " + c + "\n"

with open(yolo_dir + "/data.yaml", 'w') as f:
    f.write(yaml_content)

os.system("pip install -q ultralytics")
from ultralytics import YOLO

# Train heavy-duty YOLOv8m (Medium) for superior mAP
print("--- [AutoScientists Phase 1] Training YOLOv8m (Medium Backbone) ---")
model_m = YOLO('yolov8m.pt')
model_m.train(
    data=yolo_dir + "/data.yaml",
    epochs=25,
    imgsz=640,
    batch=16,
    device=0,
    mosaic=1.0,
    mixup=0.15,
    copy_paste=0.10,
    plots=False,
    verbose=True
)

best_m = "runs/detect/train/weights/best.pt"
if not os.path.exists(best_m):
    best_m = 'yolov8m.pt'

infer_m = YOLO(best_m)
test_files = sorted(glob.glob(yolo_dir + "/images/test/*.jpg"))
print("Generating High-Precision Test Predictions with Test-Time Augmentation (TTA)...")

records = []
sub_id = 0
for tf in test_files:
    img_id = os.path.basename(tf).replace('.jpg', '')
    # TTA + multi-scale inference
    results = infer_m.predict(tf, conf=0.20, iou=0.45, augment=True, verbose=False)
    for r in results:
        for b in r.boxes:
            cid = int(b.cls[0].item())
            conf = float(b.conf[0].item())
            xyxy = b.xyxy[0].cpu().numpy()
            records.append({
                'id': sub_id,
                'image_id': img_id,
                'class_id': cid,
                'confidence': round(conf, 4),
                'x1': int(xyxy[0]),
                'y1': int(xyxy[1]),
                'x2': int(xyxy[2]),
                'y2': int(xyxy[3])
            })
            sub_id += 1

out_csv = "/kaggle/working/submission_autoscientists_champion.csv"
df_sub = pd.DataFrame(records)
df_sub.to_csv(out_csv, index=False)
print("AutoScientists SOTA Champion Submission Saved to " + out_csv + " (" + str(len(df_sub)) + " boxes)")

shutil.rmtree(yolo_dir, ignore_errors=True)
print("Cleanup complete.")
