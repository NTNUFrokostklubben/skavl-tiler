from importlib import import_module
import sys

# Add every *_pb2 module in this folder to current namespace
for _m in ("progress_pb2",):
    sys.modules[_m] = import_module(f"{__name__}.{_m}")