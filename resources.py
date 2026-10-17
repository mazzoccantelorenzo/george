import os
import sys


def get_resource_path(relative_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base, relative_path)
