"""Bound PDF decoding in an expendable process rather than the web worker."""
import json
import sys


def main():
    if sys.platform == "linux":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (384 << 20, 384 << 20))
        resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
    try:
        from .engine import read_sources
        sources, warnings = read_sources(json.load(sys.stdin))
        json.dump({"sources": sources, "warnings": warnings}, sys.stdout)
    except ValueError as exc:
        json.dump({"error": str(exc)}, sys.stdout)
    except Exception:
        json.dump({"error": "A document could not be decoded within the reader's resource limits. Try a simpler or smaller file."}, sys.stdout)


if __name__ == "__main__":
    main()
