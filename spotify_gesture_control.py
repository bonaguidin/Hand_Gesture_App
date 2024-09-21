import cv2
import numpy as np
import pyautogui
import os
import mediapipe as mp
import time
import threading
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
import spotipy
import requests
import webbrowser
from urllib.parse import urlencode
import base64
from collections import deque

# Spotify API credentials
CLIENT_ID = "__ENTER_CLIENT_ID_HERE__"
CLIENT_SECRET = "__ENTER_CLIENT_SECRET_HERE__"
REDIRECT_URI = "http://localhost:8888/callback"

SCOPE = "user-modify-playback-state user-read-playback-state"
AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
API_BASE_URL = 'https://api.spotify.com/v1/'

# Set up Spotify client
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=SCOPE,
    open_browser=True
))

# MediaPipe setup
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.9)
mp_drawing = mp.solutions.drawing_utils

# Global variables
last_spotify_open_time = 0
spotify_open_cooldown = 3
status_text = ''
action_text = ''
last_gesture = ''
gesture_cooldown = 3  # cooldown time in seconds
last_gesture_time = 0
gesture_history = deque(maxlen=10)
gesture_confidence_threshold = 0.7

def refresh_spotify_token():
    global sp
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        open_browser=True
    ))

# OPTIONAL, can remove if wanted
def wait_before_start():
    print("Preparing to start hand gesture recognition...")
    for i in range(2, 0, -1):
        print(f"Starting in {i} seconds...")
        time.sleep(1)
    print("Starting hand gesture recognition now!")

def open_spotify():
    global action_text
    action_text = 'Opening Spotify'
    try:
        if os.name == 'nt':  # For Windows
            os.system('start spotify:')
        elif os.name == 'posix':  # For macOS and Linux
            os.system('open -a Spotify')
        else:
            print("Unsupported operating system")
        print("Spotify open command executed")

        # Wait for Spotify to open and become active
        for _ in range(1):  # Try for 3 seconds
            time.sleep(1)
            if get_active_device():
                print("Spotify is now active")
                return True
        print("Spotify didn't become active in time")
        return False
    except Exception as e:
        print(f"Error opening Spotify: {e}")
        return False

def close_spotify():
    os.system("taskkill /F /IM Spotify.exe")

def execute_spotify_command(gesture):
    global action_text, last_spotify_open_time, last_gesture, last_gesture_time

    # Implement gesture cooldown
    current_time = time.time()
    if current_time - last_gesture_time < gesture_cooldown:
        return
    last_gesture_time = current_time
    last_gesture = gesture

    device_id = ensure_device_is_active()
    if not device_id:
        print("No active Spotify device found. Please make sure Spotify is running.")
        return

    try:
        if gesture == "pause_play":
            action_text = 'Gesture recognized: Play/Pause'
            current_playback = sp.current_playback()
            if current_playback and current_playback['is_playing']:
                sp.pause_playback(device_id=device_id)
            else:
                sp.start_playback(device_id=device_id)
        elif gesture == "next":
            action_text = 'Gesture recognized: Next Track'
            sp.next_track(device_id=device_id)
        elif gesture == "previous":
            action_text = 'Gesture recognized: Previous Track'
            sp.previous_track(device_id=device_id)
        elif gesture == "close_spotify":
            action_text = 'Gesture recognized: Closing Spotify'
            close_spotify()
        elif gesture == "open_spotify":
            action_text = 'Gesture recognized: Opening Spotify'
            if time.time() - last_spotify_open_time > spotify_open_cooldown:
                if open_spotify():
                    last_spotify_open_time = time.time()
                else:
                    print("Failed to open Spotify")
    except SpotifyException as e:
        print(f"Spotify error: {e}")

def get_active_device():
    try:
        devices = sp.devices()
        active_devices = [device for device in devices['devices'] if device['is_active']]
        return active_devices[0]['id'] if active_devices else None
    except SpotifyException as e:
        print(f"Error getting active device: {e}")
        return None

# Spotify will return an error if it cannot find an open device. Can be Desktop Version or Webplayer
def ensure_device_is_active():
    device_id = get_active_device()
    if not device_id:
        try:
            devices = sp.devices()
            if devices['devices']:
                sp.transfer_playback(devices['devices'][0]['id'], force_play=False)
                return devices['devices'][0]['id']
            else:
                print("No Spotify devices found. Attempting to open Spotify...")
                if open_spotify():
                    return get_active_device()
        except SpotifyException as e:
            print(f"Error activating device: {e}")
    return device_id

# Function to ensure there are not unwanted repeat action. Adjust as desired
def execute_command_with_delay(action):
    def delayed_execution():
        time.sleep(2)
        action()

    thread = threading.Thread(target=delayed_execution)
    thread.start()


