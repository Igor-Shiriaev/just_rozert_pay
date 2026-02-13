import sys

sys.path.append("../shared-apps")
from rozert_pay_shared import (  # type: ignore[import-untyped]    # noqa: E402
    run_diff_cover,
)

if __name__ == "__main__":
    run_diff_cover.run_commands_and_diff_cover(
        "Rozert Pay",
        [
            "make pytest-cov",
            "make mypy",
            "make lint",
            "make pylint",
        ],
    )
