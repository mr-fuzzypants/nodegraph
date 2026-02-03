import asyncio
import sys
import os

"""
MediaPipe Graph Example
-----------------------
This script demonstrates a real-time computer vision pipeline using the NodeGraph engine.
It constructs a graph to process webcam video feeds using Google MediaPipe's Hand Tracking.

Graph Structure:
    [VideoSource] -> [MediaPipeHands] -> [OpenCVViewer]

Operational Mode:
    - This example runs in "Video Mode" (Continuous Loop).
    - It uses a "Pull-Based" architecture where the 'Viewer' node requests data.
    - The 'VideoSource' node is flagged as 'Always Dirty', meaning it fetches a new 
      frame from the webcam every time it is queried.
    - The main loop triggers the viewer repeatedly, preventing the script from exiting.

Requirements:
    - A connected webcam (device_index=0).
    - 'mediapipe', 'opencv-python' packages installed.
"""

# Add local path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.NodeNetwork import NodeNetwork
from core.Node import Node
from MediaPipeNodes import *

async def main():
    print("--- Starting MediaPipe Graph Demo ---")
    
    # 1. Create Network
    net = NodeNetwork("HandTrackingGraph")
    
    # 2. Create Nodes
    try:
        source = net.create_node("webcam", "VideoSource", device_index=0)
        hands = net.create_node("hand_processor", "MediaPipeHands")
        viewer = net.create_node("display", "OpenCVViewer")
    except ValueError as e:
        print(f"Error creating nodes: {e}")
        return

    # 3. Create Connections (Data Flow)
    # Source -> Hands
    source.get_output_data_port("frame").connectTo(hands.get_input_data_port("image"))
    
    # Hands -> Viewer
    # We can view the raw landmarks or the annotated image
    hands.get_output_data_port("annotated_image").connectTo(viewer.get_input_data_port("image"))

    # 4. Run Loop
    print("Graph constructed. Running loop... (Press Ctrl+C to stop)")
    print("Note: This requires a locally connected webcam.")
    
    try:
        while True:
            # Trigger the viewer manually each frame (Game Loop Pattern)
            # The Viewer will PULL data from Hands -> Source asynchronously
            
            # Since VideoSource is "Always Dirty" (conceptually), but the Graph Logic
            # requires dirty flags to propagate from upstream to downstream to trigger re-computation,
            # we manually mark the source's OUTPUT port as dirty. This forces the dirty state
            # to propagate to the Hands and Viewer nodes, ensuring they pull a new frame.
            source.get_output_data_port("frame").markDirty()
            
            # We activate the exec port to simulate a flow trigger if needed, 
            # though calling compute directly on the node bypasses port checks usually 
            # unless the node logic checks 'isActive'. 
            # OpenCVViewer checks 'if self.cin_exec.isActive()', so we must activate it.
            # viewer.get_input_control_port("exec").activate()
            
            await net.compute(start_nodes=[viewer])
            
            # Yield control briefly to allow other async tasks/Event Loop maintenance
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
