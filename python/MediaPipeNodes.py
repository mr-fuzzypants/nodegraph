import asyncio
import sys
import os

# Imports assuming 'nodegraph/python' is in PYTHONPATH
from core.Node import Node, ExecCommand, ExecutionResult, ValueType

try:
    import cv2
    import mediapipe as mp
    import numpy as np
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False
    print("Warning: OpenCV or MediaPipe not installed. MediaPipeNodes will not function.")

@Node.register("VideoSource")
class VideoSourceNode(Node):
    def __init__(self, id: str, type: str, device_index: int = 0, **kwargs):
        super().__init__(id, type, **kwargs)
        self.device_index = device_index
        self.cap = None
        
        # Outputs
        self.dout_frame = self.add_data_output("frame", ValueType.ANY) # numpy array
        
        if HAS_MEDIAPIPE:
            # Initialize lazily or now
            pass

    def _ensure_cap(self):
        if HAS_MEDIAPIPE and (self.cap is None or not self.cap.isOpened()):
             self.cap = cv2.VideoCapture(self.device_index)

    def __del__(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()

    def isDirty(self) -> bool:
        # Always dirty -> Pull model always fetches new frame
        return True

    async def compute(self) -> ExecutionResult:
        super().precompute()
        
        if not HAS_MEDIAPIPE:
            return ExecutionResult(ExecCommand.CONTINUE)

        self._ensure_cap()
        
        if not self.cap.isOpened():
             print(f"[{self.id}] VideoCapture failed to open device {self.device_index}.")
             self.dout_frame.setValue(None)
             return ExecutionResult(ExecCommand.CONTINUE)

        loop = asyncio.get_running_loop()
        ret, frame = await loop.run_in_executor(None, self.cap.read)
        
        if ret:
            self.dout_frame.setValue(frame)
        else:
            # Loop video? Or just fail
            # self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.dout_frame.setValue(None)

        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE)

@Node.register("MediaPipeHands")
class MediaPipeHandsNode(Node):
    def __init__(self, id: str, type: str, max_num_hands: int = 2, **kwargs):
        super().__init__(id, type, **kwargs)
        
        self.din_image = self.add_data_input("image", ValueType.ANY)
        self.dout_landmarks = self.add_data_output("landmarks", ValueType.ARRAY)
        self.dout_annotated_image = self.add_data_output("annotated_image", ValueType.ANY)
        
        self.hands = None
        self.mp_drawing = None
        
        if HAS_MEDIAPIPE:
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=max_num_hands,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            self.mp_drawing = mp.solutions.drawing_utils

    async def compute(self) -> ExecutionResult:
        super().precompute()
        
        image = await self.din_image.getValue()
        if image is None or not HAS_MEDIAPIPE:
             self.dout_landmarks.setValue([])
             self.dout_annotated_image.setValue(image)
             return ExecutionResult(ExecCommand.CONTINUE)

        # Convert to RGB for MediaPipe
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, self.hands.process, image_rgb)
        
        landmarks_data = []
        annotated_image = image.copy()
        
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                landmarks_data.append(hand_landmarks)
                self.mp_drawing.draw_landmarks(
                    annotated_image, 
                    hand_landmarks, 
                    self.mp_hands.HAND_CONNECTIONS
                )
        
        self.dout_landmarks.setValue(landmarks_data)
        self.dout_annotated_image.setValue(annotated_image)
        
        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE)

@Node.register("MediaPipeImageClassifier")
class MediaPipeImageClassifierNode(Node):
    def __init__(self, id: str, type: str, model_path: str = "efficientnet_lite0.tflite", **kwargs):
        super().__init__(id, type, **kwargs)
        
        self.din_image = self.add_data_input("image", ValueType.ANY)
        self.dout_categories = self.add_data_output("categories", ValueType.ARRAY)
        self.dout_annotated_image = self.add_data_output("annotated_image", ValueType.ANY)
        
        self.model_path = model_path
        self.classifier = None
        
        if HAS_MEDIAPIPE and os.path.exists(self.model_path):
            try:
                BaseOptions = mp.tasks.BaseOptions
                ImageClassifier = mp.tasks.vision.ImageClassifier
                ImageClassifierOptions = mp.tasks.vision.ImageClassifierOptions
                VisionRunningMode = mp.tasks.vision.RunningMode

                # Create a classifier instance
                options = ImageClassifierOptions(
                    base_options=BaseOptions(model_asset_path=self.model_path),
                    max_results=3,
                    running_mode=VisionRunningMode.IMAGE) # Using IMAGE mode for simplicity in this loop
                self.classifier = ImageClassifier.create_from_options(options)
            except Exception as e:
                print(f"Failed to initialize ImageClassifier: {e}")

    async def compute(self) -> ExecutionResult:
        super().precompute()
        
        image = await self.din_image.getValue()
        if image is None or not HAS_MEDIAPIPE or self.classifier is None:
             self.dout_categories.setValue([])
             self.dout_annotated_image.setValue(image)
             return ExecutionResult(ExecCommand.CONTINUE)

        # Convert to RGB for MediaPipe
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # Create MediaPipe Image
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
        
        loop = asyncio.get_running_loop()
        # Run classification in executor
        classification_result = await loop.run_in_executor(None, self.classifier.classify, mp_image)
        
        # Process results
        categories = []
        annotated_image = image.copy()
        
        if classification_result.classifications:
            top_classification = classification_result.classifications[0]
            categories = [(c.category_name, c.score) for c in top_classification.categories]

            # Draw top classification
            if categories:
                top_cat = categories[0]
                text = f"{top_cat[0]}: {top_cat[1]:.2f}"
                cv2.putText(annotated_image, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                            1, (0, 255, 0), 2, cv2.LINE_AA)

        self.dout_categories.setValue(categories)
        self.dout_annotated_image.setValue(annotated_image)
        
        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE)

