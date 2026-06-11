"""
Face Recognition Utility
Handles embedding generation, storage, and matching
"""

import os
import cv2
import numpy as np
import logging
import base64
import urllib.request
from datetime import datetime

logger = logging.getLogger(__name__)

# Check for face_recognition library (dlib backend)
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    logger.warning("face_recognition not available. Using OpenCV fallback.")
    FACE_RECOGNITION_AVAILABLE = False

# DNN model path settings
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "model")
YUNET_PATH = os.path.join(MODEL_DIR, "face_detection_yunet_2023mar.onnx")
SFACE_PATH = os.path.join(MODEL_DIR, "face_recognition_sface_2021dec.onnx")

_yunet_detector = None
_sface_recognizer = None
YUNET_SFACE_AVAILABLE = False

def _ensure_models_downloaded():
    global YUNET_SFACE_AVAILABLE
    try:
        os.makedirs(MODEL_DIR, exist_ok=True)
        
        # Download YuNet if missing
        if not os.path.exists(YUNET_PATH):
            logger.info("Downloading YuNet face detection model...")
            url = "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx"
            urllib.request.urlretrieve(url, YUNET_PATH)
            logger.info("YuNet model downloaded successfully.")
            
        # Download SFace if missing
        if not os.path.exists(SFACE_PATH):
            logger.info("Downloading SFace face recognition model...")
            url = "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx"
            urllib.request.urlretrieve(url, SFACE_PATH)
            logger.info("SFace model downloaded successfully.")
            
        YUNET_SFACE_AVAILABLE = True
    except Exception as e:
        logger.warning(f"Could not download or initialize YuNet/SFace models: {e}. Falling back to basic OpenCV cascade/grayscale.")
        YUNET_SFACE_AVAILABLE = False

# Auto-download models if face_recognition library is not available
if not FACE_RECOGNITION_AVAILABLE:
    _ensure_models_downloaded()

def _get_yunet_detector(frame_width=320, frame_height=320):
    global _yunet_detector, YUNET_SFACE_AVAILABLE
    if not YUNET_SFACE_AVAILABLE:
        return None
    try:
        if _yunet_detector is None:
            _yunet_detector = cv2.FaceDetectorYN.create(
                model=YUNET_PATH,
                config="",
                input_size=(frame_width, frame_height),
                score_threshold=0.6,
                nms_threshold=0.3,
                top_k=5000,
                backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
                target_id=cv2.dnn.DNN_TARGET_CPU
            )
        else:
            _yunet_detector.setInputSize((frame_width, frame_height))
        return _yunet_detector
    except Exception as e:
        logger.error(f"Error creating YuNet detector: {e}")
        YUNET_SFACE_AVAILABLE = False
        return None

def _get_sface_recognizer():
    global _sface_recognizer, YUNET_SFACE_AVAILABLE
    if not YUNET_SFACE_AVAILABLE:
        return None
    try:
        if _sface_recognizer is None:
            _sface_recognizer = cv2.FaceRecognizerSF.create(
                model=SFACE_PATH,
                config="",
                backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
                target_id=cv2.dnn.DNN_TARGET_CPU
            )
        return _sface_recognizer
    except Exception as e:
        logger.error(f"Error creating SFace recognizer: {e}")
        YUNET_SFACE_AVAILABLE = False
        return None


def generate_face_embedding(image_path: str) -> list | None:
    """Generate face embedding from image file."""
    try:
        if FACE_RECOGNITION_AVAILABLE:
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)
            if encodings:
                return encodings[0].tolist()
            logger.warning(f"No face found in {image_path}")
            return None
        else:
            return _opencv_face_embedding(image_path)
    except Exception as e:
        logger.error(f"Embedding generation error: {e}")
        return None


def generate_face_embedding_from_array(img_array: np.ndarray) -> list | None:
    """Generate embedding from numpy array (BGR from OpenCV)."""
    try:
        if FACE_RECOGNITION_AVAILABLE:
            rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
            encodings = face_recognition.face_encodings(rgb)
            if encodings:
                return encodings[0].tolist()
            return None
        else:
            return _opencv_face_embedding_array(img_array)
    except Exception as e:
        logger.error(f"Embedding from array error: {e}")
        return None


