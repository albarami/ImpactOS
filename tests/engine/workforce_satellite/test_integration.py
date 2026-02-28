"""Integration tests — WorkforceSatellite with SatelliteAccounts."""

from uuid import uuid4

import numpy as np

from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
from src.engine.workforce_satellite.satellite import WorkforceSatellite


class TestWithSatelliteAccounts:
    """Tests that WorkforceSatellite works with real SatelliteResult."""

    def test_works_with_real_satellite_result(
        self, two_sector_bridge, two_sector_classifications,
    ) -> None:
        """WorkforceSatellite.analyze() works with SatelliteAccounts output."""
        sat_accounts = SatelliteAccounts()
        coefficients = SatelliteCoefficients(
            jobs_coeff=np.array([0.5, 1.0]),
            import_ratio=np.array([0.2, 0.3]),
            va_ratio=np.array([0.6, 0.4]),
            version_id=uuid4(),
        )
        delta_x = np.array([100.0, 200.0])
        sat_result = sat_accounts.compute(
            delta_x=delta_x, coefficients=coefficients,
        )

        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=sat_result,
            sector_codes=["A", "F"],
        )
        # delta_jobs = [50, 200], total = 250
        assert abs(result.total_jobs - 250.0) < 0.01

    def test_works_with_unconstrained_and_feasible(
        self, two_sector_bridge, two_sector_classifications,
    ) -> None:
        """WorkforceSatellite works with both unconstrained/feasible results."""
        sat_accounts = SatelliteAccounts()
        coefficients = SatelliteCoefficients(
            jobs_coeff=np.array([0.5, 1.0]),
            import_ratio=np.array([0.2, 0.3]),
            va_ratio=np.array([0.6, 0.4]),
            version_id=uuid4(),
        )

        # Unconstrained
        unconstrained_result = sat_accounts.compute(
            delta_x=np.array([100.0, 200.0]),
            coefficients=coefficients,
        )
        # Feasible (clipped)
        feasible_result = sat_accounts.compute(
            delta_x=np.array([80.0, 150.0]),
            coefficients=coefficients,
        )

        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )

        unc_workforce = ws.analyze(
            satellite_result=unconstrained_result,
            sector_codes=["A", "F"],
        )
        feas_workforce = ws.analyze(
            satellite_result=feasible_result,
            sector_codes=["A", "F"],
        )

        # Unconstrained should have more jobs than feasible
        assert unc_workforce.total_jobs > feas_workforce.total_jobs

    def test_works_with_two_sector_model(
        self, two_sector_bridge, two_sector_classifications,
    ) -> None:
        """Works with full 2-sector IO model from ModelStore."""
        store = ModelStore()
        Z = np.array([[10.0, 20.0], [5.0, 40.0]])
        x = np.array([100.0, 200.0])
        mv = store.register(
            Z=Z, x=x,
            sector_codes=["A", "F"],
            base_year=2024,
            source="test",
        )
        model = store.get(mv.model_version_id)

        sat_accounts = SatelliteAccounts()
        coefficients = SatelliteCoefficients(
            jobs_coeff=np.array([0.5, 1.0]),
            import_ratio=np.array([0.2, 0.3]),
            va_ratio=np.array([0.6, 0.4]),
            version_id=uuid4(),
        )
        delta_d = np.array([10.0, 20.0])

        from src.engine.leontief import LeontiefSolver
        solver = LeontiefSolver()
        solve_result = solver.solve(
            loaded_model=model, delta_d=delta_d,
        )
        sat_result = sat_accounts.compute(
            delta_x=solve_result.delta_x_total,
            coefficients=coefficients,
        )

        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=sat_result,
            sector_codes=["A", "F"],
        )
        assert len(result.sector_summaries) == 2
        assert result.total_jobs > 0
