# PLATFORMS.md — running this on different machines

Run `python3 check_platform.py` first, always. It tells you exactly
what's missing on your specific machine, rather than you guessing
from a cryptic error five files deep.

## Confidence key

- ✅ **Confirmed** — actually run, on real hardware, in this project
- 🟡 **Expected** — should work, based on how Python/the dependencies
  are documented to behave, but not personally verified
- ⚠️ **Needs a different approach** — the normal instructions won't
  just work here

---

## Linux ✅ Confirmed

Everything in this project was built and tested here directly.
`python3 check_platform.py`, install what it flags, run.

## Windows ✅ Confirmed (with a real fix along the way)

Confirmed working once all `.py` files are present in one folder and
`pip install cryptography` (plus whichever optional packages
`check_platform.py` flags) has been run. The specific real error we
hit and fixed: `growing_research_agent.py` failing with
`ModuleNotFoundError: No module named 'crypto_layer'` — not a Windows
bug, just a missing-file problem, since `network_os.py` depends on
`crypto_layer.py` existing in the same folder. `check_platform.py`
won't catch a *missing file* (only missing *packages*) — for that,
`dir *.py` and compare against the full file list from this project.

## macOS 🟡 Expected, not personally verified

Should work the same as Linux/Windows:

```
python3 check_platform.py
pip install cryptography matplotlib scikit-learn requests openai anthropic
python3 growing_research_agent.py
```

**One real, specific thing to check first**: macOS sometimes ships an
old system Python (2.x historically, or an old 3.x). Run
`python3 --version` — this codebase needs 3.10+ (it uses `str | None`
union-type syntax, a hard syntax error on older Python). If your
system Python is too old: `brew install python@3.12`, then use
`python3.12` explicitly, or make it your default via your shell
profile.

If something breaks here, it's genuinely useful information — send me
the exact error, the same way the Ruby client's real API mismatches
got fixed after actually running it.

## Android — ⚠️ needs Termux, won't work as a normal app

Android doesn't give you a terminal, `pip`, or a JVM the way a
desktop OS does. Two real paths, not the same thing:

### Termux (the realistic path)

[Termux](https://f-droid.org/packages/com.termux/) — get it from
F-Droid, **not** the Play Store version (outdated/deprecated there).
Once installed, it's a real Linux-like environment:

```
pkg update
pkg install python
pip install cryptography matplotlib scikit-learn requests openai anthropic
python check_platform.py
```

`check_platform.py` detects Termux specifically (checks for
`com.termux` in `sys.prefix`) and will tell you if it thinks you're
in a real Termux environment vs. something else.

**Known Termux-specific limitations, not personally tested**:
- `matplotlib` can be finicky to install on Termux (may need
  `pkg install matplotlib` instead of `pip install matplotlib`, since
  some packages need Termux's own build rather than a generic pip
  wheel that assumes glibc)
- Background processes (the autonomous `interval_s` loops in
  `growing_research_agent.py`) may get killed by Android's battery
  optimization when Termux isn't in the foreground — you may need to
  disable battery optimization for Termux specifically in Android
  settings for long-running agents to actually keep running

### A native Android app — not what this project currently is

Building an actual installable Android app (Kotlin/Java via Android
Studio, or Chaquopy to embed Python in a native app) is a
fundamentally different, much larger project — different crypto APIs
(Android Keystore rather than plain `javax.crypto`), different
networking permissions model, a real app-signing/distribution
process. Nothing in this repo does that today. If that's genuinely
what you want (a real installable app, not "Python running in a
terminal app"), that's worth discussing as its own scoped project
rather than assumed to fall out of what exists here.

## Other JVM/language clients on non-Linux platforms

- `JavaInteropClient.java` — 🟡 expected to work anywhere a JDK 15+ is
  installed (Mac, Windows all ship real JDK installers). Won't run
  under Android's ART runtime without real adaptation (different
  crypto provider setup) — not attempted.
- `interop_client.go` — 🟡 expected to work anywhere the Go toolchain
  installs, which includes cross-compiling *to* Android via
  `GOOS=android`, but that's a real additional step not covered here.
- `interop_client.cpp` / `CMakeLists.txt` — 🟡 expected to work
  anywhere OpenSSL dev headers + a C++17 compiler are available (Mac:
  Xcode Command Line Tools + `brew install openssl`; Windows: needs
  vcpkg or similar for OpenSSL, more setup friction than Mac/Linux).
- `interop_client.rb` — 🟡 expected to work anywhere Ruby + its
  OpenSSL binding are available (Mac: `brew install ruby`).
