"""M4 Step 6: Provenance — source tracing aligned with W3C PROV-O.

Each record carries a PROV-O structure:
- entity: source file/table/page
- activity: extraction method + run ID
- agent: processor + LLM model
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from src.schema import Record


def add_provenance(records: list[Record], run_id: str | None = None) -> list[Record]:
    """Add PROV-O aligned provenance to each record's note field.

    Args:
        records: List of records to annotate.
        run_id: Optional run identifier. Auto-generated if None.

    Returns:
        Records with provenance metadata appended to note.
    """
    if run_id is None:
        run_id = f"etl_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    for rec in records:
        prov = {
            "prov:entity": {
                "source": rec.source,
            },
            "prov:activity": {
                "extracted_by": "EconDataForge_v1.0",
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "prov:agent": {
                "processor": "EconDataForge_v1.0",
            },
        }
        prov_str = json.dumps(prov, ensure_ascii=False)
        rec.note = (rec.note + f";prov={prov_str}" if rec.note else f"prov={prov_str}")

    return records
