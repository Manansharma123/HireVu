import cv2
import numpy as np
import mediapipe as mp
import base64
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass, asdict
from io import BytesIO
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
import math
import os

logger = logging.getLogger(__name__)
os.environ["GLOG_minloglevel"] = "2"  # Suppresses verbose MediaPipe logs
@dataclass
class ProctoringViolation:
    type: str
    message: str
    timestamp: datetime
    severity: str  # 'low', 'medium', 'high'
    frame_data: Optional[str] = None

@dataclass
class ProctoringSession:
    session_id: str
    violations: List[ProctoringViolation] = None
    is_active: bool = False
    max_violations: int = 3
    current_violations: int = 0
    session_terminated: bool = False
    
    def __post_init__(self):
        if self.violations is None:
            self.violations = []

class AdvancedFaceAnalyzer:
    """Advanced face analyzer using MediaPipe - ORIGINAL WORKING VERSION + BALANCED Face Matching"""
    
    def __init__(self):
        try:
            # Initialize MediaPipe Face Mesh
            self.mp_face_mesh = mp.solutions.face_mesh
            self.mp_drawing = mp.solutions.drawing_utils
            
            self.face_mesh = self.mp_face_mesh.FaceMesh(
                max_num_faces=10,
                refine_landmarks=True,
                min_detection_confidence=0.3,
                min_tracking_confidence=0.3
            )
            
            # Eye landmarks for gaze detection
            self.LEFT_EYE_LANDMARKS = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
            self.RIGHT_EYE_LANDMARKS = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
            
            # Nose tip landmark for head pose
            self.NOSE_TIP = 1
            
            # BALANCED: Face encoding storage
            self.reference_encoding = None
            self.face_matching_failures = 0  # Track consecutive failures
            self.max_consecutive_failures = 5  # BALANCED: Allow 5 consecutive failures before triggering
            
            logger.info("Advanced face analyzer with MediaPipe initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize MediaPipe: {e}")
            self.face_mesh = None
            raise e
    
    def set_reference_face(self, image):
        """Set reference face encoding from captured image - BALANCED"""
        try:
            # Convert to RGB if needed
            if len(image.shape) == 3 and image.shape[2] == 3:
                rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                rgb_image = image
                
            # Process with MediaPipe to get landmarks
            results = self.face_mesh.process(rgb_image)
            
            if results.multi_face_landmarks and len(results.multi_face_landmarks) > 0:
                # Extract key facial features for comparison - SIMPLE approach
                landmarks = results.multi_face_landmarks[0]
                self.reference_encoding = self.extract_simple_face_features(landmarks, rgb_image.shape)
                self.face_matching_failures = 0  # Reset failure counter
                logger.info("Reference face encoding created successfully")
                return True
            else:
                logger.warning("No face detected in reference image - disabling face matching")
                self.reference_encoding = None
                return False
                
        except Exception as e:
            logger.error(f"Error setting reference face: {e}")
            self.reference_encoding = None
            return False
    
    def extract_simple_face_features(self, landmarks, img_shape):
        """SIMPLIFIED: Extract basic facial features - balanced sensitivity"""
        try:
            height, width = img_shape[:2]
            
            # Only use most stable landmarks
            key_points = [
                1,    # Nose tip
                33,   # Left eye corner
                362,  # Right eye corner
                61,   # Upper lip center
                291,  # Right mouth corner
                17,   # Lower lip center
            ]
            
            # Extract normalized coordinates
            features = []
            for idx in key_points:
                if idx < len(landmarks.landmark):
                    landmark = landmarks.landmark[idx]
                    features.extend([landmark.x, landmark.y])
            
            # Calculate eye distance for normalization
            if len(features) >= 6:  # Need at least nose and eyes
                left_eye = np.array([features[2], features[3]])
                right_eye = np.array([features[4], features[5]])
                eye_distance = np.linalg.norm(left_eye - right_eye)
                
                # Add eye distance as a feature
                features.append(eye_distance)
                
                return np.array(features)
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting simple face features: {e}")
            return None
    
    def compare_faces(self, current_landmarks, img_shape, threshold=0.3):  # BALANCED threshold
        """BALANCED: Face comparison - detects different people but avoids false positives"""
        try:
            if self.reference_encoding is None:
                return True, 0.0  # No reference, assume same person
            
            current_encoding = self.extract_simple_face_features(current_landmarks, img_shape)
            if current_encoding is None:
                # Failed to extract features - be more lenient for a few failures
                self.face_matching_failures += 1
                if self.face_matching_failures < self.max_consecutive_failures:
                    return True, 0.0  # Give benefit of doubt for first few failures
                else:
                    return False, 0.8  # After 5 failures, assume different person
            
            # Reset failure counter on successful feature extraction
            self.face_matching_failures = 0
            
            # Compare feature vectors - BALANCED approach
            if len(current_encoding) == len(self.reference_encoding):
                # Simple euclidean distance
                distance = np.linalg.norm(current_encoding - self.reference_encoding)
                
                # Normalize by the magnitude to handle scale differences
                magnitude = np.linalg.norm(self.reference_encoding)
                if magnitude > 0:
                    normalized_distance = distance / magnitude
                else:
                    normalized_distance = distance
                
                # BALANCED threshold - detects different people but not too sensitive
                is_same_person = normalized_distance < threshold
                
                return is_same_person, normalized_distance
            else:
                return True, 0.0  # Feature size mismatch, assume same person
                
        except Exception as e:
            logger.error(f"Error comparing faces: {e}")
            return True, 0.0  # Error occurred, assume same person
    
    def detect_faces_and_analyze(self, input_image):
        """
        ORIGINAL WORKING LOGIC - keep exactly the same
        """
        try:
            # Convert BGR to RGB
            rgb_image = cv2.cvtColor(input_image, cv2.COLOR_BGR2RGB)
            
            # Process with MediaPipe
            results = self.face_mesh.process(rgb_image)
            
            analysis = {
                'face_count': 0,
                'gaze_direction': 'NO_FACE',
                'landmarks': None,
                'face_locations': [],
                'head_pose': 'CENTER',
                'identity_match': True,
                'identity_confidence': 1.0
            }
            
            if results.multi_face_landmarks:
                analysis['face_count'] = len(results.multi_face_landmarks)
                
                # Analyze first face (primary person)
                if len(results.multi_face_landmarks) > 0:
                    landmarks = results.multi_face_landmarks[0]
                    analysis['landmarks'] = landmarks
                    
                    # Calculate gaze direction - ORIGINAL WORKING
                    analysis['gaze_direction'] = self.calculate_gaze_direction(landmarks, input_image.shape)
                    
                    # Calculate head pose - ORIGINAL WORKING  
                    analysis['head_pose'] = self.calculate_head_pose(landmarks, input_image.shape)
                    
                    # BALANCED: Identity verification
                    if self.reference_encoding is not None:
                        is_same, confidence = self.compare_faces(landmarks, input_image.shape)
                        analysis['identity_match'] = is_same
                        analysis['identity_confidence'] = confidence
                    
                    # Get face bounding boxes for all faces - ORIGINAL WORKING
                    for face_landmarks in results.multi_face_landmarks:
                        bbox = self.get_face_bounding_box(face_landmarks, input_image.shape)
                        analysis['face_locations'].append(bbox)
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error in face analysis: {e}")
            return {
                'face_count': 0,
                'gaze_direction': 'NO_FACE',
                'landmarks': None,
                'face_locations': [],
                'head_pose': 'CENTER',
                'identity_match': True,
                'identity_confidence': 1.0
            }
    
    def calculate_gaze_direction(self, landmarks, img_shape):
        """ORIGINAL WORKING - Calculate gaze direction using eye landmarks"""
        try:
            height, width = img_shape[:2]
            
            # Get eye centers
            left_eye_center = self.get_eye_center(landmarks, self.LEFT_EYE_LANDMARKS, width, height)
            right_eye_center = self.get_eye_center(landmarks, self.RIGHT_EYE_LANDMARKS, width, height)
            
            # Calculate face center
            face_center_x = (left_eye_center[0] + right_eye_center[0]) / 2
            
            # Get nose tip for reference
            nose_tip = landmarks.landmark[self.NOSE_TIP]
            nose_x = nose_tip.x * width
            
            # Calculate gaze direction (same threshold as JS version)
            gaze_x = face_center_x - nose_x
            
            if abs(gaze_x) > width * 0.02:  # Same threshold as JS (0.02)
                return "LEFT" if gaze_x > 0 else "RIGHT"
            else:
                return "CENTER"
                
        except Exception as e:
            logger.error(f"Error calculating gaze direction: {e}")
            return "CENTER"
    
    def get_eye_center(self, landmarks, eye_indices, width, height):
        """ORIGINAL WORKING - Calculate eye center from landmarks"""
        sum_x = sum(landmarks.landmark[i].x for i in eye_indices)
        sum_y = sum(landmarks.landmark[i].y for i in eye_indices)
        
        center_x = (sum_x / len(eye_indices)) * width
        center_y = (sum_y / len(eye_indices)) * height
        
        return (center_x, center_y)
    
    def calculate_head_pose(self, landmarks, img_shape):
        """ORIGINAL WORKING - Calculate head pose/orientation"""
        try:
            height, width = img_shape[:2]
            
            # Get key facial landmarks
            nose_tip = landmarks.landmark[self.NOSE_TIP]
            left_eye = landmarks.landmark[33]  # Left eye corner
            right_eye = landmarks.landmark[362]  # Right eye corner
            
            # Convert to pixel coordinates
            nose_x = nose_tip.x * width
            left_eye_x = left_eye.x * width
            right_eye_x = right_eye.x * width
            
            # Calculate head rotation
            eye_center_x = (left_eye_x + right_eye_x) / 2
            nose_offset = nose_x - eye_center_x
            
            # Determine head pose
            if abs(nose_offset) > width * 0.05:
                return "LEFT" if nose_offset < 0 else "RIGHT"
            else:
                return "CENTER"
                
        except Exception as e:
            logger.error(f"Error calculating head pose: {e}")
            return "CENTER"
    
    def get_face_bounding_box(self, landmarks, img_shape):
        """ORIGINAL WORKING - Get bounding box for a face"""
        height, width = img_shape[:2]
        
        x_coords = [landmark.x * width for landmark in landmarks.landmark]
        y_coords = [landmark.y * height for landmark in landmarks.landmark]
        
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)
        
        return (int(x_min), int(y_min), int(x_max), int(y_max))

