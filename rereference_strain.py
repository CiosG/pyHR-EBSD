"""Re-reference stored relative strain maps without rerunning correlation.

Example: python rereference_strain.py results_old 10090 results_ref_10090
"""
import argparse
from pyhrebsd.rereference import rereference_strain
parser=argparse.ArgumentParser()
parser.add_argument("input_dir"); parser.add_argument("new_reference_index",type=int); parser.add_argument("output_dir")
a=parser.parse_args(); print(rereference_strain(a.input_dir,a.new_reference_index,a.output_dir))
