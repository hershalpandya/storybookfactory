# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Former home of legacy/visual_review.py; this name is the same module object, so imports and test patches still apply."""

import sys

from .legacy import visual_review as _module

sys.modules[__name__] = _module
