"""Former home of legacy/attempts.py; this name is the same module object, so imports and test patches still apply."""

import sys

from .legacy import attempts as _module

sys.modules[__name__] = _module
