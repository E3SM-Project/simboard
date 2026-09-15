"""Shared identity rules for the Chrysalis E3SM v3 production backfill.

Source: https://docs.e3sm.org/e3sm_data_docs/_build/html/v3/CoupledSystem/simulation_data/simulation_table.html
"""

from app.features.catalog.enums import CaseSimulationType

CHRYSALIS_MACHINE_NAME = "chrysalis"
V3_SIMULATIONS = (
    "v3.LR.piControl",
    "v3.LR.abrupt-4xCO2_0101_bcdt15m",
    "v3.LR.1pctCO2_0101_bcdt15m",
    "v3.LR.historical_0051",
    "v3.LR.historical_0101",
    "v3.LR.historical_0151",
    "v3.LR.historical_0201",
    "v3.LR.historical_0251",
    "v3.LR.hist-GHG_0101",
    "v3.LR.hist-GHG_0151",
    "v3.LR.hist-GHG_0201",
    "v3.LR.hist-aer_0101",
    "v3.LR.hist-aer_0151",
    "v3.LR.hist-aer_0201",
    "v3.LR.hist-xGHG-xaer_0101",
    "v3.LR.hist-xGHG-xaer_0151",
    "v3.LR.hist-xGHG-xaer_0201",
    "v3.LR.amip_0101",
    "v3.LR.amip_0151",
    "v3.LR.amip_0201",
    "v3.LR.piClim-control-iceini",
    "v3.LR.piClim-histall_0101",
    "v3.LR.piClim-histall_0151",
    "v3.LR.piClim-histall_0201",
    "v3.LR.piClim-histGHG_0101",
    "v3.LR.piClim-histGHG_0151",
    "v3.LR.piClim-histGHG_0201",
    "v3.LR.piClim-histaer_0101",
    "v3.LR.piClim-histaer_0151",
    "v3.LR.piClim-histaer_0201",
    "LR_ensemble",
    "v3.NARRM.amip_0101",
    "v3.NARRM_r0125.amip_0101",
    "RRM_ensemble",
    "v3.AMZRRM.amip_0101",
    "v3.EARRM.amip_0101",
)
V3_CASE_NAMES = frozenset(V3_SIMULATIONS)
V3_PRODUCTION_SIMULATION_TYPE = CaseSimulationType.PRODUCTION
