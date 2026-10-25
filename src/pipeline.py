"""Generate a complete baseline CSV, without reading any possession labels.

Run from the MYA root: python -m src.pipeline --output submissions/MYA.csv
Public diagnostics are deliberately a separate command (src.diagnostics).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback

import numpy as np

from src import config
from src.baseline import DEFAULT_HALF_WIDTH, predict_baseline
from src.refinement.exporter import export_submission, sha256_file
from src.source_policy import require_use
from src.utils.loaders import load_atd
from src.utils.official import check_official_revision


def code_provenance():
    files = sorted(config.SRC_DIR.rglob("*.py"))
    signatures = {path.relative_to(config.MYA_DIR).as_posix(): sha256_file(path) for path in files}
    revision = subprocess.run(["git", "-C", str(config.MYA_DIR), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(config.MYA_DIR), "status", "--porcelain"], capture_output=True,
                           text=True, check=True).stdout.strip()
    return {"git_revision": revision, "working_tree_dirty": bool(dirty), "source_files_sha256": signatures}


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run(output=None, *, half_width=DEFAULT_HALF_WIDTH, missing_label="D", use_cache=True):
    # Configuration and code snapshots are frozen before predictions or diagnostics.
    if type(half_width) is not int or half_width < 0 or missing_label not in ("D", "X"):
        raise ValueError("Invalid baseline configuration")
    revision = check_official_revision()
    require_use("tactical_atd_txt", "pipeline")
    require_use("tactical_atd_xml", "pipeline")
    code = code_provenance()
    settings = {"method": "nearest_player_majority_v1", "half_width": half_width,
                "missing_label": missing_label, "periods": config.EVALUATED_INTERVALS,
                "dead_zone": config.DEAD_ZONE_2HT_INTERVAL, "pitch_metres": config.PITCH_DIMS,
                "default_origin": "published official baseline_smooth50; not chosen on public labels"}
    atd = load_atd("tactical", use_cache=use_cache)
    if len(atd["ball"]) != config.TOTAL_FRAMES:
        raise ValueError("Tactical frame count differs from the submission contract")
    labels = predict_baseline(atd, half_width=half_width, missing_label=missing_label,
                              intervals=config.EVALUATED_INTERVALS, dead_zone=config.DEAD_ZONE_2HT_INTERVAL)
    artifact = export_submission(output or config.SUBMISSIONS_DIR / "MYA.csv", labels, n_expected=config.TOTAL_FRAMES)
    # Detect code edits during execution rather than assigning the wrong provenance.
    if code_provenance()["source_files_sha256"] != code["source_files_sha256"]:
        raise RuntimeError("Source code changed during prediction; regenerate the CSV")
    manifest = {"settings": settings, "official_revision": revision, "code": code,
                "inputs": atd["provenance"], "output": artifact,
                "label_counts": {label: int(np.sum(labels == label)) for label in config.LABELS},
                "ground_truth_used": False, "training": False}
    destination = config.CACHE_DIR / "runs" / f"baseline_{artifact['sha256']}.json"
    _atomic_json(destination, manifest)
    return {**artifact, "manifest": str(destination), "settings": settings}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=config.SUBMISSIONS_DIR / "MYA.csv")
    parser.add_argument("--window", type=int, default=DEFAULT_HALF_WIDTH, help="Centred half-width in frames (default +/-50)")
    parser.add_argument("--missing-label", choices=("D", "X"), default="D")
    parser.add_argument("--no-cache", action="store_true", help="Reparse the validated raw tracking")
    args = parser.parse_args(argv)
    if args.window < 0:
        parser.error("--window must be nonnegative")
    try:
        result = run(args.output, half_width=args.window, missing_label=args.missing_label, use_cache=not args.no_cache)
    except Exception as error:
        # Avoid echoing third-party exception contents derived from private inputs.
        destination = config.CACHE_DIR / "jalon2" / "generation-error.log"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(traceback.format_exc(), encoding="utf-8")
        print(f"Generation failed ({type(error).__name__}); inspect .cache/jalon2/generation-error.log locally", file=sys.stderr)
        return 1
    print(f"CSV validated: {result['rows']} rows; {Path(result['path']).name}")
    print(f"SHA-256: {result['sha256']}")
    print("Provenance saved locally in .cache/runs/; no ground truth read")
    return 0


if __name__ == "__main__":
    sys.exit(main())
