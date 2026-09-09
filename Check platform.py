"""
check_platform.py
================
Run this FIRST on any new machine, before anything else in this
project. Same spirit as your own chain project's startup.py preflight
— checks what's actually true about this environment and tells you
exactly what to fix, rather than letting you hit a cryptic error five
files deep.

    python3 check_platform.py

WHAT THIS CAN AND CAN'T PROMISE
------------------------------------
This has been run for real on Linux and (via a real error we hit and
fixed together) Windows. It has NOT been run for real on macOS or
Android — those checks are written from documented, correct behavior
of Python/pip/platform detection, but I can't personally verify them
without that hardware. If something here is wrong for your specific
Mac or Android/Termux setup, that's real information — tell me the
exact error and I'll fix this file the same way the Ruby client got
fixed after a real error surfaced.
"""

from __future__ import annotations
import importlib.util
import platform
import sys


MIN_PYTHON = (3, 10)   # this codebase uses `str | None` union syntax throughout

REQUIRED = {
    "cryptography": "crypto_layer.py (Ed25519/X25519/AES-GCM) — required for network_os.py",
}
OPTIONAL = {
    "matplotlib": "node_view_visualizer.py's charts",
    "sklearn": "corpus_vector_store.py's semantic search (package name: scikit-learn)",
    "requests": "research_video_generator.py's Runway polling loop",
    "openai": "research_art_generator.py's image generation",
    "anthropic": "research_summarizer.py's LLM summaries",
}


def check_python_version() -> list[str]:
    problems = []
    if sys.version_info < MIN_PYTHON:
        problems.append(
            f"Python {sys.version_info.major}.{sys.version_info.minor} found, "
            f"but this codebase needs {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ "
            f"(it uses `str | None` union-type syntax throughout, which is a "
            f"syntax error on older Python). Install a newer Python — on macOS, "
            f"`brew install python@3.12`; on Termux, `pkg install python`."
        )
    return problems


def check_dependencies() -> tuple[list[str], list[str]]:
    missing_required, missing_optional = [], []
    for pkg, used_by in REQUIRED.items():
        if importlib.util.find_spec(pkg) is None:
            missing_required.append(f"  pip install {pkg}   # needed for {used_by}")
    for pkg, used_by in OPTIONAL.items():
        import_name = "sklearn" if pkg == "sklearn" else pkg
        pip_name = "scikit-learn" if pkg == "sklearn" else pkg
        if importlib.util.find_spec(import_name) is None:
            missing_optional.append(f"  pip install {pip_name}   # only needed for {used_by}")
    return missing_required, missing_optional


def detect_platform() -> dict:
    system = platform.system()   # 'Linux', 'Darwin' (macOS), 'Windows'
    is_termux = system == "Linux" and "com.termux" in sys.prefix
    is_android_non_termux = system == "Linux" and "ANDROID_ROOT" in __import__("os").environ and not is_termux

    return {
        "system": system,
        "machine": platform.machine(),
        "is_macos": system == "Darwin",
        "is_windows": system == "Windows",
        "is_termux": is_termux,
        "is_android_non_termux": is_android_non_termux,
        "python_impl": platform.python_implementation(),
    }


def main():
    print("=== Platform preflight check ===\n")

    info = detect_platform()
    print(f"OS: {info['system']} ({info['machine']})")
    print(f"Python: {platform.python_version()} ({info['python_impl']})")
    if info["is_termux"]:
        print("Detected: running under Termux on Android")
    elif info["is_android_non_termux"]:
        print("Detected: Android, but NOT Termux — see PLATFORMS.md, this likely won't work as-is")
    print()

    problems = check_python_version()
    missing_required, missing_optional = check_dependencies()

    if not problems and not missing_required:
        print("✅ Core requirements met — network_os.py and digital_dna.py should run.")
    else:
        print("❌ Issues found:\n")
        for p in problems:
            print(f"  {p}\n")
        if missing_required:
            print("Missing REQUIRED packages — run these:")
            for m in missing_required:
                print(m)
            print()

    if missing_optional:
        print("Missing OPTIONAL packages (only needed for specific features):")
        for m in missing_optional:
            print(m)
        print()

    if info["is_android_non_termux"]:
        print("⚠️  You're on Android without Termux. See PLATFORMS.md — you likely need")
        print("    to install Termux from F-Droid first; this won't run in most other")
        print("    Android environments (no pip, no real filesystem access, no sockets")
        print("    the way this code expects).")

    print("\nDone. Re-run this script after installing anything it flagged.")


if __name__ == "__main__":
    main()
