"""Match one replay run's alerts against fully annotated event intervals."""
import argparse
import csv
import json
import math
import heapq
from pathlib import Path


def evaluate(predictions, intervals, duration_seconds=None):
    """Maximum point/interval matching; each event and alert is counted at most once."""
    if any(not math.isfinite(v) or v < 0 for v in predictions):
        raise ValueError("Alert times must be finite and nonnegative.")
    if any(not math.isfinite(v) or v < 0 for pair in intervals for v in pair) or any(a>b for a,b in intervals):
        raise ValueError("Intervals must be finite, nonnegative and ordered.")
    if duration_seconds is not None:
        if not math.isfinite(duration_seconds) or duration_seconds <= 0:
            raise ValueError("Evaluated duration must be finite and positive.")
        if any(t > duration_seconds for t in predictions) or any(b>duration_seconds for _,b in intervals):
            raise ValueError("Alerts/labels exceed the evaluated duration.")
    ordered = sorted(intervals)
    available,index,tp = [],0,0
    for value in sorted(predictions):
        while index < len(ordered) and ordered[index][0] <= value:
            heapq.heappush(available,ordered[index][1]); index += 1
        while available and available[0] < value:
            heapq.heappop(available)
        if available:
            heapq.heappop(available); tp += 1
    denominator = len(predictions)+len(intervals)
    return {"true_positives": tp, "false_positives": len(predictions)-tp,
            "false_negatives": len(intervals)-tp,
            "precision": tp/len(predictions) if predictions else None,
            "recall": tp/len(intervals) if intervals else None,
            "f1": 2*tp/denominator if denominator else None,
            "evaluated_seconds":duration_seconds,
            "false_alarms_per_hour":(len(predictions)-tp)*3600/duration_seconds if duration_seconds else None}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", required=True, help="CSV exported from Alarm history")
    p.add_argument("--labels", required=True, help="CSV with start_seconds,end_seconds")
    p.add_argument("--run-id", required=True, help="Replay run_id in the exported CSV")
    p.add_argument("--allow-empty-run", action="store_true", help="Explicitly confirm a completed run with zero exported alerts")
    p.add_argument("--kind", default="suspected_throw", choices=["suspected_throw", "person_movement"])
    p.add_argument("--duration-seconds",type=float,help="Duration of the fully reviewed video/run for false alarms per hour")
    p.add_argument("--output",help="Save a JSON evaluation report")
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
        result = {"run_id":args.run_id,"kind":args.kind,
                  **evaluate(predictions,intervals,args.duration_seconds)}
        print(json.dumps(result,indent=2))
        if args.output:
            path = Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        print("Meaningful only when every target event in the entire replay is annotated.")
    except (ValueError, KeyError, OSError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