def match_face(unknown_embedding: list, known_embeddings: list,
               tolerance: float = 0.5) -> dict:
    """
    Match unknown face against a list of known embeddings.
    Returns dict with: matched (bool), patient_id, confidence, index
    """
    if not unknown_embedding or not known_embeddings:
        return {"matched": False, "patient_id": None, "confidence": 0, "index": -1}

    try:
        if FACE_RECOGNITION_AVAILABLE:
            unknown = np.array(unknown_embedding)
            distances = []
            for item in known_embeddings:
                emb = np.array(item["embedding"])
                dist = np.linalg.norm(unknown - emb)
                distances.append(dist)

            if not distances:
                return {"matched": False, "patient_id": None, "confidence": 0, "index": -1}

            min_idx  = int(np.argmin(distances))
            min_dist = distances[min_idx]

            if min_dist <= tolerance:
                confidence = float(max(0, (1 - min_dist / tolerance) * 100))
                return {
                    "matched":    True,
                    "patient_id": known_embeddings[min_idx]["patient_id"],
                    "patient_name": known_embeddings[min_idx].get("name", "Unknown"),
                    "mdr_status": known_embeddings[min_idx].get("mdr_status", 0),
                    "mdr_probability": known_embeddings[min_idx].get("mdr_probability", 0),
                    "risk_level": known_embeddings[min_idx].get("risk_level", "Low"),
                    "confidence": round(confidence, 2),
                    "index":      min_idx
                }
        else:
            # OpenCV fallback matching using unit-normalized vector Euclidean distance
            unknown = np.array(unknown_embedding, dtype=np.float32)
            unknown_norm = np.linalg.norm(unknown)
            if unknown_norm > 0:
                unknown = unknown / unknown_norm

            distances = []
            for item in known_embeddings:
                emb = np.array(item["embedding"], dtype=np.float32)
                if emb.shape != unknown.shape:
                    distances.append(float('inf'))
                    continue
                emb_norm = np.linalg.norm(emb)
                if emb_norm > 0:
                    emb = emb / emb_norm
                dist = np.linalg.norm(unknown - emb)
                distances.append(dist)

            if not distances:
                return {"matched": False, "patient_id": None, "confidence": 0, "index": -1}

            min_idx  = int(np.argmin(distances))
            min_dist = distances[min_idx]

            # Choose appropriate tolerance threshold based on embedding size
            if len(unknown_embedding) == 128:
                # SFace embeddings (128-d)
                fallback_tolerance = 1.12 * (tolerance / 0.5)
            else:
                # Legacy 4096-d grayscale embeddings
                fallback_tolerance = tolerance * 1.5 if tolerance < 1.0 else tolerance

            if min_dist <= fallback_tolerance:
                confidence = float(max(0, (1 - min_dist / fallback_tolerance) * 100))
                return {
                    "matched":    True,
                    "patient_id": known_embeddings[min_idx]["patient_id"],
                    "patient_name": known_embeddings[min_idx].get("name", "Unknown"),
                    "mdr_status": known_embeddings[min_idx].get("mdr_status", 0),
                    "mdr_probability": known_embeddings[min_idx].get("mdr_probability", 0),
                    "risk_level": known_embeddings[min_idx].get("risk_level", "Low"),
                    "confidence": round(confidence, 2),
                    "index":      min_idx
                }

        return {"matched": False, "patient_id": None, "confidence": 0, "index": -1}

    except Exception as e:
        logger.error(f"Face matching error: {e}")
        return {"matched": False, "patient_id": None, "confidence": 0, "index": -1}


def detect_faces_in_frame(frame: np.ndarray) -> list:
    """Detect face locations in a frame. Returns list of (top, right, bottom, left)."""
    try:
        if FACE_RECOGNITION_AVAILABLE:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(rgb, model="hog")
            return locations
        else:
            return _opencv_detect_faces(frame)
    except Exception as e:
        logger.error(f"Face detection error: {e}")
        return []


def get_face_encodings_from_frame(frame: np.ndarray, locations: list) -> list:
    """Get face encodings for given locations in a frame."""
    try:
        if FACE_RECOGNITION_AVAILABLE:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            encodings = face_recognition.face_encodings(rgb, locations)
            return [e.tolist() for e in encodings]
        elif YUNET_SFACE_AVAILABLE:
            detector = _get_yunet_detector(frame.shape[1], frame.shape[0])
            recognizer = _get_sface_recognizer()
            
            if detector is not None and recognizer is not None:
                retval, faces = detector.detect(frame)
                encodings = []
                
                # If no faces detected by YuNet but locations are provided, return zero embeddings
                if not retval or faces is None or len(faces) == 0:
                    return [[0] * 128] * len(locations)
                
                for loc in locations:
                    top, right, bottom, left = loc
                    loc_center = ((left + right) / 2, (top + bottom) / 2)
                    
                    # Find the face with the closest bounding box center
                    best_face = None
                    min_dist = float('inf')
                    for face in faces:
                        fx, fy, fw, fh = map(int, face[0:4])
                        face_center = (fx + fw/2, fy + fh/2)
                        dist = (loc_center[0] - face_center[0])**2 + (loc_center[1] - face_center[1])**2
                        if dist < min_dist:
                            min_dist = dist
                            best_face = face
                    
                    # Generate embedding for the matched face
                    if best_face is not None:
                        aligned_face = recognizer.alignCrop(frame, best_face)
                        embedding = recognizer.feature(aligned_face)
                        encodings.append(embedding[0].tolist())
                    else:
                        encodings.append([0] * 128)
                return encodings
            else:
                return [[0] * 128] * len(locations)
        else:
            # OpenCV basic fallback: extract resized grayscale region for each location
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            encodings = []
            h, w = gray.shape[:2]
            for loc in locations:
                top, right, bottom, left = loc
                top = max(0, min(top, h - 1))
                bottom = max(0, min(bottom, h))
                left = max(0, min(left, w - 1))
                right = max(0, min(right, w))
                if bottom - top > 0 and right - left > 0:
                    face_region = cv2.resize(gray[top:bottom, left:right], (64, 64))
                    encodings.append(face_region.flatten().tolist())
                else:
                    encodings.append([0] * 4096)
            return encodings
    except Exception as e:
        logger.error(f"Get encodings from frame error: {e}")
        return []


