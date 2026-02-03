import asyncio
import sys
import os
import urllib.request
import ssl

"""
Object Detection Graph Example
------------------------------
This script demonstrates an Object Detection pipeline using the NodeGraph engine.
It uses Google MediaPipe's efficientdet_lite0 model to detect objects in webcam video frames.

Structure:
    [VideoSource] -> [MediaPipeObjectDetector] -> [OpenCVViewer]

Data Flow:
    1. VideoSource captures a frame.
    2. ObjectDetector detects objects (Person, Cup, Phone, etc.) and draws bounding boxes.
    3. OpenCVViewer displays the annotated frame.
"""

# Add local path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.NodeNetwork import NodeNetwork
from core.Node import Node
from MediaPipeNodes import *

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float32/1/efficientdet_lite0.tflite"
MODEL_FILENAME = "efficientdet_lite0.tflite"

def download_model_if_needed():
    if not os.path.exists(MODEL_FILENAME):
        print(f"Downloading model file '{MODEL_FILENAME}' from {MODEL_URL}...")
        try:
            # Bypass SSL verification for demo purposes on macOS
            ssl_context = ssl._create_unverified_context()
            with urllib.request.urlopen(MODEL_URL, context=ssl_context) as response, open(MODEL_FILENAME, 'wb') as out_file:
                out_file.write(response.read())
            print("Download complete.")
        except Exception as e:
            print(f"Error downloading model: {e}")
            sys.exit(1)
    else:
        print(f"Model file '{MODEL_FILENAME}' found.")

async def main():
    print("--- Starting Object Detector Graph Demo ---")
    
    download_model_if_needed()
    
    net = NodeNetwork("ObjectDetectorGraph")
    
    try:
        source = net.create_node("webcam", "VideoSource", device_index=0)
        detector = net.create_node("detector", "MediaPipeObjectDetector", model_path=MODEL_FILENAME)
        viewer = net.create_node("display", "OpenCVViewer")
    except ValueError as e:
        print(f"Error creating nodes: {e}")
        return

    # Connections
    source.get_output_data_port("frame").connectTo(detector.get_input_data_port("image"))
    detector.get_output_data_port("annotated_image").connectTo(viewer.get_input_data_port("image"))

    print("Graph constructed. Running loop... (Press Ctrl+C to stop)")
    print("Note: This requires a locally connected webcam.")
    
    try:
        while True:
            # Force source to be dirty to pull new frame
            source.get_output_data_port("frame").markDirty()
            
            await net.compute(start_nodes=[viewer])
            
            # Yield to event loop
            await asyncio.sleep(0.001) 
            
    except KeyboardInterrupt:
        print("Stopping...")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error during execution: {repr(e)}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
