"""Tools for creating reviewed illustrated storybooks."""

from importlib import metadata

try:
    # pyproject.toml is the single source of the version; installed metadata carries it.
    __version__ = metadata.version("storybook-toolkit")
except metadata.PackageNotFoundError:  # running from an uninstalled source tree
    __version__ = "0+unknown"
