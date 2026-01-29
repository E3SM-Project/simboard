import glob
import os


def validate_e3sm_experiment(exp_dir):
    required = [
        "e3sm_timing.*",
        "timing.*.tar.gz",
        "README.case.*",
        "GIT_DESCRIBE.*",
        "CaseDocs.*/",
    ]

    for pattern in required:
        if not glob.glob(os.path.join(exp_dir, pattern)):
            raise OSError(f"Missing required file: {pattern}")
