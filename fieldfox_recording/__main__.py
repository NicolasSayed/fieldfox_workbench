"""Run with python -m fieldfox_recording inspect|export|plot|gui."""
from __future__ import annotations

import argparse
import json
import sys
from .parser import FieldFoxRecording, RecordingError, inspect_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent FieldFox GPSA/RTSA trace decoder (static reconstruction)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("gui", help="Open the Tkinter recording viewer")
    inspect = sub.add_parser("inspect", help="Inspect file prefixes, states and trace boundaries")
    inspect.add_argument("path")
    export = sub.add_parser("export", help="Export a complete GPSA/RTSA trace session")
    export.add_argument("path")
    export.add_argument("--format", choices=["csv", "npz", "mat"], required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--chunk-sweeps", type=int, default=5000, help="MAT: maximum sweeps per part")
    export.add_argument("--max-part-mib", type=float, default=128, help="MAT: array payload budget per part")
    export.add_argument("--source-timezone", default="EST", help="MAT: instrument clock zone (default fixed EST)")
    export.add_argument("--dst-fold", type=int, choices=[0, 1], help="MAT: ambiguous DST hour, earlier/later")
    for command in (inspect, export):
        command.add_argument("--recover-incomplete", action="store_true", help="Zero-fill short TRC tails")
        command.add_argument("--expected-sweeps", type=int, help="Recovery: explicit final count when no RPX declares it")
    plot = sub.add_parser("plot", help="View a selected recording section as a Matplotlib waterfall")
    from .spectrogram import add_arguments, run
    add_arguments(plot)
    args = parser.parse_args(argv)
    try:
        if args.command == "gui":
            from .gui import main as gui_main
            return gui_main()
        if args.command == "plot":
            return run(args)
        if args.command == "inspect":
            result = inspect_path(args.path, recover_incomplete=args.recover_incomplete, expected_sweeps=args.expected_sweeps)
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0 if result["supported"] else 2
        rec = FieldFoxRecording.open(args.path, recover_incomplete=args.recover_incomplete, expected_sweeps=args.expected_sweeps)
        if args.format == "mat":
            rec.to_mat(args.output, chunk_sweeps=args.chunk_sweeps, max_part_mib=args.max_part_mib,
                       source_timezone=args.source_timezone, dst_fold=args.dst_fold)
        else:
            getattr(rec, f"to_{args.format}")(args.output)
        print(f"Exported {len(rec)} sweeps, {rec.states[0].points} points, {rec.states[0].trace_count} trace(s) to {args.output}")
        return 0
    except (RecordingError, OSError, ValueError) as error:
        print(f"fieldfox-recording: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
