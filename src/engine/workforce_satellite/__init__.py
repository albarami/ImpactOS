"""Workforce/Saudization Satellite — MVP-11.

Deterministic 4-step pipeline:
1. delta_jobs (from SatelliteAccounts — already computed)
2. Occupation decomposition (delta_jobs × OccupationBridge)
3. Nationality feasibility split (three-tier → range estimates)
4. Nitaqat compliance check (diagnostic only, no clipping)

Consumes D-4 curated data. No LLM calls.
"""
