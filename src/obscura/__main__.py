"""Allow running as `python -m obscura`."""

import sys


def main():
    if len(sys.argv) > 1:
        from obscura.cli import main as cli_main
        cli_main()
    else:
        try:
            from obscura.app import launch
            launch()
        except ImportError:
            from obscura.cli import main as cli_main
            cli_main()


if __name__ == "__main__":
    main()
