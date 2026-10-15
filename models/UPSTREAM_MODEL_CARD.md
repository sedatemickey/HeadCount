---
license: mit
base_model:
- Ultralytics/YOLOv8
pipeline_tag: object-detection
---

ONNX version of https://github.com/Abcfsa/YOLOv8_head_detector





YOLOv8_head_detector
model trained for head detection,graduation project 2023-24

Info
These model are trained with yolov8 on the dataset SCUT-HEAD part A and part B. medium.pt is bigger and more accurate while nano.pt is smaller and faster.

Usage
If you already have ultralytics/yolov8 installed,then just choose one of these two models to do your prediction jobs. Else first enter these in the command line

pip install ultralytics
pip install opencv-python
pip install pandas
Basic usage:

python example.py --model path/to/model_weights.pt --source path/to/img_folder --output path/to/save.csv --mode track/detect
Output format
Depends on mode.If mode is detect,then the columns would be ["name","xmin","ymin","xmax","ymax"]. If mode is track,then there will be an additional "id" column between "name" and "xmin".
Output has no index column
"xmin",...,"ymax" are all normalized to 0-1.