def frame_to_base64(frame: np.ndarray) -> str:
    """Convert OpenCV frame to base64 string."""
    try:
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buffer).decode("utf-8")
    except Exception as e:
        logger.error(f"Frame to base64 error: {e}")
        return ""


def save_detected_face(frame: np.ndarray, location: tuple, save_dir: str,
                       patient_id: str) -> str | None:
    """Crop and save detected face from frame."""
    try:
        top, right, bottom, left = location
        padding = 20
        h, w = frame.shape[:2]
        top    = max(0, top - padding)
        right  = min(w, right + padding)
        bottom = min(h, bottom + padding)
        left   = max(0, left - padding)

        face_img  = frame[top:bottom, left:right]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename  = f"{patient_id}_{timestamp}.jpg"
        filepath  = os.path.join(save_dir, filename)
        cv2.imwrite(filepath, face_img)
        return filename
    except Exception as e:
        logger.error(f"Save face error: {e}")
        return None


def draw_recognition_box(frame: np.ndarray, location: tuple,
                         label: str, color: tuple, confidence: float = 0) -> np.ndarray:
    """Draw bounding box and label on frame."""
    top, right, bottom, left = location
    cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

    # Background for text
    label_text = f"{label} ({confidence:.1f}%)" if confidence else label
    (w, h), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(frame, (left, top - h - 10), (left + w + 4, top), color, -1)
    cv2.putText(frame, label_text, (left + 2, top - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return frame


# ── OpenCV fallbacks when face_recognition is unavailable ─────────────────────

def _opencv_face_embedding(image_path: str) -> list | None:
    try:
        img  = cv2.imread(image_path)
        if img is None:
            return None
        
        detector = _get_yunet_detector(img.shape[1], img.shape[0])
        recognizer = _get_sface_recognizer()
        
        if YUNET_SFACE_AVAILABLE and detector is not None and recognizer is not None:
            retval, faces = detector.detect(img)
            if retval and faces is not None and len(faces) > 0:
                aligned_face = recognizer.alignCrop(img, faces[0])
                embedding = recognizer.feature(aligned_face)
                return embedding[0].tolist()
            logger.warning(f"YuNet found no face in {image_path}")
            return None
        else:
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            if len(faces) == 0:
                return None
            x, y, w, h = faces[0]
            face_region = cv2.resize(gray[y:y+h, x:x+w], (64, 64))
            return face_region.flatten().tolist()
    except Exception as e:
        logger.error(f"OpenCV face embedding error: {e}")
        return None


def _opencv_face_embedding_array(img_array: np.ndarray) -> list | None:
    try:
        if img_array is None:
            return None
            
        detector = _get_yunet_detector(img_array.shape[1], img_array.shape[0])
        recognizer = _get_sface_recognizer()
        
        if YUNET_SFACE_AVAILABLE and detector is not None and recognizer is not None:
            retval, faces = detector.detect(img_array)
            if retval and faces is not None and len(faces) > 0:
                aligned_face = recognizer.alignCrop(img_array, faces[0])
                embedding = recognizer.feature(aligned_face)
                return embedding[0].tolist()
            return None
        else:
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            gray  = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            if len(faces) == 0:
                return None
            x, y, w, h = faces[0]
            face_region = cv2.resize(gray[y:y+h, x:x+w], (64, 64))
            return face_region.flatten().tolist()
    except Exception as e:
        logger.error(f"OpenCV face embedding array error: {e}")
        return None


def _opencv_detect_faces(frame: np.ndarray) -> list:
    try:
        detector = _get_yunet_detector(frame.shape[1], frame.shape[0])
        if YUNET_SFACE_AVAILABLE and detector is not None:
            retval, faces = detector.detect(frame)
            locations = []
            if retval and faces is not None:
                for face in faces:
                    x, y, w, h = map(int, face[0:4])
                    locations.append((y, x + w, y + h, x))
            return locations
        else:
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            locations = []
            for (x, y, w, h) in faces:
                locations.append((int(y), int(x + w), int(y + h), int(x)))  # (top, right, bottom, left)
            return locations
    except Exception as e:
        logger.error(f"OpenCV detect faces error: {e}")
        return []
