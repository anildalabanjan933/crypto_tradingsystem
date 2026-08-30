#!/usr/bin/env python3
"""One-shot dashboard performance profiler - auto-discovers all tab modules."""
import cProfile, pstats, io, time, importlib, inspect, os, sys, glob

sys.path.insert(0, ".")

tab_files = sorted(glob.glob("dashboard/*tab*.py"))
if not tab_files:
    print("No tab files found under dashboard/*tab*.py")
    sys.exit(0)

for path in tab_files:
    modname = "dashboard." + os.path.basename(path)[:-3]
    print(f"\n{'='*70}\n{modname}  ({path})\n{'='*70}")
    t0i = time.time()
    try:
        mod = importlib.import_module(modname)
    except Exception as e:
        print(f"  IMPORT FAILED: {e}")
        continue
    print(f"  import time: {time.time()-t0i:.3f}s")

    funcs = [f for name, f in inspect.getmembers(mod, inspect.isfunction)
             if f.__module__ == modname]
    if not funcs:
        print("  No top-level functions found.")
        continue

    for fn in funcs:
        sig = inspect.signature(fn)
        required = [p for p in sig.parameters.values()
                    if p.default is inspect.Parameter.empty
                    and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        if required:
            continue
        pr = cProfile.Profile()
        t0 = time.time()
        try:
            pr.enable()
            fn()
            pr.disable()
        except Exception as e:
            print(f"  {fn.__name__}(): SKIPPED/ERROR -> {type(e).__name__}: {e}")
            continue
        elapsed = time.time() - t0
        flag = "  <-- SLOW" if elapsed > 0.2 else ""
        print(f"  {fn.__name__}(): {elapsed:.3f}s{flag}")
        if elapsed > 0.2:
            s = io.StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
            ps.print_stats(8)
            print(s.getvalue())

print("\nDONE. Functions marked '<-- SLOW' (>0.2s) are the fix targets.")
