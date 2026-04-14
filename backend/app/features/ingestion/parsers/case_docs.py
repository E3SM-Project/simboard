import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from dateutil.relativedelta import relativedelta

from app.features.ingestion.parsers.utils import _open_text
from app.features.simulation.schemas import KNOWN_EXPERIMENT_TYPES


def parse_env_case(env_case_path: str | Path) -> dict[str, str | None]:
    """Parse env_case.xml (plain or gzipped).

    Parameters
    ----------
    env_case_path : str or Path
        Path to the env_case.xml file (plain or .gz)

    Returns
    -------
    dict
        Dictionary with case metadata (values are str or None), including:

        - ``case_name``: Case name (``CASE``)
        - ``case_group``: Case group (``CASE_GROUP``)
        - ``machine``: Machine name (``MACH``)
        - ``user``: Real user (``REALUSER``)
        - ``campaign``: Derived campaign identifier from the case name
        - ``experiment_type``: Derived experiment type, constrained to
          KNOWN_EXPERIMENT_TYPES when possible
        - ``compset_alias``: Compset alias (``COMPSET``)
    """
    env_case_path = Path(env_case_path)

    case_name = _extract_value_from_file(env_case_path, "CASE")
    case_group = _extract_value_from_file(env_case_path, "CASE_GROUP")
    machine = _extract_value_from_file(env_case_path, "MACH")
    user = _extract_value_from_file(env_case_path, "REALUSER")
    compset_alias = _extract_value_from_file(env_case_path, "COMPSET")
    case_root = _extract_value_from_file(env_case_path, "CASEROOT")

    # Extract metadata that requires special handling
    campaign, experiment_type = _extract_campaign_and_experiment_type(case_name)

    return {
        "case_name": case_name,
        "case_group": case_group,
        "machine": machine,
        "user": user,
        "campaign": campaign,
        "experiment_type": experiment_type,
        "compset_alias": compset_alias,
        "case_root": case_root,
    }


def parse_env_build(env_build_path: str | Path) -> dict[str, str | None]:
    """Parse env_build.xml (plain or gzipped).

    Parameters
    ----------
    env_build_path : str or Path
        Path to the env_build.xml file (plain or .gz)

    Returns
    -------
    dict
        Dictionary with keys 'grid_resolution', 'compiler', 'mpilib' (str or None)
    """
    env_build_path = Path(env_build_path)

    grid_resolution = _extract_value_from_file(env_build_path, "GRID")
    compiler = _extract_value_from_file(env_build_path, "COMPILER")
    mpilib = _extract_value_from_file(env_build_path, "MPILIB")

    return {"grid_resolution": grid_resolution, "compiler": compiler, "mpilib": mpilib}


def parse_env_run(env_run_path: str | Path) -> dict[str, str | None]:
    """Parse env_run.xml (plain or gzipped) to extract runtime settings.

    Parameters
    ----------
    env_run_path : str or Path
        Path to the env_run.xml file (plain or .gz)

    Returns
    -------
    dict
        Dictionary with runtime initialization and simulation date metadata.
    """
    env_run_path = Path(env_run_path)
    initialization_type = _extract_value_from_file(env_run_path, "RUN_TYPE")
    run_start_date = _extract_value_from_file(env_run_path, "RUN_STARTDATE")
    run_ref_date = _extract_value_from_file(env_run_path, "RUN_REFDATE")
    stop_option = _extract_value_from_file(env_run_path, "STOP_OPTION")
    stop_n = _extract_value_from_file(env_run_path, "STOP_N")
    stop_date = _extract_value_from_file(env_run_path, "STOP_DATE")
    output_path = _extract_value_from_file(env_run_path, "RUNDIR")
    archive_path = _extract_value_from_file(env_run_path, "DOUT_S_ROOT")
    postprocessing_script = _extract_value_from_file(env_run_path, "POSTRUN_SCRIPT")

    simulation_start_date = (
        run_ref_date if initialization_type == "branch" else run_start_date
    )
    simulation_end_date = _calculate_simulation_end_date(
        simulation_start_date,
        stop_option,
        stop_n,
        stop_date,
    )

    return {
        "initialization_type": initialization_type,
        "simulation_start_date": simulation_start_date,
        "simulation_end_date": simulation_end_date,
        "output_path": output_path,
        "archive_path": archive_path,
        "postprocessing_script": postprocessing_script,
    }


def _extract_value_from_file(path: Path, entry_id: str) -> str | None:
    """Extract the value of a specific entry from an XML file.

    Parameters
    ----------
    path : Path
        Path to the XML file (plain or .gz)
    entry_id : str
        The ID of the entry to extract

    Returns
    -------
    str | None
        The value of the entry, or None if not found
    """
    try:
        text = _open_text(path)
    except (OSError, UnicodeDecodeError):
        return None

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None

    return _find_entry_value(root, entry_id)


def _find_entry_value(root, entry_id: str) -> str | None:
    """
    Search for <entry id="..." value="..." /> or <entry id="...">text</entry>.

    Parameters
    ----------
    root : Element
        The root element of the XML tree
    entry_id : str
        The ID of the entry to find

    Returns
    -------
    str | None
        The value of the entry, or None if not found
    """
    for entry in root.iter("entry"):
        if entry.attrib.get("id") == entry_id:
            # Prefer value attribute if present
            if "value" in entry.attrib:
                return entry.attrib["value"]

            # Otherwise, use text content if present and non-empty
            if entry.text and entry.text.strip():
                return entry.text.strip()

    return None


def _extract_campaign_and_experiment_type(
    case_name: str | None,
) -> tuple[str | None, str | None]:
    """Extract campaign and experiment type from case name.

    Parameters
    ----------
    case_name : str or None
        The case name to parse.

    Returns
    -------
    tuple of (str or None, str or None)
        campaign and experiment_type values.
    """
    campaign = None
    experiment_type = None

    # Example: v3.LR.historical
    if case_name:
        # Remove trailing instance suffix like _0121
        base = re.sub(r"_\d+$", "", case_name)

        # Only infer campaign for dot-delimited case names.
        # Timing files sometimes use short case names (e.g., e3sm_v1_ne30)
        # that do not encode campaign/experiment type.
        if "." not in base:
            return None, None

        # Campaign is the base case name without the trailing instance suffix
        campaign = base

        # Candidate experiment type = last dot token
        candidate = campaign.split(".")[-1]

        if candidate in KNOWN_EXPERIMENT_TYPES:
            experiment_type = candidate

    return campaign, experiment_type


def _calculate_simulation_end_date(
    simulation_start_date: str | None,
    stop_option: str | None,
    stop_n: str | None,
    stop_date: str | None,
) -> str | None:
    if not stop_option:
        return None

    if stop_option == "date":
        return _parse_stop_date(stop_date)

    if not simulation_start_date:
        return None

    if stop_n is None:
        return None

    try:
        start_date = datetime.strptime(simulation_start_date, "%Y-%m-%d")
        stop_n_int = int(stop_n)
    except ValueError:
        return None

    if stop_option == "ndays":
        end_date = start_date + relativedelta(days=stop_n_int)
    elif stop_option == "nmonths":
        end_date = start_date + relativedelta(months=stop_n_int)
    elif stop_option == "nyears":
        end_date = start_date + relativedelta(years=stop_n_int)
    else:
        return None

    return end_date.strftime("%Y-%m-%d")


def _parse_stop_date(stop_date: str | None) -> str | None:
    if not stop_date:
        return None

    try:
        return datetime.strptime(stop_date, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return None
