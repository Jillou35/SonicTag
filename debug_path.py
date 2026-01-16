
import sys
import os

sys.path.append(os.path.abspath("src"))
import sonictag.deepseal
from sonictag.deepseal import DeepSeal

print(f"DeepSeal Module File: {sonictag.deepseal.__file__}")
print(f"DeepSeal Class: {DeepSeal}")

ds = DeepSeal()
print("Calling extract...")
ds.extract(audio=[0]*44100)
print("Done.")
