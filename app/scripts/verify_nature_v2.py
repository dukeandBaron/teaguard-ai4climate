"""Compatibility command in V3; delegates to current engineering acceptance."""

from verify_engineering import verify

if __name__ == "__main__":
    raise SystemExit(verify())