@Node.register("MediaPipeObjectDetector")
class MediaPipeObjectDetectorNode(Node):
    def __init__(self, id: str, type: str, model_path: str = "efficientdet_lite0.tflite", **kwargs):
        super().__init__(id, type, **kwargs)
        
        self.din_image = self.add_data_input("image", ValueType.ANY)
        self.dout_detections = self.add_data_output("detections", ValueType.ARRAY)
        self.dout_annotated_image = self.add_data_output("annotated_image", ValueType.ANY)
        
        self.model_path = model_path
        self.detector = None
        
        if HAS_MEDIAPIPE and os.path.exists(self.model_path):
            try:
                BaseOptions = mp.tasks.BaseOptions
                ObjectDetector = mp.tasks.vision.ObjectDetector
                ObjectDetectorOptions = mp.tasks.vision.ObjectDetectorOptions
                VisionRunningMode = mp.tasks.vision.RunningMode

                options = ObjectDetectorOptions(
                    base_options=BaseOptions(model_asset_path=self.model_path),
                    max_results=5,
                    running_mode=VisionRunningMode.IMAGE
                )
                self.detector = ObjectDetector.create_from_options(options)
            except Exception as e:
                print(f"Failed to initialize ObjectDetector: {e}")

    async def compute(self) -> ExecutionResult:
        super().precompute()
        
        image = await self.din_image.getValue()
        if image is None or not HAS_MEDIAPIPE or self.detector is None:
             self.dout_detections.setValue([])
             self.dout_annotated_image.setValue(image)
             return ExecutionResult(ExecCommand.CONTINUE)

        # Convert to RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
        
        loop = asyncio.get_running_loop()
        detection_result = await loop.run_in_executor(None, self.detector.detect, mp_image)
        
        detections_data = []
        annotated_image = image.copy()
        
        for detection in detection_result.detections:
            # bbox is relative to image size in some versions, or absolute in tasks API?
            # Tasks API returns bounding_box as RECT (origin_x, origin_y, width, height)
            bbox = detection.bounding_box
            start_point = (bbox.origin_x, bbox.origin_y)
            end_point = (bbox.origin_x + bbox.width, bbox.origin_y + bbox.height)
            
            category = detection.categories[0]
            label = f"{category.category_name} ({category.score:.2f})"
            
            # Store data
            detections_data.append({
                "bbox": [bbox.origin_x, bbox.origin_y, bbox.width, bbox.height],
                "label": category.category_name,
                "score": category.score
            })

            # Draw
            cv2.rectangle(annotated_image, start_point, end_point, (255, 0, 0), 3)
            cv2.putText(annotated_image, label, (bbox.origin_x, bbox.origin_y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
        
        self.dout_detections.setValue(detections_data)
        self.dout_annotated_image.setValue(annotated_image)
        
        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE)

@Node.register("MediaPipeTextClassifier")
class MediaPipeTextClassifierNode(Node):
    def __init__(self, id: str, type: str, model_path: str = "bert_classifier.tflite", **kwargs):
        super().__init__(id, type, **kwargs)
        
        self.din_text = self.add_data_input("text", ValueType.ANY) # Expected string
        self.dout_categories = self.add_data_output("categories", ValueType.ARRAY)
        
        self.model_path = model_path
        self.classifier = None
        
        if HAS_MEDIAPIPE and os.path.exists(self.model_path):
            try:
                BaseOptions = mp.tasks.BaseOptions
                TextClassifier = mp.tasks.text.TextClassifier
                TextClassifierOptions = mp.tasks.text.TextClassifierOptions

                options = TextClassifierOptions(
                    base_options=BaseOptions(model_asset_path=self.model_path)
                )
                self.classifier = TextClassifier.create_from_options(options)
            except Exception as e:
                print(f"Failed to initialize TextClassifier: {e}")

    async def compute(self) -> ExecutionResult:
        super().precompute()
        
        text = await self.din_text.getValue()
        if text is None or not HAS_MEDIAPIPE or self.classifier is None:
             self.dout_categories.setValue([])
             return ExecutionResult(ExecCommand.CONTINUE)
        
        loop = asyncio.get_running_loop()
        # MediaPipe Text tasks are typically CPU bound and fast, but run in executor for safety
        classification_result = await loop.run_in_executor(None, self.classifier.classify, text)
        
        categories = []
        if classification_result.classifications:
            # Usually one head for text classification
            top_classification = classification_result.classifications[0]
            categories = [(c.category_name, c.score) for c in top_classification.categories] # sort?
            # Sort by score descending
            categories.sort(key=lambda x: x[1], reverse=True)

        self.dout_categories.setValue(categories)
        
        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE)

