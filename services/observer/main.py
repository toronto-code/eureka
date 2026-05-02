"""Entry point for ``poetry run python main.py``.

Mirrors the ``mycelium-observer`` console script.
"""

from mycelium_observer.main import run

if __name__ == "__main__":
    run()
