#!/usr/bin/env python
import sys
import os

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
    sys.path.insert(0, application_path)

from src.main import main

if __name__ == "__main__":
    main()