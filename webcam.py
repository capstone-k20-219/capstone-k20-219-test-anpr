import cv2
import torch
import os
import sys
import function.utils_rotate as utils_rotate
import re
import function.helper as helper
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, db

pattern = re.compile("^(1[1-2]|1[4-9]|[2-9][0-9])[A-Z]([0-9A-Z]|[A-Z][0-9])?-[0-9]{4,5}$")

# Check camera type: checkin - checkout
cameraType = sys.argv[1]

# load model
yolo_LP_detect = torch.hub.load('yolov5', 'custom', path='model/LP_detector_nano_61.pt', force_reload=True, source='local')
yolo_license_plate = torch.hub.load('yolov5', 'custom', path='model/LP_ocr_nano_62.pt', force_reload=True, source='local')
yolo_license_plate.conf = 0.60

# Load the Firebase credentials and initialize the Firebase app
load_dotenv()
cred = credentials.Certificate("credentials.json")
firebase_admin.initialize_app(cred, {
    "databaseURL": os.getenv("FIREBASE_DB_URL"),
})

# Get the reference to the Firebase database node
ref = db.reference("scanData/plateNumberIn") if cameraType == "checkin" else db.reference("scanData/plateNumberOut")

# Open the camera
cv2.namedWindow("ANPR", cv2.WINDOW_NORMAL)
cv2.setWindowProperty("ANPR", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
vid = cv2.VideoCapture(0)

# Check if the camera is opened or not
if vid.isOpened():
    rval, frame = vid.read()
else:
    rval = False
    print("Failed to open camera")

# Start the loop to read the LP
while(True):
    ret, frame = vid.read()
    # detect the license plate
    plates = yolo_LP_detect(frame, size=640)
    list_plates = plates.pandas().xyxy[0].values.tolist() # multiple detected plates
    list_read_plates = set()
    # detect plate number
    for plate in list_plates:
        flag = 0
        x = int(plate[0]) # xmin
        y = int(plate[1]) # ymin
        w = int(plate[2] - plate[0]) # xmax - xmin
        h = int(plate[3] - plate[1]) # ymax - ymin  
        crop_img = frame[y:y+h, x:x+w]
        cv2.rectangle(frame, (int(plate[0]),int(plate[1])), (int(plate[2]),int(plate[3])), color = (0,0,225), thickness = 2)
        cv2.imwrite("plate.jpg", crop_img)
        rc_image = cv2.imread("plate.jpg")
        lp = ""
        for cc in range(0,2):
            for ct in range(0,2):
                # read the plate number
                lp = helper.read_plate(yolo_license_plate, utils_rotate.deskew(crop_img, cc, ct))
                # plate number validation
                if lp != "unknown" and re.fullmatch(pattern, lp) is not None:
                    list_read_plates.add(lp)
                    cv2.putText(frame, "LP: " + lp, (int(plate[0]), int(plate[1]-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (36,255,12), 2)
                    ref.set(lp)
                    flag = 1
                    break
            if flag == 1:
                break
    cv2.imshow('ANPR', frame)
    key = cv2.waitKey(20)
    if key == 27: # exit on ESC
        break

vid.release()
cv2.destroyAllWindows()