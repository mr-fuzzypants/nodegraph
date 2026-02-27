import sys
import os

try:
    from python.core.DurableExecutor import DurableExecutorMixin
    print("Import success")
    mixin = DurableExecutorMixin()
    print("Instance success")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
