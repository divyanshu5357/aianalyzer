"""
Comparison test verifying old vs. new semantic contract metric calculations on the real 2026 Mohali dataset.
"""

import os
from sqlalchemy import create_engine, text
from app.semantic.metric_registry import METRIC_REGISTRY, calculate_ratio


def test_2026_mohali_semantic_metric_benchmark():
    db_url = os.environ.get("DATABASE_URL", "postgresql://ai_admin:ai_password@127.0.0.1:5433/ai_agent")
    engine = create_engine(db_url)
    ds_id = "50b48957-3f9c-4c9a-b8f8-1920b20b5bfe"

    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
            SELECT 
                SUM(cy_leads) as leads,
                SUM(cy_cucet) as cucet,
                SUM(cy_admission) as net_admission,
                COUNT(*) FILTER (WHERE lead_type = 'Refunded') as refunded_count,
                COUNT(*) FILTER (WHERE lead_type IN ('Enrolled', 'Refunded')) as gross_admission_count
            FROM analytics.uploaded_metrics
            WHERE dataset_id = :ds
        """
            ),
            {"ds": ds_id},
        ).mappings().first()

        leads = int(row["leads"])
        cucet = int(row["cucet"])
        net_admission = int(row["net_admission"])
        refunded = int(row["refunded_count"])
        gross_admission = int(row["gross_admission_count"])

        # Expected audited values from real 2026 Mohali dataset
        assert leads == 974328, f"Expected 974328 leads, got {leads}"
        assert cucet == 52107, f"Expected 52107 CUCET, got {cucet}"
        assert net_admission == 22546, f"Expected 22546 net admissions, got {net_admission}"
        assert refunded == 8302, f"Expected 8302 refunded, got {refunded}"
        assert gross_admission == 30848, f"Expected 30848 gross admissions, got {gross_admission}"

        # Formula Validation
        lead_cucet_rate = round(calculate_ratio(cucet, leads), 2)
        lead_admission_rate = round(calculate_ratio(net_admission, leads), 2)
        cucet_admission_rate = round(calculate_ratio(net_admission, cucet), 2)

        assert lead_cucet_rate == 5.35, f"Expected 5.35%, got {lead_cucet_rate}%"
        assert lead_admission_rate == 2.31, f"Expected 2.31%, got {lead_admission_rate}%"
        assert cucet_admission_rate == 43.27, f"Expected 43.27%, got {cucet_admission_rate}%"
