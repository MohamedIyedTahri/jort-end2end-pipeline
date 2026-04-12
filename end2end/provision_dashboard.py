from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parent))
    from provision_company360_dashboard import main as provision_company360_dashboard
    from provision_exec_dashboard import main as provision_exec_dashboard
else:
    from .provision_company360_dashboard import main as provision_company360_dashboard
    from .provision_exec_dashboard import main as provision_exec_dashboard


def main() -> None:
    provision_exec_dashboard()
    provision_company360_dashboard()
    print(
        json.dumps(
            {
                "status": "ok",
                "dashboards": ["jort-executive-dashboard", "jort-company-360-dashboard"],
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()