from datetime import datetime
from typing import Any

from dateutil.relativedelta import relativedelta


def parse_case_status(file_path: str) -> dict[str, Any]:
    """
    Parse the case status file and extract relevant information.

    Parameters
    ----------
    file_path : str
        Path to the case status file.

    Returns
    -------
    dict[str, Any]
        A dictionary containing parsed information such as run start and
        end dates.
    """
    result: dict[str, Any] = {
        "run_start_date": None,
        "run_end_date": None,
    }

    with open(file_path, "r") as file:
        for line in file:
            if "RUN_STARTDATE" in line:
                result["run_start_date"] = line.split("RUN_STARTDATE=")[1]
                result["run_start_date"] = result["run_start_date"].split()[0]
            elif "STOP_OPTION" in line and "STOP_N" in line:
                stop_option = line.split("STOP_OPTION=")[1].split(",")[0]
                stop_n = int(line.split("STOP_N=")[1].split()[0])

                result["run_end_date"] = _calculate_run_end_date(
                    result["run_start_date"], stop_option, stop_n
                )

    return result


def _calculate_run_end_date(
    run_start_date: str | None, stop_option: str | None, stop_n: int | None
) -> str | None:
    if not (run_start_date and stop_option and stop_n):
        return None

    start = datetime.strptime(run_start_date, "%Y-%m-%d")
    option = stop_option.lower()
    n = stop_n

    if option == "ndays":
        end = start + relativedelta(days=n)
    elif option == "nmonths":
        end = start + relativedelta(months=n)
    elif option == "nyears":
        end = start + relativedelta(years=n)
    else:
        return None

    return end.strftime("%Y-%m-%d")
