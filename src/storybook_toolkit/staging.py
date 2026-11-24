"""Former home of legacy/staging.py; this name is the same module object, so imports and test patches still apply."""

import sys

from .legacy import staging as _module

sys.modules[__name__] = _module
