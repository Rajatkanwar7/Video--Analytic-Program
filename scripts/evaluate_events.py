"""Match one replay run's alerts against fully annotated event intervals."""
import argparse
import csv
import json
import math


def evaluate(predictions, intervals):
    """Maximum one-to-one matching, including overlapping annotation windows."""
    assigned = {}
    def match(prediction, seen):
        for index, (start, end) in enumerate(intervals):
            if index in seen or not start <= predictions[prediction] <= end:
                continue
            seen.add(index)
            if index not in assigned or match(assigned[index], seen):
                assigned[index] = prediction
                return True
        return False
    for index in range(len(predictions)):
        match(index, set())
    tp = len(assigned)
    return {"true_positives": tp, "false_positives": len(predictions)-tp,
            "false_negatives": len(intervals)-tp,
            "precision": tp/len(predictions) if predictions else None,
            "recall": tp/len(intervals) if intervals else None}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", required=True, help="CSV exported from Alarm history")
    p.add_argument("--labels", required=True, help="CSV with start_seconds,end_seconds")
    p.add_argument("--run-id", required=True, help="Replay run_id in the exported CSV")
    p.add_argument("--allow-empty-run", action="store_true", help="Explicitly confirm a completed run with zero exported alerts")
    p.add_argument("--kind", default="suspected_throw", choices=["suspected_throw", "person_movement"])
    args = p.parse_args()
    try:
        with open(args.events, encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["run_id"] == args.run_id]
        if not rows and not args.allow_empty_run:
            raise ValueError("No rows match run-id. Check the replay/export; use --allow-empty-run only for a confirmed completed zero-alert run.")
        predictions = [float(r["source_time"]) for r in rows if r["kind"] == args.kind]
        with open(args.labels, encoding="utf-8-sig", newline="") as f:
            intervals = [(float(r["start_seconds"]), float(r["end_seconds"])) for r in csv.DictReader(f)]
        if any(not math.isfinite(v) or v < 0 for pair in intervals for v in pair):
            raise ValueError("Annotation times must be finite and nonnegative.")
        if any(start > end for start, end in intervals):
            raise ValueError("Each start time must be no later than its end time.")
        print(json.dumps(evaluate(predictions, intervals), indent=2))
        print("Meaningful only when every target event in the entire replay is annotated.")
    except (ValueError, KeyError, OSError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
