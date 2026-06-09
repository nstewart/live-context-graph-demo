import os
import sys

# Put the propagation-tap root on sys.path so `from src.tap import ...` resolves
# when pytest is run from anywhere.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
