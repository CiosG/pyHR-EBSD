"""Re-reference a completed PyHREBSD homography run.

Example:
    python rereference_homography.py results_old 10090 results_ref_10090
"""
import argparse
from pyhrebsd.rereference import rereference_homography

parser=argparse.ArgumentParser()
parser.add_argument("input_dir")
parser.add_argument("new_reference_index",type=int)
parser.add_argument("output_dir")
args=parser.parse_args()
print(rereference_homography(args.input_dir,args.new_reference_index,args.output_dir))
