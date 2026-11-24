"""Former home of legacy/continuity.py; this name is the same module object, so imports and test patches still apply."""

import sys

from .legacy import continuity as _module

sys.modules[__name__] = _module
