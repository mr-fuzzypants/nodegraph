import asyncio
import sys
import os

"""
MediaPipe Gesture Recognition Example
-------------------------------------
This script demonstrates a real-time computer vision pipeline using the NodeGraph engine.
It constructs a graph to process webcam video feeds using Google MediaPipe's Gesture Recognition.

Graph Structure:
    [VideoSource] -> [MediaPipeGestureRecognizer] -> [OpenCVViewer]

Operational Mode:
    - This example runs in "Video Mode" (Continuous Loop).
    - It uses a "Pull-Based" architecture where the 'Viewer' node requests data.
    - The 'VideoSource' node is flagged as 'Always Dirty', meaning it fetches a new
      frame from the webcam every time it is queried.
    - The main loop triggers the viewer repeatedly, preventing the script from exiting.

Requirements:
    - A connected webcam (device_index=0).
    - 'mediapipe', 'opencv-python' packages installed.
    - 'gesture_recognizer.task' model file in the same directory (or model_path specified).
"""

# Add local path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.NodeNetwork import NodeNetwork
from core.Node import Node
from MediaPipeNodes import *

async def main():
    print("--- Starting MediaPipe Gesture Recognition Demo ---")
    
    # 1. Create Network
    net = NodeNetwork("GestureRecognitionGraph")
    
    # Check for model file (optional warning)
    if not os.path.exists("gesture_recognizer.task"):
        print("Warning: 'gesture_recognizer.task' not found in current directory. Node might fail to initialize.")
        # Try to use default name logic in Node if simple filename allows it, 
        # but the node defaults to "gesture_recognizer.task" anyway.
    
    # 2. Create Nodes
    try:
        source = net.create_node("webcam", "VideoSource", device_index=0)
        recognizer = net.create_node("gesture_proc", "MediaPipeGestureRecognizer", model_path="gesture_recognizer.task")
        viewer = net.create_node("display", "OpenCVViewer")
    except ValueError as e:
        print(f"Error creating nodes: {e}")
        return

    # 3. Create Connections (Data Flow)
    # Source -> Recognizer
    source.get_output_data_port("frame").connectTo(recognizer.get_input_data_port("image"))
    
    # Recognizer -> Viewer
    recognizer.get_output_data_port("annotated_image").connectTo(viewer.get_input_data_port("image"))

    # 4. Run Loop
    print("Graph constructed. Running loop... (Press Ctrl+C to stop)")
    print("Note: This requires a locally connected webcam.")
    
    try:
        while True:
            # Trigger the viewer manually each frame (Game Loop Pattern)
            # The Viewer will PULL data from Recognizer -> Source asynchronously
            
            # Mark source as dirty to propagate update
            source.get_output_data_port("frame").markDirty()
            
            # Start computation from the viewer
            await net.compute(start_nodes=[viewer])
            
            # Yield control briefly
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