@Node.register("MediaPipeGestureRecognizer")
class MediaPipeGestureRecognizerNode(Node):
    def __init__(self, id: str, type: str, model_path: str = "gesture_recognizer.task", **kwargs):
        super().__init__(id, type, **kwargs)
        
        self.din_image = self.add_data_input("image", ValueType.ANY)
        self.dout_gestures = self.add_data_output("gestures", ValueType.ARRAY)
        self.dout_annotated_image = self.add_data_output("annotated_image", ValueType.ANY)
        
        self.model_path = model_path
        self.recognizer = None
        
        if HAS_MEDIAPIPE and os.path.exists(self.model_path):
            try:
                BaseOptions = mp.tasks.BaseOptions
                GestureRecognizer = mp.tasks.vision.GestureRecognizer
                GestureRecognizerOptions = mp.tasks.vision.GestureRecognizerOptions
                VisionRunningMode = mp.tasks.vision.RunningMode

                options = GestureRecognizerOptions(
                    base_options=BaseOptions(model_asset_path=self.model_path),
                    running_mode=VisionRunningMode.IMAGE
                )
                self.recognizer = GestureRecognizer.create_from_options(options)
            except Exception as e:
                print(f"Failed to initialize GestureRecognizer: {e}")

    async def compute(self) -> ExecutionResult:
        super().precompute()
        
        image = await self.din_image.getValue()
        if image is None or not HAS_MEDIAPIPE or self.recognizer is None:
             self.dout_gestures.setValue([])
             self.dout_annotated_image.setValue(image)
             return ExecutionResult(ExecCommand.CONTINUE)

        # Convert to RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
        
        loop = asyncio.get_running_loop()
        recognition_result = await loop.run_in_executor(None, self.recognizer.recognize, mp_image)
        
        gestures_data = []
        annotated_image = image.copy()
        
        if recognition_result.gestures:
            for i, gestures in enumerate(recognition_result.gestures):
                if gestures:
                    top_gesture = gestures[0]
                    gestures_data.append({
                        "name": top_gesture.category_name,
                        "score": top_gesture.score,
                        "hand_index": i
                    })
                    
                    if i < len(recognition_result.hand_landmarks):
                        hand_landmarks = recognition_result.hand_landmarks[i]
                        # wrist is index 0
                        wrist = hand_landmarks[0]
                        h, w, c = annotated_image.shape
                        cx, cy = int(wrist.x * w), int(wrist.y * h)
                        
                        label = f"{top_gesture.category_name} ({top_gesture.score:.2f})"
                        cv2.putText(annotated_image, label, (cx, cy - 20), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
                                    
                        # Draw wrist point
                        cv2.circle(annotated_image, (cx, cy), 10, (255, 0, 0), -1)

        self.dout_gestures.setValue(gestures_data)
        self.dout_annotated_image.setValue(annotated_image)
        
        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE)

@Node.register("OpenCVViewer")
class OpenCVViewerNode(Node):
    def __init__(self, id: str, type: str, **kwargs):
        super().__init__(id, type, **kwargs)
        self.window_name = f"Node Graph Viewer [{id}]"
        
        # Inputs
        self.cin_exec = self.add_control_input("exec")
        self.din_image = self.add_data_input("image", ValueType.ANY)
        
        # Outputs
        self.cout_next = self.add_control_output("next")

    async def compute(self) -> ExecutionResult:
        super().precompute()
        
        # If triggered by flow
        if self.cin_exec.isActive():
            self.cin_exec.deactivate()
        
        # Pull image
        image = await self.din_image.getValue()
        
        if HAS_MEDIAPIPE and image is not None:
            cv2.imshow(self.window_name, image)
            # Short wait key to update window
            cv2.waitKey(1)
            
        next_nodes = self._get_nodes_from_port(self.cout_next)
        
        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE, next_nodes)