def calculate_finger_angles(landmarks):
    wrist = landmarks[mp_hands.HandLandmark.WRIST]
    finger_angles = []
    for finger_tip_id in [mp_hands.HandLandmark.THUMB_TIP, mp_hands.HandLandmark.INDEX_FINGER_TIP, 
                          mp_hands.HandLandmark.MIDDLE_FINGER_TIP, mp_hands.HandLandmark.RING_FINGER_TIP, 
                          mp_hands.HandLandmark.PINKY_TIP]:
        finger_tip = landmarks[finger_tip_id]
        angle = np.arctan2(finger_tip.y - wrist.y, finger_tip.x - wrist.x)
        finger_angles.append(angle)
    return finger_angles

# Hand gesture recognition. Change if you would like to add/adjust hands signs
def recognize_gesture(landmarks):
    def is_finger_extended(finger_tip, finger_pip, wrist):
        return landmarks[finger_tip].y < landmarks[finger_pip].y < landmarks[wrist].y

    wrist = landmarks[mp_hands.HandLandmark.WRIST]
    
    thumb_tip = landmarks[mp_hands.HandLandmark.THUMB_TIP]
    index_tip = landmarks[mp_hands.HandLandmark.INDEX_FINGER_TIP]
    
    thumb_extended = landmarks[mp_hands.HandLandmark.THUMB_TIP].x < landmarks[mp_hands.HandLandmark.THUMB_IP].x
    index_extended = is_finger_extended(mp_hands.HandLandmark.INDEX_FINGER_TIP, mp_hands.HandLandmark.INDEX_FINGER_PIP, mp_hands.HandLandmark.WRIST)
    middle_extended = is_finger_extended(mp_hands.HandLandmark.MIDDLE_FINGER_TIP, mp_hands.HandLandmark.MIDDLE_FINGER_PIP, mp_hands.HandLandmark.WRIST)
    ring_extended = is_finger_extended(mp_hands.HandLandmark.RING_FINGER_TIP, mp_hands.HandLandmark.RING_FINGER_PIP, mp_hands.HandLandmark.WRIST)
    pinky_extended = is_finger_extended(mp_hands.HandLandmark.PINKY_TIP, mp_hands.HandLandmark.PINKY_PIP, mp_hands.HandLandmark.WRIST)

    # Check for "OK" sign (close_spotify)
    thumb_index_distance = ((thumb_tip.x - index_tip.x)**2 + (thumb_tip.y - index_tip.y)**2)**0.5
    ok_sign = thumb_index_distance < 0.1 and middle_extended and ring_extended and pinky_extended

    if ok_sign:
        return "close_spotify", 0.9
    elif index_extended and not (thumb_extended or middle_extended or ring_extended or pinky_extended):
        return "next", 0.9
    elif index_extended and middle_extended and not (thumb_extended or ring_extended or pinky_extended):
        return "open_spotify", 0.9
    elif index_extended and middle_extended and ring_extended and pinky_extended:
        return "pause_play", 0.9
    elif thumb_extended and not (index_extended or middle_extended or ring_extended or pinky_extended):
        return "previous", 0.9

    return "unknown", 0.0

def get_dominant_gesture(gesture_history):
    if not gesture_history:
        return "unknown", 0.0
    
    gesture_counts = {}
    for gesture, confidence in gesture_history:
        if gesture not in gesture_counts:
            gesture_counts[gesture] = {"count": 0, "total_confidence": 0}
        gesture_counts[gesture]["count"] += 1
        gesture_counts[gesture]["total_confidence"] += confidence
    
    dominant_gesture = max(gesture_counts, key=lambda x: gesture_counts[x]["count"])
    average_confidence = gesture_counts[dominant_gesture]["total_confidence"] / gesture_counts[dominant_gesture]["count"]
    
    return dominant_gesture, average_confidence



def main():
    global status_text, action_text
    cap = cv2.VideoCapture(0)

    wait_before_start()
    status_text = 'Hand Gesture Recognition Started'

    while cap.isOpened():
        success, image = cap.read()
        if not success:
            continue

        image = cv2.cvtColor(cv2.flip(image, 1), cv2.COLOR_BGR2RGB)
        results = hands.process(image)

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(image, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                gesture, confidence = recognize_gesture(hand_landmarks.landmark)
                gesture_history.append((gesture, confidence))
                
                dominant_gesture, avg_confidence = get_dominant_gesture(gesture_history)
                if dominant_gesture != "unknown" and avg_confidence > gesture_confidence_threshold:
                    execute_spotify_command(dominant_gesture)
                    gesture_history.clear()  # Clear history after executing a command

        cv2.putText(image, status_text, (10, 30), cv2.FONT_HERSHEY_DUPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(image, action_text, (10, 70), cv2.FONT_HERSHEY_DUPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

        cv2.imshow('Hand Gesture Recognition', cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        if cv2.waitKey(5) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    hands.close()

if __name__ == "__main__":
    main()
