# Make "src" importable in CI and local runs
import os, sys
sys.path.insert(0, os.path.abspath(os.getcwd()))
