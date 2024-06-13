from scipy.spatial import distance as dist
from imutils.video import VideoStream
from imutils import face_utils
from threading import Thread
import numpy as np
import argparse
import imutils
import time
import dlib
import cv2
import os
import firebase_admin
from firebase_admin import credentials, db
import RPi.GPIO as GPIO
from time import sleep

# Initialize Firebase
cred = credentials.Certificate("credentials.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://project-ngantuk-default-rtdb.asia-southeast1.firebasedatabase.app/'
})

# Buzzer setup
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
buzzer = 18
GPIO.setup(buzzer, GPIO.OUT)

# Alarm and status flags
alarm_status = False
alarm_status2 = False
saying = False
COUNTER = 0
yawn_start_time = None
eye_close_start_time = None

# Load face detector and predictor
detector = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
predictor = dlib.shape_predictor('shape_predictor_68_face_landmarks.dat')

# Argument parser for webcam index
ap = argparse.ArgumentParser()
ap.add_argument("-w", "--webcam", type=int, default=0, help="index webcam pada sistem")
args = vars(ap.parse_args())

# Constants
EYE_AR_THRESH = 0.3
EYE_AR_CONSEC_FRAMES = 30
YAWN_THRESH = 20

# Start video stream
vs = VideoStream(src=args["webcam"]).start()
time.sleep(2.0)

def send_to_firebase(status, value):
    ref = db.reference('drowsiness')
    ref.push({
        'status': status,
        'value': value,
        'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
    })

def alarm(msg):
    global alarm_status, alarm_status2, saying

    while alarm_status:
        print('call')
        s = 'espeak "' + msg + '"'
        os.system('espeak "{}"'.format(msg))
        os.system(s)

    if alarm_status2:
        print('call')
        saying = True
        s = 'espeak "' + msg + '"'
        os.system('espeak "{}"'.format(msg))
        os.system(s)
        saying = False

def eye_aspect_ratio(eye):
    A = dist.euclidean(eye[1], eye[5])
    B = dist.euclidean(eye[2], eye[4])
    C = dist.euclidean(eye[0], eye[3])
    ear = (A + B) / (2.0 * C)
    return ear

def final_ear(shape):
    (lStart, lEnd) = face_utils.FACIAL_LANDMARKS_IDXS["left_eye"]
    (rStart, rEnd) = face_utils.FACIAL_LANDMARKS_IDXS["right_eye"]
    leftEye = shape[lStart:lEnd]
    rightEye = shape[rStart:rEnd]
    leftEAR = eye_aspect_ratio(leftEye)
    rightEAR = eye_aspect_ratio(rightEye)
    ear = (leftEAR + rightEAR) / 2.0
    return (ear, leftEye, rightEye)

def lip_distance(shape):
    top_lip = shape[50:53]
    top_lip = np.concatenate((top_lip, shape[61:64]))
    low_lip = shape[56:59]
    low_lip = np.concatenate((low_lip, shape[65:68]))
    top_mean = np.mean(top_lip, axis=0)
    low_mean = np.mean(low_lip, axis=0)
    distance = abs(top_mean[1] - low_mean[1])
    return distance

def buzzer_control(state):
    if state:
        GPIO.output(buzzer, GPIO.HIGH)
        print("Beep")
    else:
        GPIO.output(buzzer, GPIO.LOW)
        print("No Beep")

while True:
    frame = vs.read()
    frame = imutils.resize(frame, width=450)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    rects = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30),
                                      flags=cv2.CASCADE_SCALE_IMAGE)

    for (x, y, w, h) in rects:
        rect = dlib.rectangle(int(x), int(y), int(x + w), int(y + h))
        shape = predictor(gray, rect)
        shape = face_utils.shape_to_np(shape)

        eye = final_ear(shape)
        ear = eye[0]
        leftEye = eye[1]
        rightEye = eye[2]
        distance = lip_distance(shape)

        leftEyeHull = cv2.convexHull(leftEye)
        rightEyeHull = cv2.convexHull(rightEye)
        cv2.drawContours(frame, [leftEyeHull], -1, (0, 255, 0), 1)
        cv2.drawContours(frame, [rightEyeHull], -1, (0, 255, 0), 1)

        lip = shape[48:60]
        cv2.drawContours(frame, [lip], -1, (0, 255, 0), 1)

        if ear < EYE_AR_THRESH:
            if eye_close_start_time is None:
                eye_close_start_time = time.time()
            elif time.time() - eye_close_start_time > 1:
                COUNTER += 1
                if COUNTER >= EYE_AR_CONSEC_FRAMES:
                    if not alarm_status:
                        alarm_status = True
                        t = Thread(target=alarm, args=('wake up sir',))
                        t.daemon = True
                        t.start()
                        send_to_firebase("Mata Mengantuk !!!", ear)
                    cv2.putText(frame, "MATA MENGANTUK!!!", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    buzzer_control(True)
        else:
            COUNTER = 0
            alarm_status = False
            eye_close_start_time = None
            buzzer_control(False)

        if distance > YAWN_THRESH:
            if yawn_start_time is None:
                yawn_start_time = time.time()
            elif time.time() - yawn_start_time > 3:
                cv2.putText(frame, "MULUT MENGUAP !!!", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                if not alarm_status2 and not saying:
                    alarm_status2 = True
                    t = Thread(target=alarm, args=('take some fresh air sir',))
                    t.daemon = True
                    t.start()
                send_to_firebase("Mulut Menguap !!!", distance)
                buzzer_control(True)
        else:
            alarm_status2 = False
            buzzer_control(False)

        cv2.putText(frame, "MATA: {:.2f}".format(ear), (300, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(frame, "MULUT: {:.2f}".format(distance), (300, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    cv2.imshow("Frame", frame)
    key = cv2.waitKey(1)
    if key == ord("q"):
        break

cv2.destroyAllWindows()
vs.stop()
GPIO.cleanup()
