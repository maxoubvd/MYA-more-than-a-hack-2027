"""Local J0/J1 acceptance check: no labels, prediction, or private row output."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time
import traceback

import numpy as np

from src import config
from src.preprocessing.cache_manager import fingerprint
from src.source_policy import load_registry
from src.utils.loaders import load_atd, load_homography, load_smart_tagging
from src.utils.official import check_official_revision


def run():
    load_registry()
    report = {"official_revision": check_official_revision(), "sources": {}}
    for source in ("tactical", "broadcast"):
        start = time.perf_counter()
        direct = load_atd(source, use_cache=False, save_cache=True)
        cached = load_atd(source, use_cache=True, save_cache=False)
        keys = ("players", "ball", "frame_ids", "video_frames", "players_metres", "ball_metres",
                "players_observed", "ball_observed", "players_speed_observed", "ball_speed_observed")
        equal = all(np.array_equal(direct[key], cached[key], equal_nan=True) for key in keys)
        if not cached["cache_hit"] or not equal or direct["team_mapping"] != cached["team_mapping"]:
            raise RuntimeError("Direct/cache roundtrip mismatch")
        matrices, errors, valid, table = load_homography(source)
        spec = config.get_source(source)
        report["sources"][source] = {
            "shape": list(direct["players"].shape), "frame_alignment": True,
            "mapping_complete": set(direct["team_mapping"]) == set(range(spec.num_slots)),
            "direct_cache_equal": equal, "cache_hit": cached["cache_hit"],
            "homography_shape": list(matrices.shape), "seconds": round(time.perf_counter() - start, 2),
            "provenance": direct["provenance"], "homography_input": fingerprint(spec.homography_path),
            "speed_unit_from_xml": direct["speed_unit"],
            "speed_documentation_conflict": direct["speed_documentation_conflict"],
            "negative_homography_errors_marked_unavailable": table.attrs["negative_error_count"],
        }
        print(f"{source}: {spec.num_frames} frames, {spec.num_slots} slots; alignment, XML, homography and cache OK", flush=True)
        del direct, cached, matrices, errors, valid, table
    smart = load_smart_tagging()
    report["smart_tagging"] = {"intervals": len(smart), "bounds_valid": True,
                               "interval_convention": smart.attrs["interval_convention"],
                               "input": fingerprint(config.TACTICAL_SMART_TAGGING_XML)}
    report["videos"] = {source: {"path": str(config.get_source(source).video_path.resolve()),
                                   "exists": config.get_source(source).video_path.is_file(),
                                   "required_for_j0_j1": False} for source in ("tactical", "broadcast")}
    destination = config.CACHE_DIR / "manifests" / "ingestion.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("J0/J1 ingestion checks passed. Local manifest: .cache/manifests/ingestion.json")
    return report


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        # Third-party exception messages may echo input. Full diagnostics stay local.
        destination = config.CACHE_DIR / "manifests" / "validation-error.log"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(traceback.format_exc(), encoding="utf-8")
        print(f"Validation failed ({type(error).__name__}); inspect .cache/manifests/validation-error.log locally", file=sys.stderr)
        sys.exit(1)
