"""Former home of legacy/scenes.py; this name is the same module object, so imports and test patches still apply."""

import sys

from .legacy import scenes as _module

sys.modules[__name__] = _module
