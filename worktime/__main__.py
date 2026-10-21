"""Entry point: python -m worktime"""
from worktime import __version__


def main() -> None:
    print(f"work-time-sheet v{__version__}")


if __name__ == "__main__":
    main()
