"""Local Spark environment setup, shared by every job in this package.

PySpark launches a JVM subprocess and needs JAVA_HOME pointed at a Spark-compatible
JDK. Homebrew's default `openjdk` on this machine is a version newer than Spark
currently supports, so we pin to the `openjdk@17` keg explicitly rather than relying
on whatever `java` resolves to on PATH.
"""

import os
from pathlib import Path

_BREW_JDK17_HOME = "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"


def ensure_java_home() -> None:
    """Point JAVA_HOME at a Spark-compatible JDK, unless already set.

    Only knows about the Homebrew-on-Apple-Silicon install path used in local dev.
    The containerized deploy target (Section 11) will bundle its own JDK and won't
    go through this function at all.
    """
    if "JAVA_HOME" in os.environ:
        return
    if not Path(_BREW_JDK17_HOME).exists():
        raise RuntimeError(
            "JAVA_HOME is not set and the expected Homebrew openjdk@17 install "
            f"was not found at {_BREW_JDK17_HOME}. Install it with "
            "`brew install openjdk@17`, or set JAVA_HOME yourself."
        )
    os.environ["JAVA_HOME"] = _BREW_JDK17_HOME
