# Allows to publish coverage info for PR diffs in github. For example of how to add to project,
# see https://github.com/nvnv/betmaster/pull/14596
import os
import subprocess
import sys
import time
import traceback
import typing
from threading import Thread
from typing import Literal, Any, cast

from github import Github
from github.PullRequest import PullRequest


def run_tests_with_coverage() -> str:
    try:
        subprocess.run(
            "pytest --cov=rozert_pay_shared --cov-report=xml --cov-report=html tests/",
            check=True,
            shell=True,
        )

        return "coverage.xml"
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при запуске тестов: {e}")  # noqa: T201
        sys.exit(1)


def get_coverage_report(coverage_file: str) -> str:
    """Генерирует отчет о покрытии измененного кода используя diff-cover"""
    base_branch = os.environ.get("BASE_BRANCH", "origin/develop")
    try:
        subprocess.run(
            [
                "diff-cover",
                coverage_file,
                f"--compare-branch={base_branch}",  # сравниваем с main веткой
                "--markdown-report=report.md",  # сохраняем результат в JSON
            ],
            check=True,
        )

        with open("report.md") as f:
            return f.read()
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        print(  # noqa: T201
            f"Ошибка при генерации отчета diff-cover: {e}", file=sys.stderr
        )  # noqa: T201
        sys.exit(1)


def find_and_delete_existing_comment(pr: PullRequest, marker: str) -> None:
    comments = pr.get_issue_comments()
    for comment in comments:
        if marker in comment.body:
            comment.delete()
            print("Previous coverage comment deleted")  # noqa: T201


def update_or_create_comment(pr_number: int, comment_body: str, comment_marker: str) -> None:
    try:
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise ValueError("GITHUB_TOKEN не установлен")

        repo_name = os.getenv("GITHUB_REPOSITORY")
        if not repo_name:
            raise ValueError("GITHUB_REPOSITORY не установлен")

        gh = Github(github_token)
        repo = gh.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        find_and_delete_existing_comment(pr, comment_marker)

        if "No lines with coverage information in this diff" not in comment_body:
            pr.create_issue_comment(comment_body)
            print("New coverage comment created successfully")  # noqa: T201
        else:
            print("No coverage information in this diff")  # noqa: T201

    except Exception as e:
        print(f"Error updating/creating comment: {e}")  # noqa: T201
        sys.exit(1)


def run(project_name: str) -> None:
    coverage_file = "coverage.xml"

    marker = f"# Coverage report for {project_name}"
    comment = get_coverage_report(coverage_file).replace(
        "# Diff Coverage", marker
    )

    # Some modifications in comment: add expanding for coverage details
    modified = []
    for line in comment.split("\n"):
        modified.append(line)
        if "**Coverage**" in line:
            print("FOUND LINE")
            modified.append("<details>")
            modified.append("<summary>**Coverage Details (Expand to see)**</summary>")
    modified.append("</details>")

    comment = "\n".join(modified)
    print(f"Generated comment: \n{comment}")  # noqa: T201

    pr_number = os.getenv("GITHUB_REF_NAME", "").replace("/merge", "")
    if not pr_number:
        raise RuntimeError("GITHUB_REF_NAME не установлен")  # noqa: T201

    update_or_create_comment(int(pr_number), comment, comment_marker=marker)


def run_several_commands(
    *cmds: str,
    timeout: int = 300,
) -> typing.Union[list[str], None]:
    # Returns list of failed commands if any
    processes = []

    for cmd in cmds:
        t = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        processes.append(t)

    start = time.time()

    stdout_lines: list[list[str]] = [[] for _ in range(len(processes))]
    stderr_lines: list[list[str]] = [[] for _ in range(len(processes))]

    def read_stream(process: subprocess.Popen[Any], lines: list[str], stream: Literal['stdout', 'stderr']) -> None:
        stream_buf = {
            'stdout': process.stdout,
            'stderr': process.stderr,
        }[stream]

        try:
            for line in cast(Any, stream_buf):
                sys.stderr.write(line)
                lines.append(line)
                sys.stderr.flush()
        except Exception:
            traceback.print_exc()

    for i, pr in enumerate(processes):
        thread = Thread(target=read_stream, args=(pr, stdout_lines[i], 'stdout'))
        thread.start()

        thread = Thread(target=read_stream, args=(pr, stderr_lines[i], 'stderr'))
        thread.start()

    failed_commands = []
    for i, process in enumerate(processes):
        try:
            process.wait()
        except KeyboardInterrupt:
            print(f"Killed process {cmds[i]}")
            process.terminate()

        if process.returncode:
            print(f"↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓ COMMAND {cmds[i]} FAILED with status {process.returncode} ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓")
            print(f"STDOUT:\n", "".join(stdout_lines[i]))
            print(f"STDERR:\n", "".join(stderr_lines[i]))
            print(f"↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑ COMMAND {cmds[i]} FAILED status {process.returncode} ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑")
            failed_commands.append(cmds[i])

    if failed_commands:
        print(f"========= Failed commands: =========")
        for cmd in failed_commands:
            print(cmd)

        return failed_commands
    return None


def run_commands_and_diff_cover(service: str, cmds: list[str]) -> None:
    failed_commands: list[str] = []
    try:
        failed_commands = run_several_commands(*cmds) or []
    except Exception as e:
        failed_commands.append(f"run_several_commands error: {e}")

    sys.stdout.flush()
    sys.stderr.flush()

    try:
        run(project_name=service)
    except Exception as e:
        # TODO: comment to github?
        print(f"CANT RUN DIFF COVER! {e}")

    sys.stdout.flush()
    sys.stderr.flush()

    if failed_commands:
        print("!!! TESTS FAILED !!!", file=sys.stderr)
        for cmd in failed_commands:
            print("\t", cmd, file=sys.stderr)
        sys.exit(1)
    else:
        print("TESTS OK", file=sys.stderr)
