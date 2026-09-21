from .config import load_settings
from .server import run_server


def main() -> None:
    settings = load_settings()
    run_server(settings)


if __name__ == "__main__":
    main()
