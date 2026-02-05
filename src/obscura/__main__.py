"""Allow running as `python -m obscura`."""

import os
import sys

from obscura.runtime import configure_ocr_runtime


def main():
    configure_ocr_runtime()

    if len(sys.argv) > 1 or os.environ.get("OBSCURA_CLI_ONLY") == "1":
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
