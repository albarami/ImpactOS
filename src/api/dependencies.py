"""FastAPI dependency injection factories for repositories.

Each factory takes AsyncSession via Depends(get_async_session) and returns
a repository instance. API endpoints use these via Depends().
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session
from src.repositories.compiler import CompilationRepository, OverridePairRepository
from src.repositories.depth import DepthArtifactRepository, DepthPlanRepository
from src.repositories.documents import (
    DocumentRepository,
    ExtractionJobRepository,
    LineItemRepository,
)
from src.repositories.engine import (
    BatchRepository,
    ModelDataRepository,
    ModelVersionRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)
from src.repositories.exports import ExportRepository
from src.repositories.feasibility import (
    ConstraintSetRepository,
    FeasibilityResultRepository,
)
from src.repositories.governance import AssumptionRepository, ClaimRepository
from src.repositories.libraries import (
    AssumptionLibraryRepository,
    MappingLibraryRepository,
    ScenarioPatternRepository,
)
from src.repositories.metrics import EngagementRepository, MetricEventRepository
from src.repositories.scenarios import ScenarioVersionRepository
from src.repositories.workforce import (
    EmploymentCoefficientsRepository,
    SaudizationRulesRepository,
    SectorOccupationBridgeRepository,
    WorkforceResultRepository,
)

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


async def get_export_repo(
    session: AsyncSession = Depends(get_async_session),
) -> ExportRepository:
    return ExportRepository(session)


# ---------------------------------------------------------------------------
# Metrics / Observability
# ---------------------------------------------------------------------------


async def get_metric_event_repo(
    session: AsyncSession = Depends(get_async_session),
) -> MetricEventRepository:
    return MetricEventRepository(session)


async def get_engagement_repo(
    session: AsyncSession = Depends(get_async_session),
) -> EngagementRepository:
    return EngagementRepository(session)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


async def get_document_repo(
    session: AsyncSession = Depends(get_async_session),
) -> DocumentRepository:
    return DocumentRepository(session)


async def get_extraction_job_repo(
    session: AsyncSession = Depends(get_async_session),
) -> ExtractionJobRepository:
    return ExtractionJobRepository(session)


async def get_line_item_repo(
    session: AsyncSession = Depends(get_async_session),
) -> LineItemRepository:
    return LineItemRepository(session)


# ---------------------------------------------------------------------------
# Governance
# ---------------------------------------------------------------------------


async def get_assumption_repo(
    session: AsyncSession = Depends(get_async_session),
) -> AssumptionRepository:
    return AssumptionRepository(session)


async def get_claim_repo(
    session: AsyncSession = Depends(get_async_session),
) -> ClaimRepository:
    return ClaimRepository(session)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


async def get_scenario_version_repo(
    session: AsyncSession = Depends(get_async_session),
) -> ScenarioVersionRepository:
    return ScenarioVersionRepository(session)


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------


async def get_compilation_repo(
    session: AsyncSession = Depends(get_async_session),
) -> CompilationRepository:
    return CompilationRepository(session)


async def get_override_pair_repo(
    session: AsyncSession = Depends(get_async_session),
) -> OverridePairRepository:
    return OverridePairRepository(session)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


async def get_model_version_repo(
    session: AsyncSession = Depends(get_async_session),
) -> ModelVersionRepository:
    return ModelVersionRepository(session)


async def get_model_data_repo(
    session: AsyncSession = Depends(get_async_session),
) -> ModelDataRepository:
    return ModelDataRepository(session)


async def get_run_snapshot_repo(
    session: AsyncSession = Depends(get_async_session),
) -> RunSnapshotRepository:
    return RunSnapshotRepository(session)


async def get_result_set_repo(
    session: AsyncSession = Depends(get_async_session),
) -> ResultSetRepository:
    return ResultSetRepository(session)


async def get_batch_repo(
    session: AsyncSession = Depends(get_async_session),
) -> BatchRepository:
    return BatchRepository(session)


# ---------------------------------------------------------------------------
# Depth Engine
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Feasibility
# ---------------------------------------------------------------------------


async def get_constraint_set_repo(
    session: AsyncSession = Depends(get_async_session),
) -> ConstraintSetRepository:
    return ConstraintSetRepository(session)


async def get_feasibility_result_repo(
    session: AsyncSession = Depends(get_async_session),
) -> FeasibilityResultRepository:
    return FeasibilityResultRepository(session)


# ---------------------------------------------------------------------------
# Depth Engine
# ---------------------------------------------------------------------------


async def get_depth_plan_repo(
    session: AsyncSession = Depends(get_async_session),
) -> DepthPlanRepository:
    return DepthPlanRepository(session)


async def get_depth_artifact_repo(
    session: AsyncSession = Depends(get_async_session),
) -> DepthArtifactRepository:
    return DepthArtifactRepository(session)


# ---------------------------------------------------------------------------
# Workforce
# ---------------------------------------------------------------------------


async def get_employment_coefficients_repo(
    session: AsyncSession = Depends(get_async_session),
) -> EmploymentCoefficientsRepository:
    return EmploymentCoefficientsRepository(session)


async def get_sector_occupation_bridge_repo(
    session: AsyncSession = Depends(get_async_session),
) -> SectorOccupationBridgeRepository:
    return SectorOccupationBridgeRepository(session)


async def get_saudization_rules_repo(
    session: AsyncSession = Depends(get_async_session),
) -> SaudizationRulesRepository:
    return SaudizationRulesRepository(session)


async def get_workforce_result_repo(
    session: AsyncSession = Depends(get_async_session),
) -> WorkforceResultRepository:
    return WorkforceResultRepository(session)


# ---------------------------------------------------------------------------
# Knowledge Flywheel (Libraries)
# ---------------------------------------------------------------------------


async def get_mapping_library_repo(
    session: AsyncSession = Depends(get_async_session),
) -> MappingLibraryRepository:
    return MappingLibraryRepository(session)


async def get_assumption_library_repo(
    session: AsyncSession = Depends(get_async_session),
) -> AssumptionLibraryRepository:
    return AssumptionLibraryRepository(session)


async def get_scenario_pattern_repo(
    session: AsyncSession = Depends(get_async_session),
) -> ScenarioPatternRepository:
    return ScenarioPatternRepository(session)
