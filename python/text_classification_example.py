import asyncio
import sys
import os
import urllib.request
import ssl
import time

"""
Text Classification Graph Example
---------------------------------
This script demonstrates a Text Classification pipeline using the NodeGraph engine.
It uses Google MediaPipe's BERT classifier to classify the sentiment of text strings.

Structure:
    [TextSource] -> [MediaPipeTextClassifier] -> [ConsolePrinter]

Data Flow:
    1. TextSource iterates through a predefined list of sentences.
    2. TextClassifier analyzes the sentiment (positive/negative).
    3. ConsolePrinter prints the text and the classification result.
"""

# Add local path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.NodeNetwork import NodeNetwork
from core.Node import Node, ExecutionResult, ExecCommand, ValueType
from MediaPipeNodes import *

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/text_classifier/bert_classifier/float32/1/bert_classifier.tflite"
MODEL_FILENAME = "bert_classifier.tflite"

def download_model_if_needed():
    if not os.path.exists(MODEL_FILENAME):
        print(f"Downloading model file '{MODEL_FILENAME}' from {MODEL_URL}...")
        try:
            ssl_context = ssl._create_unverified_context()
            with urllib.request.urlopen(MODEL_URL, context=ssl_context) as response, open(MODEL_FILENAME, 'wb') as out_file:
                out_file.write(response.read())
            print("Download complete.")
        except Exception as e:
            print(f"Error downloading model: {e}")
            sys.exit(1)
    else:
        print(f"Model file '{MODEL_FILENAME}' found.")

# --- Custom Nodes for this Example using the 'register' decorator? 
# Or just defining classes and registering manually if internal registry allows, 
# but @Node.register is easiest.

@Node.register("TextSource")
class TextSourceNode(Node):
    def __init__(self, id: str, type: str, **kwargs):
        super().__init__(id, type, **kwargs)
        self.dout_text = self.add_data_output("text", ValueType.ANY)
        self.texts = [
            "I absolutely love this movie, it's fantastic!",
            "This is the worst experience I have ever had.",
            "The weather is okay, not great but not bad.",
            "I'm so happy with the service provided.",
            "Terrible, I will never return.",
            "Mediocre at best.",
            "An absolute masterpiece of engineering.",
            "Disgusting food and rude staff."
        ]
        self.index = 0



    async def compute(self) -> ExecutionResult:
        super().precompute()
        
        text = self.texts[self.index]
        # Cycle
        self.index = (self.index + 1) % len(self.texts)

        print("IN COMPUTE", self.index)
        
        self.dout_text.setValue(text)
        
        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE)

@Node.register("ResultPrinter")
class ResultPrinterNode(Node):
    def __init__(self, id: str, type: str, **kwargs):
        super().__init__(id, type, **kwargs)
        self.din_text = self.add_data_input("text", ValueType.ANY)
        self.din_categories = self.add_data_input("categories", ValueType.ARRAY)

    async def compute(self) -> ExecutionResult:
        super().precompute()

        
        
        # We explicitly fetch the values from the inputs
        # This triggers the recursive compute of upstream nodes if they are dirty
        # AND it sets the local port value and marks it as clean.
        text = await self.din_text.getValue()
        categories = await self.din_categories.getValue()
        
        print("-" * 60)
        print(f"Input Text: \"{text}\"")
        print("Classification:")
        for category, score in categories:
            print(f"  - {category}: {score:.4f}")
        print("-" * 60)
             
        # Debug: Check cleanliness before postcompute assertion
        # print(f"DEBUG: Text input clean? {not self.din_text.isDirty()}")
        # print(f"DEBUG: Categories input clean? {not self.din_categories.isDirty()}")

        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE)


async def main():
    print("--- Starting Text Classification Graph Demo ---")
    
    download_model_if_needed()
    
    net = NodeNetwork("TextClassifierGraph")
    
    try:
        source = net.create_node("source", "TextSource")
        classifier = net.create_node("classifier", "MediaPipeTextClassifier", model_path=MODEL_FILENAME)
        printer = net.create_node("printer", "ResultPrinter")
    except ValueError as e:
        print(f"Error creating nodes: {e}")
        return

    # Connections
    # Source -> Classifier
    source.get_output_data_port("text").connectTo(classifier.get_input_data_port("text"))
    
    # Source -> Printer (to show original text)
    source.get_output_data_port("text").connectTo(printer.get_input_data_port("text"))
    
    # Classifier -> Printer
    classifier.get_output_data_port("categories").connectTo(printer.get_input_data_port("categories"))

    print("Graph constructed. Processing texts... (Press Ctrl+C to stop)")
    
    try:
        while True:
            # Mark source output dirty to trigger downstream updates
            source.get_output_data_port("text").markDirty()
            # Mark the node itself dirty so it re-computes when pulled
            source.markDirty()
            
            await net.compute(start_nodes=[printer])
            
            # Wait a bit between classifications
            await asyncio.sleep(1.0) 
            
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
