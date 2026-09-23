"""Run the original coast-team Boundary allocators. Requires Python and a JDK (tested with Java 17).

From the repository root:
    git clone https://github.com/coast-team/replication-benchmarker.git /tmp/replication-benchmarker
    git -C /tmp/replication-benchmarker checkout e3f6f534cd0d37f2c9e7b3288cd6f92b3b4784cc
    python code/logoot/upstream/check_boundary.py /tmp/replication-benchmarker

Set JAVA_HOME if the JDK is not on PATH. The runner stops the intentional infinite
loop in a separate process; BoundaryExamples.java explains why it cannot terminate.
"""

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

UPSTREAM_COMMIT = "e3f6f534cd0d37f2c9e7b3288cd6f92b3b4784cc"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path, help="Path to the coast-team/replication-benchmarker checkout")
    args = parser.parse_args()
    upstream = Path(args.upstream).resolve()
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if revision != UPSTREAM_COMMIT:
        parser.error(f"Expected upstream commit {UPSTREAM_COMMIT}, found {revision}")
    subprocess.run(["git", "-C", str(upstream), "diff", "--exit-code", "HEAD", "--", "src/main/java"], check=True)
    java_home = os.environ.get("JAVA_HOME")
    java = str(Path(java_home) / "bin/java") if java_home else "java"
    javac = str(Path(java_home) / "bin/javac") if java_home else "javac"
    with tempfile.TemporaryDirectory(prefix="logoot-boundary-") as classes:
        subprocess.run(
            [
                javac,
                "-d",
                classes,
                "-sourcepath",
                str(upstream / "src/main/java"),
                str(Path(__file__).with_name("BoundaryExamples.java")),
            ],
            check=True,
            timeout=60,
        )
        command = [java, "-Xmx256m", "-cp", classes, "jbenchmarker.logoot.BoundaryExamples"]
        subprocess.run([*command, "list"], check=True, timeout=30)
        with subprocess.Popen(
            [*command, "boundary"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        ) as process:
            try:
                output, _ = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate()
                print(output, end="")
                if "CALLING_NONTERMINATING_ALLOCATION" not in output:
                    raise RuntimeError("Timed out before reaching the demonstrated infinite loop") from None
                print("Stopped the upstream allocation; the negative recurrence above establishes nontermination.")
            else:
                print(output, end="")
                raise RuntimeError(
                    f"Expected the demonstrated infinite loop, but Java exited with {process.returncode}"
                )


if __name__ == "__main__":
    main()
