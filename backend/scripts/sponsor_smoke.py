#!/usr/bin/env python3
"""Card-path entry point for the ENG-042 sponsor smoke.

The ENG-042 task card names ``backend/scripts/sponsor_smoke.py`` as an
expected artifact. The implementation lives in the module layout the repo
actually uses (``app/modules/integrations/smoke.py``, alongside every other
sponsor smoke CLI); this thin wrapper keeps the card's path working:

    python scripts/sponsor_smoke.py --chat --evidence-out docs/evidence/sponsor-health.md
"""

import sys
from pathlib import Path

# Make ``app`` importable when invoked directly from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.integrations.smoke import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
