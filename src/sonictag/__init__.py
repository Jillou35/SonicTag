from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sonictag")
except PackageNotFoundError:
    # Si le package n'est pas installé (ex: test en local)
    __version__ = "unknown"
