"""Tests for RunSnapshot provenance badge fields.

D-5 Task 8: RunSnapshot records which data path was used,
enabling color-coded badges in the UI (green=official,
blue=curated_real, yellow=synthetic, red=synthetic_fallback).
"""

from uuid import uuid4

from src.models.run import RunSnapshot


class TestRunSnapshotProvenance:
    def test_run_snapshot_has_data_mode(self):
        snap = RunSnapshot(
            run_id=uuid4(),
            model_version_id=uuid4(),
            taxonomy_version_id=uuid4(),
            concordance_version_id=uuid4(),
            mapping_library_version_id=uuid4(),
            assumption_library_version_id=uuid4(),
            prompt_pack_version_id=uuid4(),
            data_mode="curated_real",
            data_source_id="saudi_io_kapsarc_2018",
            checksum_verified=True,
        )
        assert snap.data_mode == "curated_real"
        assert snap.data_source_id == "saudi_io_kapsarc_2018"
        assert snap.checksum_verified is True

    def test_run_snapshot_provenance_defaults(self):
        snap = RunSnapshot(
            run_id=uuid4(),
            model_version_id=uuid4(),
            taxonomy_version_id=uuid4(),
            concordance_version_id=uuid4(),
            mapping_library_version_id=uuid4(),
            assumption_library_version_id=uuid4(),
            prompt_pack_version_id=uuid4(),
        )
        assert snap.data_mode is None
        assert snap.data_source_id is None
        assert snap.checksum_verified is False
