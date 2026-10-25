"""Public diagnostic only: reproduce official scores, optionally check a frozen MYA CSV.

This module is never imported by prediction. No training, tuning, variant search
or selection occurs here. Detailed reports and frame-derived outputs stay local.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback

from src import config
from src.pipeline import _atomic_json
from src.refinement.exporter import sha256_file
from src.source_policy import require_use
from src.utils.official import check_official_revision

# Published scores at the pinned official revision, rounded to four decimals.
# Values check the scorer installation, never choose a MYA setting.
REFERENCE_SCORES = {
    "baseline_raw": (.0378, .5972),
    "baseline_smooth25": (.2868, .6200),
    "baseline_smooth50": (.3256, .6207),
    "baseline_smooth125": (.4242, .5812),
}


def frozen_submission(path):
    path = Path(path).resolve()
    digest = sha256_file(path)
    manifest_path = config.CACHE_DIR / "runs" / f"baseline_{digest}.json"
    if not manifest_path.is_file():
        raise ValueError("Generate the candidate and its manifest before running public diagnostics")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["output"]["sha256"] != digest or manifest["ground_truth_used"] is not False:
        raise ValueError("Candidate manifest is inconsistent")
    return path, digest, manifest


def run(submission=None):
    revision = check_official_revision()
    require_use("public_labels", "diagnostic")
    candidate = frozen_submission(submission) if submission is not None else None
    output = config.CACHE_DIR / "jalon2" / "public_diagnostic"
    output.mkdir(parents=True, exist_ok=True)
    summary = {"purpose": "diagnostic_only", "official_revision": revision, "selection_performed": False,
               "default_half_width_fixed_before_diagnostic": 50, "references": {}, "candidate": None}
    # A fresh folder restricts the scorer to these four references and one frozen
    # candidate; unrelated user submissions cannot accidentally enter the board.
    with tempfile.TemporaryDirectory(prefix="inputs-", dir=output) as temporary:
        inputs = Path(temporary)
        for name in REFERENCE_SCORES:
            source = config.RESULTS_DIR / f"{name}.csv"
            shutil.copyfile(source, inputs / source.name)
            summary["references"][name] = {"sha256": sha256_file(source)}
        if candidate:
            path, digest, manifest = candidate
            shutil.copyfile(path, inputs / "MYA.csv")
            if sha256_file(inputs / "MYA.csv") != digest:
                raise RuntimeError("Candidate changed after freezing")
            summary["candidate"] = {"sha256": digest, "settings_frozen_before_labels": manifest["settings"],
                                    "code": manifest["code"]}
        # Save the candidate/settings snapshot before the scorer reads any labels.
        _atomic_json(output / "frozen_inputs.json", summary)
        command = [sys.executable, str(config.EVAL_DIR / "run_evaluation.py"), "--gt", "public",
                   "--results", str(inputs), "--out", str(output), "--bootstrap", "0", "--no-detail"]
        with (output / "official-evaluation.log").open("w", encoding="utf-8") as log:
            process = subprocess.run(command, cwd=config.CHALLENGE_DIR, stdout=log, stderr=subprocess.STDOUT)
        if process.returncode:
            raise RuntimeError("Official scorer failed; inspect local official-evaluation.log")
    with (output / "scoreboard.csv").open(encoding="utf-8", newline="") as handle:
        scores = {row["submission"]: row for row in csv.DictReader(handle)}
    for name, expected in REFERENCE_SCORES.items():
        row = scores[name]
        actual = float(row["spell_f1_mean"]), float(row["macro_f1"])
        if row["status"] != "scored" or tuple(round(x, 4) for x in actual) != expected:
            raise RuntimeError("Published reference scores were not reproduced")
        summary["references"][name].update(spell_f1=actual[0], macro_f1=actual[1], published_scores_reproduced=True)
    if candidate:
        row = scores["MYA"]
        if row["status"] != "scored":
            raise RuntimeError("Candidate rejected by official scorer")
        summary["candidate"].update(spell_f1=float(row["spell_f1_mean"]), macro_f1=float(row["macro_f1"]))
    _atomic_json(output / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--submission", type=Path, help="Optional CSV already frozen by src.pipeline")
    args = parser.parse_args(argv)
    try:
        summary = run(args.submission)
    except Exception as error:
        destination = config.CACHE_DIR / "jalon2" / "diagnostic-error.log"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(traceback.format_exc(), encoding="utf-8")
        print(f"Public diagnostic failed ({type(error).__name__}); details remain local", file=sys.stderr)
        return 1
    print("All four published reference scores reproduced with the pinned official scorer")
    print("Diagnostic only; no variant selected. Reports: .cache/jalon2/public_diagnostic/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
