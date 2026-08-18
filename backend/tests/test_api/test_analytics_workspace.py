"""Coverage for the paginated source/program BI comparison workspace."""
from __future__ import annotations

import unittest
from uuid import uuid4

from sqlalchemy import text

from app.analytics.workspace import query_workspace_comparison
from app.database.connection import SessionLocal
from app.database.repository import create_data_source, create_dataset, set_dataset_period


class TestAnalyticsWorkspace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        # academic_label is intentionally constrained to varchar(10), matching
        # the real historical period registry.
        suffix = uuid4().hex[:8]
        cls.period_a = f"A{suffix}"
        cls.period_b = f"B{suffix}"
        cls.source_ids: list[str] = []
        cls.dataset_ids: list[str] = []

        cls.dataset_a = cls._create_period_dataset(cls.period_a, 2090, 2091)
        cls.dataset_b = cls._create_period_dataset(cls.period_b, 2091, 2092)
        cls.unrelated_dataset_id = cls._create_unrelated_dataset()
        cls._insert_metrics(cls.dataset_a, cls._period_a_metrics())
        cls._insert_metrics(cls.dataset_b, cls._period_b_metrics())

        # A third dataset has deliberately huge values. It must never leak into
        # a comparison selected by the two period labels above.
        cls._insert_metrics(
            cls.unrelated_dataset_id,
            [
                {
                    "row_number": 1,
                    "source": "Leak source",
                    "state": "North",
                    "program_name": "Leak program",
                    "cluster": "Leak detail",
                    "campus_name": "Leak campus",
                    "owner": "Leak owner",
                    "leads": 999_999,
                    "admissions": 999_999,
                }
            ],
        )

        # Enough grouped rows to prove the endpoint pages aggregates rather
        # than handing a large result set to React.
        bulk_a = []
        bulk_b = []
        for index in range(1, 206):
            row = {
                "row_number": index + 10,
                "source": f"Bulk {index:03d}",
                "state": "Bulk state",
                "program_name": f"Bulk program {index:03d}",
                "cluster": "Bulk",
                "campus_name": "Bulk campus",
                "owner": "Bulk owner",
                "leads": 5,
                "admissions": 1,
            }
            bulk_a.append(row)
            bulk_b.append(dict(row))
        cls._insert_metrics(cls.dataset_a, bulk_a)
        cls._insert_metrics(cls.dataset_b, bulk_b)
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        for dataset_id in cls.dataset_ids:
            cls.db.execute(
                text("DELETE FROM analytics.uploaded_metrics WHERE dataset_id = :dataset_id"),
                {"dataset_id": dataset_id},
            )
            cls.db.execute(
                text("DELETE FROM system.datasets WHERE id = :dataset_id"),
                {"dataset_id": dataset_id},
            )
        for source_id in cls.source_ids:
            cls.db.execute(
                text("DELETE FROM system.data_sources WHERE id = :source_id"),
                {"source_id": source_id},
            )
        cls.db.commit()
        cls.db.close()

    @classmethod
    def _create_period_dataset(cls, label: str, start_year: int, end_year: int) -> str:
        dataset_id = str(uuid4())
        source_id = create_data_source(cls.db, f"workspace-source-{dataset_id}", "test")
        create_dataset(
            cls.db,
            dataset_id,
            source_id,
            f"Workspace dataset {label}",
            f"{label}.csv",
            "csv",
            300,
            14,
        )
        set_dataset_period(cls.db, dataset_id, start_year, end_year, label)
        cls.db.execute(
            text("UPDATE system.datasets SET is_period_active = TRUE WHERE id = :dataset_id"),
            {"dataset_id": dataset_id},
        )
        cls.dataset_ids.append(dataset_id)
        cls.source_ids.append(str(source_id))
        return dataset_id

    @classmethod
    def _create_unrelated_dataset(cls) -> str:
        dataset_id = str(uuid4())
        source_id = create_data_source(cls.db, f"workspace-unrelated-{dataset_id}", "test")
        create_dataset(
            cls.db,
            dataset_id,
            source_id,
            "Unrelated workspace dataset",
            "unrelated.csv",
            "csv",
            1,
            14,
        )
        cls.dataset_ids.append(dataset_id)
        cls.source_ids.append(str(source_id))
        return dataset_id

    @staticmethod
    def _period_a_metrics() -> list[dict]:
        return [
            {
                "row_number": 1,
                "source": "Direct",
                "state": "North",
                "program_name": "Alpha",
                "cluster": "Core",
                "campus_name": "Main",
                "owner": "Ava",
                "leads": 100,
                "admissions": 20,
            },
            {
                "row_number": 2,
                "source": "Partner",
                "state": "South",
                "program_name": "Beta",
                "cluster": "Advanced",
                "campus_name": "City",
                "owner": "Ben",
                "leads": 100,
                "admissions": 10,
            },
            {
                "row_number": 3,
                "source": "Slow",
                "state": "East",
                "program_name": "Gamma",
                "cluster": "Core",
                "campus_name": "Main",
                "owner": "Ava",
                "leads": 100,
                "admissions": 20,
            },
        ]

    @staticmethod
    def _period_b_metrics() -> list[dict]:
        return [
            {
                "row_number": 1,
                "source": "Direct",
                "state": "North",
                "program_name": "Alpha",
                "cluster": "Core",
                "campus_name": "Main",
                "owner": "Ava",
                "leads": 120,
                "admissions": 30,
            },
            {
                "row_number": 2,
                "source": "Partner",
                "state": "South",
                "program_name": "Beta",
                "cluster": "Advanced",
                "campus_name": "City",
                "owner": "Ben",
                "leads": 75,
                "admissions": 7,
            },
            {
                "row_number": 3,
                "source": "Slow",
                "state": "East",
                "program_name": "Gamma",
                "cluster": "Core",
                "campus_name": "Main",
                "owner": "Ava",
                "leads": 50,
                "admissions": 5,
            },
        ]

    @classmethod
    def _insert_metrics(cls, dataset_id: str, rows: list[dict]) -> None:
        query = text(
            """
            INSERT INTO analytics.uploaded_metrics
                (id, dataset_id, row_number, source, state, program_name, cluster,
                 campus_name, owner, cy_leads, cy_admission, py_leads, py_admission)
            VALUES
                (:id, :dataset_id, :row_number, :source, :state, :program_name, :cluster,
                 :campus_name, :owner, :leads, :admissions, 0, 0)
            """
        )
        cls.db.execute(
            query,
            [{"id": str(uuid4()), "dataset_id": dataset_id, **row} for row in rows],
        )

    def _query(self, workspace: str, **kwargs):
        return query_workspace_comparison(
            self.db,
            workspace=workspace,
            period_a_label=self.period_a,
            period_b_label=self.period_b,
            **kwargs,
        )

    def test_source_filtering(self):
        result = self._query("source", filters={"state": "North"})

        assert len(result["rows"]) == 1
        assert result["rows"][0]["source"] == "Direct"
        assert result["rows"][0]["state"] == "North"

    def test_program_filtering_and_optional_specialization(self):
        result = self._query("program", filters={"program": "Beta"})

        assert len(result["rows"]) == 1
        assert result["rows"][0]["program"] == "Beta"
        assert result["rows"][0]["specialization"] == "Advanced"

    def test_increased_and_decreased_filters_are_calculated_in_sql(self):
        increased = self._query("source", metric="leads", performance="increased", limit=10)
        decreased = self._query("source", metric="leads", performance="decreased", limit=10)

        assert [row["source"] for row in increased["rows"]] == ["Direct"]
        assert {row["source"] for row in decreased["rows"]} == {"Partner", "Slow"}
        assert all(row["absolute_change"] > 0 for row in increased["rows"])
        assert all(row["absolute_change"] < 0 for row in decreased["rows"])

    def test_sorting_supports_both_directions(self):
        ascending = self._query("source", sort_field="lead_change", sort_direction="asc", limit=10)
        descending = self._query("source", sort_field="lead_change", sort_direction="desc", limit=10)

        asc_values = [row["lead_change"] for row in ascending["rows"]]
        desc_values = [row["lead_change"] for row in descending["rows"]]
        assert asc_values == sorted(asc_values)
        assert desc_values == sorted(desc_values, reverse=True)

    def test_exact_and_percentage_display_modes_keep_correct_aggregates(self):
        exact = self._query("source", display="exact", filters={"source": "Direct"})
        percentage = self._query("source", display="percentage", filters={"source": "Direct"})

        assert exact["display"] == "exact"
        assert percentage["display"] == "percentage"
        assert exact["rows"][0]["period_a_leads"] == 100
        assert percentage["rows"][0]["lead_change_percent"] == 20.0

        conversion = self._query("source", metric="conversion_rate", filters={"source": "Direct"})
        conversion_row = conversion["rows"][0]
        assert conversion_row["absolute_change"] == 5.0
        assert conversion_row["conversion_change_percentage_points"] == 5.0

    def test_arbitrary_period_comparison_and_dataset_isolation(self):
        result = self._query("source", filters={"source": "Direct"})
        row = result["rows"][0]

        assert result["period_a"] == self.period_a
        assert result["period_b"] == self.period_b
        assert row["period_a_leads"] == 100
        assert row["period_b_leads"] == 120
        assert row["lead_change"] == 20
        assert row["lead_change_percent"] == 20.0
        assert all(row["source"] != "Leak source" for row in result["rows"])

    def test_large_result_is_limited_and_paginated(self):
        first_page = self._query("source", limit=25, sort_field="source", sort_direction="asc")
        second_page = self._query("source", limit=25, offset=25, sort_field="source", sort_direction="asc")

        assert len(first_page["rows"]) == 25
        assert first_page["pagination"]["has_more"] is True
        assert len(second_page["rows"]) == 25
        assert first_page["rows"][0]["source"] != second_page["rows"][0]["source"]
