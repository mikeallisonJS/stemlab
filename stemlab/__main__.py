"""`python -m stemlab`: the same command line as the `stemlab` script.

The desktop app starts the server this way, so the process it spawns is the
Python interpreter itself and can be stopped without leaving a child behind.
"""

from stemlab.cli import app

if __name__ == "__main__":
    app()
