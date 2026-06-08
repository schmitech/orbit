import os
import sys
import importlib


SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if SERVER_DIR in sys.path:
    sys.path.remove(SERVER_DIR)
sys.path.insert(0, SERVER_DIR)

INFERENCE_DIR = os.path.join(SERVER_DIR, 'inference')
loaded_inference = sys.modules.get('inference')
if loaded_inference and not getattr(loaded_inference, '__file__', '').startswith(INFERENCE_DIR):
    del sys.modules['inference']

importlib.import_module('inference')