class ProctoringService:
    def __init__(self):
        self.sessions: Dict[str, ProctoringSession] = {}
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.face_analyzer = AdvancedFaceAnalyzer()
        
        # ORIGINAL WORKING - Violation thresholds - EXACTLY 5 seconds
        self.no_face_threshold = 5.0
        self.multiple_face_threshold = 5.0
        self.looking_away_threshold = 5.0
        
        # ORIGINAL WORKING - Cooldown periods - 2 seconds as original
        self.cooldown_period = 2.0
        
        # ORIGINAL WORKING - Timing tracking
        self.violation_timers = {}
        self.cooldown_timers = {}
        
    async def create_session(self, session_id: str) -> Dict:
        """ORIGINAL WORKING - Create a new proctoring session."""
        try:
            session = ProctoringSession(session_id=session_id)
            self.sessions[session_id] = session
            self.violation_timers[session_id] = {}
            self.cooldown_timers[session_id] = {}
            
            logger.info(f"Created proctoring session: {session_id}")
            return {"status": "success", "session_id": session_id}
        except Exception as e:
            logger.error(f"Error creating session {session_id}: {e}")
            return {"status": "error", "message": str(e)}
    
    async def set_reference_face(self, session_id: str, image_data: str) -> Dict:
        """ORIGINAL WORKING - Set reference face from captured image"""
        try:
            if session_id not in self.sessions:
                return {"status": "error", "message": "Session not found"}
            
            # Decode image
            if ',' in image_data:
                image_bytes = base64.b64decode(image_data.split(',')[1])
            else:
                image_bytes = base64.b64decode(image_data)
                
            nparr = np.frombuffer(image_bytes, np.uint8)
            reference_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if reference_image is None:
                return {"status": "error", "message": "Could not decode reference image"}
            
            # Set reference face in analyzer
            success = self.face_analyzer.set_reference_face(reference_image)
            
            session = self.sessions[session_id]
            session.is_active = True
            
            if success:
                logger.info(f"Reference face set and session activated: {session_id}")
                return {
                    "status": "success", 
                    "message": "Reference face captured and session activated successfully"
                }
            else:
                logger.info(f"Face detection failed but session activated anyway: {session_id}")
                return {
                    "status": "success", 
                    "message": "Session activated successfully"
                }
            
        except Exception as e:
            logger.error(f"Error setting reference face for {session_id}: {e}")
            # Still activate session on error
            if session_id in self.sessions:
                self.sessions[session_id].is_active = True
            return {"status": "success", "message": "Session activated successfully"}
    
    async def process_frame(self, session_id: str, image_data: str) -> Dict:
        """ORIGINAL WORKING - Process a video frame for proctoring violations."""
        try:
            if session_id not in self.sessions:
                return {"status": "error", "message": "Session not found"}
            
            session = self.sessions[session_id]
            if not session.is_active or session.session_terminated:
                return {"status": "inactive"}
            
            # Decode image
            if ',' in image_data:
                image_bytes = base64.b64decode(image_data.split(',')[1])
            else:
                image_bytes = base64.b64decode(image_data)
                
            nparr = np.frombuffer(image_bytes, np.uint8)
            frame_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame_image is None:
                return {"status": "error", "message": "Could not decode image"}
            
            # Run analysis in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor, 
                self._analyze_frame_fixed_reset, 
                session, frame_image
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing frame for {session_id}: {e}")
            return {"status": "error", "message": str(e)}
    
    def _analyze_frame_fixed_reset(self, session: ProctoringSession, frame_img: np.ndarray) -> Dict:
        """FIXED: Frame analysis with immediate reset when behavior corrects"""
        current_time = datetime.now()
        violations = []
        
        # Analyze frame
        analysis = self.face_analyzer.detect_faces_and_analyze(frame_img)
        
        # FIXED: Check violations and immediately reset when corrected
        
        # 1. No face violation
        if analysis['face_count'] == 0:
            violations.extend(self._handle_no_face_improved(session, current_time))
        else:
            # Face detected - IMMEDIATELY reset no face timer and cooldown
            self._immediate_reset(session.session_id, 'no_face')
        
        # 2. Multiple faces violation  
        if analysis['face_count'] > 1:
            violations.extend(self._handle_multiple_faces_improved(session, current_time, analysis['face_count']))
        else:
            # Single or no face - IMMEDIATELY reset multiple faces timer and cooldown
            self._immediate_reset(session.session_id, 'multiple_faces')
        
        # 3. Looking away violation (only if exactly one face)
        if analysis['face_count'] == 1:
            if analysis['gaze_direction'] in ['LEFT', 'RIGHT']:
                violations.extend(self._handle_looking_away_improved(session, current_time, analysis['gaze_direction']))
            else:
                # Looking at center - IMMEDIATELY reset looking away timer and cooldown
                self._immediate_reset(session.session_id, 'looking_away')
            
            # 4. BALANCED Identity verification - detects different people properly
            if (self.face_analyzer.reference_encoding is not None and 
                not analysis['identity_match']):  # REMOVED the high confidence check
                violations.extend(self._handle_identity_change(session, current_time, analysis['identity_confidence']))
            else:
                # Identity OK - IMMEDIATELY reset identity timer and cooldown
                self._immediate_reset(session.session_id, 'identity_change')
        
        # Check if session should be terminated
        if session.current_violations >= session.max_violations:
            session.session_terminated = True
            violations.append({
                "type": "session_terminated",
                "message": "SESSION TERMINATED: Too many violations detected!",
                "severity": "high",
                "terminate": True
            })
        
        return {
            "status": "success",
            "violations": violations,
            "session_active": session.is_active and not session.session_terminated,
            "violation_count": session.current_violations,
            "max_violations": session.max_violations,
            "face_count": analysis['face_count'],
            "gaze_direction": analysis['gaze_direction'],
            "head_pose": analysis['head_pose']
        }
    
    def _immediate_reset(self, session_id: str, timer_key: str):
        """FIXED: Immediately reset both timer and cooldown when behavior corrects"""
        # Reset violation timer immediately
        if session_id in self.violation_timers and timer_key in self.violation_timers[session_id]:
            del self.violation_timers[session_id][timer_key]
        
        # Reset cooldown timer immediately
        if session_id in self.cooldown_timers and timer_key in self.cooldown_timers[session_id]:
            del self.cooldown_timers[session_id][timer_key]
    
    def _is_in_cooldown(self, session_id: str, timer_key: str, current_time: datetime) -> bool:
        """ORIGINAL WORKING - Check if a violation type is in cooldown period"""
        if timer_key in self.cooldown_timers.get(session_id, {}):
            elapsed = (current_time - self.cooldown_timers[session_id][timer_key]).total_seconds()
            return elapsed < self.cooldown_period
        return False
    
    def _handle_no_face_improved(self, session: ProctoringSession, current_time: datetime) -> List[Dict]:
        """ORIGINAL WORKING - Handle no face detected violation"""
        timer_key = 'no_face'
        
        # Check if in cooldown period
        if self._is_in_cooldown(session.session_id, timer_key, current_time):
            return []  # Don't show warning during cooldown
        
        if timer_key not in self.violation_timers[session.session_id]:
            self.violation_timers[session.session_id][timer_key] = current_time
            return [{"type": "warning", "message": "NO FACE DETECTED!", "severity": "low"}]
        
        elapsed = (current_time - self.violation_timers[session.session_id][timer_key]).total_seconds()
        if elapsed >= self.no_face_threshold:
            # Add violation
            violation = ProctoringViolation(
                type="no_face",
                message="No face detected for extended period",
                timestamp=current_time,
                severity="medium"
            )
            session.violations.append(violation)
            session.current_violations += 1
            
            # Reset timer and start cooldown
            self._reset_violation_timer(session.session_id, timer_key)
            self.cooldown_timers[session.session_id][timer_key] = current_time
            
            return [{
                "type": "violation",
                "message": "VIOLATION: No face detected for too long",
                "severity": "medium"
            }]
        
        remaining = self.no_face_threshold - elapsed
        return [{
            "type": "warning",
            "message": "NO FACE DETECTED!",
            "timer": f"Warning in: {remaining:.1f}s",
            "severity": "low"
        }]
    
    def _handle_multiple_faces_improved(self, session: ProctoringSession, current_time: datetime, face_count: int) -> List[Dict]:
        """ORIGINAL WORKING - Handle multiple faces detected violation"""
        timer_key = 'multiple_faces'
        
        # Check if in cooldown period
        if self._is_in_cooldown(session.session_id, timer_key, current_time):
            return []  # Don't show warning during cooldown
        
        if timer_key not in self.violation_timers[session.session_id]:
            self.violation_timers[session.session_id][timer_key] = current_time
            return [{
                "type": "warning",
                "message": f"{face_count} PEOPLE DETECTED! ONLY 1 ALLOWED!",
                "severity": "medium"
            }]
        
        elapsed = (current_time - self.violation_timers[session.session_id][timer_key]).total_seconds()
        if elapsed >= self.multiple_face_threshold:
            # Add violation
            violation = ProctoringViolation(
                type="multiple_faces",
                message=f"Multiple people detected: {face_count} faces",
                timestamp=current_time,
                severity="high"
            )
            session.violations.append(violation)
            session.current_violations += 1
            
            # Reset timer and start cooldown
            self._reset_violation_timer(session.session_id, timer_key)
            self.cooldown_timers[session.session_id][timer_key] = current_time
            
            return [{
                "type": "violation",
                "message": f"VIOLATION: {face_count} people detected",
                "severity": "high"
            }]
        
        remaining = self.multiple_face_threshold - elapsed
        return [{
            "type": "warning",
            "message": f"{face_count} PEOPLE DETECTED! ONLY 1 ALLOWED!",
            "timer": f"Warning in: {remaining:.1f}s",
            "severity": "medium"
        }]
    
    def _handle_looking_away_improved(self, session: ProctoringSession, current_time: datetime, direction: str) -> List[Dict]:
        """ORIGINAL WORKING - Handle looking away violation"""
        timer_key = 'looking_away'
        
        # Check if in cooldown period
        if self._is_in_cooldown(session.session_id, timer_key, current_time):
            return []  # Don't show warning during cooldown
        
        if timer_key not in self.violation_timers[session.session_id]:
            self.violation_timers[session.session_id][timer_key] = current_time
            return [{
                "type": "warning",
                "message": f"LOOKING AWAY ({direction})!",
                "severity": "low"
            }]
        
        elapsed = (current_time - self.violation_timers[session.session_id][timer_key]).total_seconds()
        if elapsed >= self.looking_away_threshold:
            # Add violation
            violation = ProctoringViolation(
                type="looking_away",
                message=f"Student looking {direction.lower()}",
                timestamp=current_time,
                severity="medium"
            )
            session.violations.append(violation)
            session.current_violations += 1
            
            # Reset timer and start cooldown
            self._reset_violation_timer(session.session_id, timer_key)
            self.cooldown_timers[session.session_id][timer_key] = current_time
            
            return [{
                "type": "violation",
                "message": f"VIOLATION: Looking {direction.lower()} for too long",
                "severity": "medium"
            }]
        
        remaining = self.looking_away_threshold - elapsed
        return [{
            "type": "warning",
            "message": f"LOOKING AWAY ({direction})!",
            "timer": f"Warning in: {remaining:.1f}s",
            "severity": "low"
        }]
    
    def _handle_identity_change(self, session: ProctoringSession, current_time: datetime, confidence: float) -> List[Dict]:
        """BALANCED: Handle identity change - detects different people but not too sensitive"""
        timer_key = 'identity_change'
        identity_threshold = 4.0  # BALANCED: 4 seconds (responsive but not too fast)
        
        # Check if in cooldown period
        if self._is_in_cooldown(session.session_id, timer_key, current_time):
            return []  # Don't show warning during cooldown
        
        if timer_key not in self.violation_timers[session.session_id]:
            self.violation_timers[session.session_id][timer_key] = current_time
            return [{
                "type": "warning", 
                "message": "IDENTITY VERIFICATION FAILED!",
                "severity": "high"
            }]
        
        elapsed = (current_time - self.violation_timers[session.session_id][timer_key]).total_seconds()
        if elapsed >= identity_threshold:
            # Add violation
            violation = ProctoringViolation(
                type="identity_change",
                message="Different person detected during interview",
                timestamp=current_time,
                severity="high"
            )
            session.violations.append(violation)
            session.current_violations += 1
            
            # Reset timer and start cooldown
            self._reset_violation_timer(session.session_id, timer_key)
            self.cooldown_timers[session.session_id][timer_key] = current_time
            
            return [{
                "type": "violation",
                "message": "VIOLATION: Different person detected!",
                "severity": "high"
            }]
        
        remaining = identity_threshold - elapsed
        return [{
            "type": "warning",
            "message": "IDENTITY VERIFICATION FAILED!",
            "timer": f"Warning in: {remaining:.1f}s",
            "severity": "high"
        }]
    
    def _reset_violation_timer(self, session_id: str, timer_key: str):
        """ORIGINAL WORKING - Reset a specific violation timer."""
        if session_id in self.violation_timers and timer_key in self.violation_timers[session_id]:
            del self.violation_timers[session_id][timer_key]
    
    async def get_session_report(self, session_id: str) -> Dict:
        """ORIGINAL WORKING - Get proctoring report for a session."""
        if session_id not in self.sessions:
            return {"status": "error", "message": "Session not found"}
        
        session = self.sessions[session_id]
        violations_data = [asdict(v) for v in session.violations]
        
        # Convert datetime objects to strings for JSON serialization
        for violation in violations_data:
            if 'timestamp' in violation and violation['timestamp']:
                violation['timestamp'] = violation['timestamp'].isoformat()
        
        return {
            "status": "success",
            "session_id": session_id,
            "violations": violations_data,
            "total_violations": session.current_violations,
            "session_terminated": session.session_terminated
        }
    
    async def end_session(self, session_id: str) -> Dict:
        """ORIGINAL WORKING - End a proctoring session."""
        if session_id in self.sessions:
            self.sessions[session_id].is_active = False
            logger.info(f"Ended proctoring session: {session_id}")
            return {"status": "success", "message": "Session ended"}
        return {"status": "error", "message": "Session not found"}
    
    def cleanup_session(self, session_id: str):
        """ORIGINAL WORKING - Clean up session data."""
        if session_id in self.sessions:
            del self.sessions[session_id]
        if session_id in self.violation_timers:
            del self.violation_timers[session_id]
        if session_id in self.cooldown_timers:
            del self.cooldown_timers[session_id]