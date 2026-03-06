from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import re
import threading
import subprocess
import sys
import ast
import shutil
import importlib.util
import importlib
from importlib import metadata
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ntf.assertions import AssertionEngine
from ntf.config import load_config
from ntf.executor import ExecuteError, RequestExecutor
from ntf.extract import ExtractStore
from ntf.http import RequestsTransport
from ntf.allure_results import AllureResultsWriter, now_ms
from ntf.plugins import plugin_counts, reporter_plugins, transport_plugins
from ntf.renderer import RenderContext, build_renderer, clear_external_functions, set_external_functions
from ntf.integrations.dingding import DingDingBot
from ntf.yaml_case import load_yaml_suite

import pytest

LOG = logging.getLogger("ntf")


def main() -> None:
    argv = sys.argv[1:]
    if "..." in argv and ("run-yaml" in argv or "migrate" in argv):
        print("Detected '...' placeholder in command. Please remove it and provide the real arguments.")
        print("Example:")
        print("  ntf run-yaml --config configs/default.yaml --cases tests/data --report report/run-yaml.json")
        raise SystemExit(2)

    parser = argparse.ArgumentParser(prog="ntf")
    parser.add_argument("--version", action="store_true", help="Print ntf and Python version.")
    parser.add_argument("--log-level", default="INFO", help="Logging level: DEBUG/INFO/WARNING/ERROR.")
    parser.add_argument("--log-file", default=None, help="Write logs to file.")
    sub = parser.add_subparsers(dest="cmd")

    run = sub.add_parser("run")
    run.add_argument("--config", default=str(Path("configs/default.yaml")))
    run.add_argument("--profile", default=None, help="Config profile name in config YAML.")
    run.add_argument("--allure-dir", default=None, help="If set, pass --alluredir to pytest.")
    run.add_argument(
        "--debugtalk",
        default=None,
        help="Path to a python file providing DebugTalk-style functions for ${func()} rendering (pytest mode).",
    )
    run.add_argument(
        "--allure-clean",
        action="store_true",
        help="If set, pass --clean-alluredir (requires --allure-dir).",
    )

    run_yaml = sub.add_parser("run-yaml")
    run_yaml.add_argument("--config", default=str(Path("configs/default.yaml")))
    run_yaml.add_argument("--profile", default=None, help="Config profile name in config YAML.")
    run_yaml.add_argument(
        "--allure-dir",
        default=None,
        help="If set, write Allure results to this directory (without pytest).",
    )
    run_yaml.add_argument(
        "--cases",
        required=True,
        nargs="+",
        help="YAML case file/dir/glob. e.g. tests/data/*.yaml",
    )
    run_yaml.add_argument(
        "--continue-on-fail",
        action="store_true",
        help="Continue executing remaining cases even if one fails.",
    )
    run_yaml.add_argument(
        "--vars",
        nargs="*",
        default=[],
        help="Preload ExtractStore values. Format: key=value (repeatable).",
    )
    run_yaml.add_argument(
        "--include-file",
        default=None,
        help="Regex: only run YAML files whose path matches.",
    )
    run_yaml.add_argument(
        "--exclude-file",
        default=None,
        help="Regex: skip YAML files whose path matches.",
    )
    run_yaml.add_argument(
        "--include-case",
        default=None,
        help="Regex: only run cases whose case_name matches.",
    )
    run_yaml.add_argument(
        "--exclude-case",
        default=None,
        help="Regex: skip cases whose case_name matches.",
    )
    run_yaml.add_argument(
        "--report",
        default=None,
        help="Write JSON report to this path (failures + summary).",
    )
    run_yaml.add_argument(
        "--mock-login",
        action="store_true",
        help="Call mock_server /dar/user/login before running cases and preload returned token into ExtractStore.",
    )
    run_yaml.add_argument(
        "--mock-user",
        default="test01",
        help="mock_server login username (form field: user_name).",
    )
    run_yaml.add_argument(
        "--mock-pass",
        default="admin123",
        help="mock_server login password (form field: passwd).",
    )
    run_yaml.add_argument(
        "--debugtalk",
        default=None,
        help="Path to a python file providing DebugTalk-style functions for ${func()} rendering.",
    )
    run_yaml.add_argument("--retry", type=int, default=0, help="Retry times per case.")
    run_yaml.add_argument(
        "--retry-on",
        default="request,timeout,5xx",
        help="Comma separated retry conditions: request,validation,extract,timeout,5xx,exception",
    )
    run_yaml.add_argument("--workers", type=int, default=1, help="Worker threads for independent cases.")
    run_yaml.add_argument("--timeout-s", type=float, default=None, help="Override global timeout seconds.")
    run_yaml.add_argument(
        "--transport",
        default=None,
        help="Use named transport plugin from entry-points group ntf.transports.",
    )
    run_yaml.add_argument(
        "--reporter",
        default=None,
        help="Use named reporter plugin from entry-points group ntf.reporters.",
    )
    run_yaml.add_argument(
        "--renderer",
        default=None,
        help="Use named renderer plugin from entry-points group ntf.renderers.",
    )
    run_yaml.add_argument("--dingding-enabled", action="store_true", help="Send run-yaml summary to DingDing.")
    run_yaml.add_argument("--dingding-webhook", default=None, help="DingDing robot webhook URL.")
    run_yaml.add_argument("--dingding-secret", default=None, help="DingDing robot secret.")
    run_yaml.add_argument("--dingding-at-all", action="store_true", help="Mention all in DingDing message.")

    allure = sub.add_parser("allure")
    allure_sub = allure.add_subparsers(dest="allure_cmd", required=True)
    allure_serve = allure_sub.add_parser("serve")
    allure_serve.add_argument("--dir", dest="allure_dir", default="report/allure-results")
    allure_stop = allure_sub.add_parser("stop")
    allure_stop.add_argument("--pid", required=True, type=int, help="PID of the running allure process.")
    allure_generate = allure_sub.add_parser("generate")
    allure_generate.add_argument("--results", dest="results_dir", default="report/allure-results")
    allure_generate.add_argument("--out", dest="out_dir", default="report/allure-report")
    allure_generate.add_argument("--clean", action="store_true")

    mock = sub.add_parser("mock")
    mock_sub = mock.add_subparsers(dest="mock_cmd", required=True)
    mock_start = mock_sub.add_parser("start")
    mock_start.add_argument(
        "--port",
        type=int,
        default=8787,
        help="Port to use (must match mock_server implementation).",
    )
    mock_sub.add_parser("status")
    mock_sub.add_parser("stop")

    migrate = sub.add_parser("migrate")
    migrate_sub = migrate.add_subparsers(dest="migrate_cmd", required=True)
    mig_check = migrate_sub.add_parser("check")
    mig_check.add_argument("--path", required=True, help="Old testcase directory or YAML file.")
    mig_check.add_argument("--out", default=None, help="Write JSON report to this path.")

    mig_convert = migrate_sub.add_parser("convert")
    mig_convert.add_argument("--src", required=True, help="Old testcase directory.")
    mig_convert.add_argument("--dst", required=True, help="Destination directory to copy YAML files into.")
    mig_convert.add_argument("--index", default=None, help="Write index JSON to this path.")

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--config", default=str(Path("configs/default.yaml")))
    doctor.add_argument("--profile", default=None)

    ns, unknown_args = parser.parse_known_args()
    _setup_logging(ns.log_level, ns.log_file)

    if ns.version:
        print(_version_text())
        if ns.cmd is None:
            raise SystemExit(0)

    if ns.cmd is None:
        parser.print_help()
        raise SystemExit(2)

    if ns.cmd == "run":
        _ = load_config(ns.config, profile=ns.profile)
        # Forward anything after `--` to pytest. Using parse_known_args keeps compatibility
        # with the common pattern: `ntf run ... -- -k xxx`.
        args = []
        if ns.debugtalk:
            functions = _load_debugtalk(ns.debugtalk)
            set_external_functions(functions)
        if ns.allure_dir:
            if importlib.util.find_spec("allure_pytest") is None:
                print("allure-pytest plugin not installed, cannot use --allure-dir.")
                print("Install with: pip install allure-pytest")
                raise SystemExit(1)
            args.append(f"--alluredir={ns.allure_dir}")
            if ns.allure_clean:
                args.append("--clean-alluredir")
        if unknown_args:
            args.extend(unknown_args)
        try:
            raise SystemExit(pytest.main(args))
        finally:
            # Avoid leaking DebugTalk functions to other test runs.
            clear_external_functions()

    if ns.cmd == "run-yaml":
        if unknown_args:
            raise SystemExit(f"Unknown arguments for run-yaml: {unknown_args}")
        cfg = load_config(ns.config, profile=ns.profile)

        include_file_re = re.compile(ns.include_file) if ns.include_file else None
        exclude_file_re = re.compile(ns.exclude_file) if ns.exclude_file else None
        include_case_re = re.compile(ns.include_case) if ns.include_case else None
        exclude_case_re = re.compile(ns.exclude_case) if ns.exclude_case else None

        files: list[str] = []
        for p in ns.cases:
            # glob
            if any(ch in p for ch in ["*", "?", "["]):
                files.extend(glob.glob(p, recursive=True))
                continue

            pp = Path(p)
            if pp.is_dir():
                files.extend([str(x) for x in pp.rglob("*.yaml")])
                files.extend([str(x) for x in pp.rglob("*.yml")])
                continue

            files.append(str(pp))

        # 去重 + 保持顺序
        seen: set[str] = set()
        uniq_files: list[str] = []
        for f in files:
            af = os.path.abspath(f)
            if af in seen:
                continue
            seen.add(af)
            uniq_files.append(af)

        if not uniq_files:
            raise SystemExit("No YAML files matched.")

        # skip non-testcase yaml files by convention
        uniq_files = [f for f in uniq_files if Path(f).name.lower() not in {"extract.yaml", "extract.yml"}]
        if not uniq_files:
            raise SystemExit("No YAML files matched after skipping non-testcase files.")

        # file filters
        filtered_files: list[str] = []
        for f in uniq_files:
            if include_file_re and not include_file_re.search(f):
                continue
            if exclude_file_re and exclude_file_re.search(f):
                continue
            filtered_files.append(f)

        uniq_files = sorted(filtered_files)
        if not uniq_files:
            raise SystemExit("No YAML files matched after filters.")

        store = ExtractStore()

        functions: Any | None = None
        if ns.debugtalk:
            functions = _load_debugtalk(ns.debugtalk)

        # preload vars
        for item in ns.vars:
            if "=" not in item:
                raise SystemExit(f"Invalid --vars item: {item} (expected key=value)")
            k, v = item.split("=", 1)
            store.set(k, v)

        transport = _build_transport(ns.transport, cfg)
        engine = AssertionEngine()
        timeout_s = ns.timeout_s if ns.timeout_s is not None else cfg.timeout_s
        executor = RequestExecutor(
            base_url=cfg.base_url,
            timeout_s=timeout_s,
            transport=transport,
            extract_store=store,
            assertion_engine=engine,
            functions=functions,
            sign_config=cfg.sign,
            renderer_name=ns.renderer,
        )

        if ns.mock_login:
            token = _mock_login(transport, cfg.base_url, user_name=ns.mock_user, passwd=ns.mock_pass)
            store.set("token", token)

        total = 0
        passed = 0
        failed = 0
        skipped = 0

        failures: list[dict[str, Any]] = []

        allure_writer: AllureResultsWriter | None = None
        if ns.allure_dir:
            allure_writer = AllureResultsWriter(ns.allure_dir)

        case_entries: list[dict[str, Any]] = []
        for f in uniq_files:
            suite = load_yaml_suite(f)
            for base, cases in suite:
                cookies = _parse_cookies(base.cookies, store, functions=functions, renderer_name=ns.renderer)
                for tc in cases:
                    if include_case_re and not include_case_re.search(tc.case_name):
                        continue
                    if exclude_case_re and exclude_case_re.search(tc.case_name):
                        continue
                    case_id = f"{f}::{tc.case_name}"
                    case_entries.append(
                        {
                            "id": case_id,
                            "file": f,
                            "base": base,
                            "tc": tc,
                            "cookies": cookies,
                            "depends": tc.depends_on or [],
                        }
                    )

        if not case_entries:
            raise SystemExit("No cases matched after filters.")

        retry_on = {x.strip().lower() for x in str(ns.retry_on).split(",") if x.strip()}
        ordered_entries = _order_case_entries(case_entries)
        total = len(ordered_entries)
        status_by_id: dict[str, str] = {}
        allure_lock = threading.Lock()

        can_parallel = ns.workers > 1 and _can_parallelize(ordered_entries)
        if ns.workers > 1 and not can_parallel:
            print("workers>1 requested, but current case graph needs ordered/shared execution; fallback to sequential.")

        def _record_failure(file_path: str, case_name: str, message: str) -> None:
            failures.append({"file": file_path, "case_name": case_name, "error": message})

        if can_parallel:
            with ThreadPoolExecutor(max_workers=max(1, ns.workers)) as pool:
                future_map = {
                    pool.submit(
                        _run_case_with_retry,
                        executor=executor,
                        base=e["base"],
                        tc=e["tc"],
                        cookies=e["cookies"],
                        retry=max(0, int(e["tc"].retry if e["tc"].retry is not None else ns.retry)),
                        retry_on=retry_on,
                    ): e
                    for e in ordered_entries
                }
                for fut in as_completed(future_map):
                    e = future_map[fut]
                    file_path = e["file"]
                    tc = e["tc"]
                    start_ms, stop_ms, ok, result, err = fut.result()
                    if ok:
                        LOG.info("case passed file=%s case=%s", Path(file_path).name, tc.case_name)
                        passed += 1
                        status_by_id[e["id"]] = "passed"
                        if allure_writer is not None and result is not None:
                            with allure_lock:
                                _write_allure_for_success(allure_writer, file_path, e["base"].api_name, tc.case_name, start_ms, stop_ms, result)
                        continue

                    failed += 1
                    status_by_id[e["id"]] = "failed"
                    msg = _err_message(err)
                    print(f"[FAIL] {Path(file_path).name} :: {tc.case_name} -> {msg}")
                    LOG.error("case failed file=%s case=%s error=%s", Path(file_path).name, tc.case_name, msg)
                    _record_failure(file_path, tc.case_name, msg)
                    if allure_writer is not None:
                        with allure_lock:
                            _write_allure_for_failure(allure_writer, file_path, e["base"].api_name, tc.case_name, start_ms, stop_ms, err)
                    if not ns.continue_on_fail:
                        break
        else:
            for e in ordered_entries:
                file_path = e["file"]
                tc = e["tc"]
                LOG.info("case start file=%s case=%s", Path(file_path).name, tc.case_name)
                dep_ids = e.get("dep_ids", [])
                if dep_ids and any(status_by_id.get(d) != "passed" for d in dep_ids):
                    skipped += 1
                    status_by_id[e["id"]] = "skipped"
                    msg = f"dependency not passed: {dep_ids}"
                    print(f"[SKIP] {Path(file_path).name} :: {tc.case_name} -> {msg}")
                    LOG.warning("case skipped file=%s case=%s reason=%s", Path(file_path).name, tc.case_name, msg)
                    _record_failure(file_path, tc.case_name, msg)
                    if allure_writer is not None:
                        _write_allure_for_skipped(allure_writer, file_path, e["base"].api_name, tc.case_name, msg)
                    continue

                start_ms = now_ms()
                try:
                    _run_hooks(
                        tc.setup_hooks,
                        store,
                        functions=functions,
                        renderer_name=ns.renderer,
                        phase="setup_hooks",
                        case_name=tc.case_name,
                    )
                    s_ms, stop_ms, ok, result, err = _run_case_with_retry(
                        executor=executor,
                        base=e["base"],
                        tc=tc,
                        cookies=e["cookies"],
                        retry=max(0, int(tc.retry if tc.retry is not None else ns.retry)),
                        retry_on=retry_on,
                    )
                    start_ms = s_ms
                    if ok:
                        passed += 1
                        status_by_id[e["id"]] = "passed"
                        LOG.info("case passed file=%s case=%s", Path(file_path).name, tc.case_name)
                        if allure_writer is not None and result is not None:
                            _write_allure_for_success(
                                allure_writer, file_path, e["base"].api_name, tc.case_name, start_ms, stop_ms, result
                            )
                    else:
                        failed += 1
                        status_by_id[e["id"]] = "failed"
                        msg = _err_message(err)
                        print(f"[FAIL] {Path(file_path).name} :: {tc.case_name} -> {msg}")
                        LOG.error("case failed file=%s case=%s error=%s", Path(file_path).name, tc.case_name, msg)
                        _record_failure(file_path, tc.case_name, msg)
                        if allure_writer is not None:
                            _write_allure_for_failure(
                                allure_writer, file_path, e["base"].api_name, tc.case_name, start_ms, stop_ms, err
                            )
                        if not ns.continue_on_fail:
                            raise SystemExit(1)
                except Exception as hook_err:
                    stop_ms = now_ms()
                    failed += 1
                    status_by_id[e["id"]] = "failed"
                    msg = str(hook_err)
                    print(f"[FAIL] {Path(file_path).name} :: {tc.case_name} -> {msg}")
                    LOG.error("case failed file=%s case=%s error=%s", Path(file_path).name, tc.case_name, msg)
                    _record_failure(file_path, tc.case_name, msg)
                    if allure_writer is not None:
                        _write_allure_for_failure(
                            allure_writer, file_path, e["base"].api_name, tc.case_name, start_ms, stop_ms, hook_err
                        )
                    if not ns.continue_on_fail:
                        raise SystemExit(1)
                finally:
                    try:
                        _run_hooks(
                            tc.teardown_hooks,
                            store,
                            functions=functions,
                            renderer_name=ns.renderer,
                            phase="teardown_hooks",
                            case_name=tc.case_name,
                        )
                    except Exception as teardown_err:
                        print(f"[WARN] {Path(file_path).name} :: {tc.case_name} teardown error -> {teardown_err}")
                        LOG.warning(
                            "teardown hook error file=%s case=%s error=%s",
                            Path(file_path).name,
                            tc.case_name,
                            teardown_err,
                        )

        summary = {"total": total, "passed": passed, "failed": failed, "skipped": skipped}
        print(f"Summary: total={total} passed={passed} failed={failed} skipped={skipped}")
        LOG.info("run-yaml summary total=%s passed=%s failed=%s skipped=%s", total, passed, failed, skipped)
        _notify_dingding_run_yaml(
            summary=summary,
            failures=failures,
            enabled=ns.dingding_enabled,
            webhook=ns.dingding_webhook,
            secret=ns.dingding_secret,
            at_all=ns.dingding_at_all,
        )
        _dispatch_reporter(ns.reporter, summary=summary, failures=failures)
        if ns.report:
            _write_report(ns.report, summary=summary, failures=failures)
        raise SystemExit(0 if failed == 0 else 1)

    if ns.cmd == "mock":
        if unknown_args:
            raise SystemExit(f"Unknown arguments for mock: {unknown_args}")
        root = Path(__file__).resolve().parent.parent
        pid_path = root / ".ntf" / "mock_server.pid"
        pid_path.parent.mkdir(parents=True, exist_ok=True)

        if ns.mock_cmd == "status":
            pid = _read_pid(pid_path)
            if not pid:
                print("mock_server: stopped")
                raise SystemExit(0)
            if _pid_alive(pid):
                print(f"mock_server: running (pid={pid})")
                raise SystemExit(0)
            print(f"mock_server: stale pid file (pid={pid})")
            raise SystemExit(1)

        if ns.mock_cmd == "stop":
            pid = _read_pid(pid_path)
            if not pid:
                print("mock_server: stopped")
                raise SystemExit(0)
            _terminate_pid(pid)
            try:
                pid_path.unlink(missing_ok=True)
            except Exception:
                pass
            print("mock_server: stopped")
            raise SystemExit(0)

        if ns.mock_cmd == "start":
            pid = _read_pid(pid_path)
            if pid and _pid_alive(pid):
                print(f"mock_server already running (pid={pid})")
                raise SystemExit(0)

            script = root / "mock_server" / "base" / "flask_service.py"
            if not script.exists():
                raise SystemExit(f"mock_server entry not found: {script}")

            missing = _check_mock_deps()
            if missing:
                pkgs = " ".join(missing)
                print("mock_server missing dependencies:")
                for m in missing:
                    print(f"- {m}")
                print(f"Install with: pip install {pkgs}")
                raise SystemExit(1)

            # note: flask_service.py has port hardcoded. '--port' currently only for future extension.
            p = subprocess.Popen(
                [sys.executable, str(script)],
                cwd=str(script.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            pid_path.write_text(str(p.pid), encoding="utf-8")
            print(f"mock_server: started (pid={p.pid})")
            raise SystemExit(0)

    if ns.cmd == "migrate":
        if unknown_args:
            raise SystemExit(f"Unknown arguments for migrate: {unknown_args}")
        if ns.migrate_cmd == "check":
            report = _migrate_check(ns.path)
            if ns.out:
                _write_json(ns.out, report)
            print(
                f"migrate check: files={report['summary']['files']} cases={report['summary']['cases']} issues={report['summary']['issues']}"
            )
            raise SystemExit(0)

        if ns.migrate_cmd == "convert":
            report = _migrate_convert(ns.src, ns.dst)
            if ns.index:
                _write_json(ns.index, report)
            print(
                f"migrate convert: files={report['summary']['files']} copied={report['summary']['copied']} issues={report['summary']['issues']}"
            )
            raise SystemExit(0)

    if ns.cmd == "allure":
        if unknown_args:
            raise SystemExit(f"Unknown arguments for allure: {unknown_args}")
        allure_bin = shutil.which("allure")
        if not allure_bin:
            print("allure CLI not found in PATH.")
            print("Install Allure commandline and ensure 'allure' is available.")
            raise SystemExit(1)

        if ns.allure_cmd == "serve":
            # non-blocking: keep terminal usable
            p = subprocess.Popen(
                [allure_bin, "serve", ns.allure_dir],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            print(f"allure serve started (pid={p.pid}).")
            print("If you need to stop it: ntf allure stop --pid <pid>")
            raise SystemExit(0)

        if ns.allure_cmd == "stop":
            _terminate_pid(ns.pid)
            print(f"allure serve stopped (pid={ns.pid})")
            raise SystemExit(0)

        if ns.allure_cmd == "generate":
            args = [allure_bin, "generate", ns.results_dir, "-o", ns.out_dir]
            if ns.clean:
                args.append("--clean")
            p = subprocess.Popen(args)
            raise SystemExit(p.wait())

    if ns.cmd == "doctor":
        if unknown_args:
            raise SystemExit(f"Unknown arguments for doctor: {unknown_args}")
        checks = _collect_doctor_checks(ns.config, profile=ns.profile)
        _print_doctor_checks(checks)
        failed = [c for c in checks if c["status"] == "FAIL"]
        raise SystemExit(1 if failed else 0)


def _run_hooks(
    hooks: list[Any] | None,
    store: ExtractStore,
    *,
    functions: Any | None,
    renderer_name: str | None,
    phase: str,
    case_name: str,
) -> None:
    if not hooks:
        return
    renderer = build_renderer(RenderContext(extract_store=store), functions=functions, renderer_name=renderer_name)
    for idx, hook in enumerate(hooks):
        try:
            if isinstance(hook, str):
                renderer.render(hook)
                continue
            if isinstance(hook, dict):
                if "set" in hook and isinstance(hook["set"], dict):
                    for k, v in hook["set"].items():
                        store.set(str(k), renderer.render(v))
                    continue
                if "call" in hook:
                    renderer.render(str(hook["call"]))
                    continue
                renderer.render(hook)
                continue
            renderer.render(hook)
        except Exception as e:
            raise RuntimeError(f"{phase} failed at index={idx} case={case_name}: {e}") from e


def _order_case_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not entries:
        return entries

    by_id = {e["id"]: e for e in entries}
    by_stem_case: dict[str, list[str]] = {}
    by_case: dict[str, list[str]] = {}
    for e in entries:
        file_path = str(e["file"])
        case_name = str(e["tc"].case_name)
        stem_key = f"{Path(file_path).stem}::{case_name}"
        by_stem_case.setdefault(stem_key, []).append(e["id"])
        by_case.setdefault(case_name, []).append(e["id"])

    dep_ids_map: dict[str, list[str]] = {}
    for e in entries:
        cur_file = str(e["file"])
        deps: list[str] = []
        for dep in e.get("depends", []):
            dep = str(dep).strip()
            if not dep:
                continue
            if dep in by_id:
                deps.append(dep)
                continue
            if "::" in dep:
                matched = by_stem_case.get(dep)
                if matched and len(matched) == 1:
                    deps.append(matched[0])
                    continue
                matched2 = [x for x in by_id.keys() if x.endswith(f"::{dep.split('::', 1)[1]}") and x.startswith(dep.split("::", 1)[0])]
                if len(matched2) == 1:
                    deps.append(matched2[0])
                    continue
                raise ValueError(f"depends_on unresolved/ambiguous: {dep} (in {cur_file}::{e['tc'].case_name})")

            candidates = by_case.get(dep, [])
            if len(candidates) == 1:
                deps.append(candidates[0])
                continue
            if len(candidates) == 0:
                raise ValueError(f"depends_on missing: {dep} (in {cur_file}::{e['tc'].case_name})")
            raise ValueError(f"depends_on ambiguous: {dep} (in {cur_file}::{e['tc'].case_name})")
        dep_ids_map[e["id"]] = deps

    in_degree: dict[str, int] = {k: 0 for k in by_id.keys()}
    graph: dict[str, list[str]] = {k: [] for k in by_id.keys()}
    for node, deps in dep_ids_map.items():
        for d in deps:
            graph[d].append(node)
            in_degree[node] += 1

    q: list[str] = [k for k, v in in_degree.items() if v == 0]
    ordered_ids: list[str] = []
    while q:
        n = q.pop(0)
        ordered_ids.append(n)
        for nxt in graph[n]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                q.append(nxt)

    if len(ordered_ids) != len(entries):
        cycle_nodes = [k for k, v in in_degree.items() if v > 0]
        raise ValueError(f"depends_on cycle detected: {cycle_nodes}")

    ordered: list[dict[str, Any]] = []
    for node_id in ordered_ids:
        e = dict(by_id[node_id])
        e["dep_ids"] = dep_ids_map[node_id]
        ordered.append(e)
    return ordered


def _can_parallelize(entries: list[dict[str, Any]]) -> bool:
    for e in entries:
        tc = e["tc"]
        if e.get("dep_ids"):
            return False
        if tc.setup_hooks or tc.teardown_hooks:
            return False
        if tc.extract or tc.extract_list:
            return False
    return True


def _run_case_with_retry(
    *,
    executor: RequestExecutor,
    base: Any,
    tc: Any,
    cookies: dict[str, Any] | None,
    retry: int,
    retry_on: set[str],
) -> tuple[int, int, bool, Any | None, BaseException | None]:
    attempt = 0
    start_ms = now_ms()
    while True:
        attempt += 1
        try:
            result = executor.execute(
                method=base.method,
                url=base.url,
                headers=base.header,
                cookies=cookies,
                request_kwargs=tc.request,
                extract=tc.extract,
                extract_list=tc.extract_list,
                validation=tc.validation,
                timeout_s=tc.timeout_s,
            )
            stop_ms = now_ms()
            return start_ms, stop_ms, True, result, None
        except Exception as e:
            stop_ms = now_ms()
            if attempt > (retry + 1):
                return start_ms, stop_ms, False, None, e
            if not _should_retry(e, retry_on):
                return start_ms, stop_ms, False, None, e


def _should_retry(err: BaseException, retry_on: set[str]) -> bool:
    if "exception" in retry_on:
        return True

    if isinstance(err, ExecuteError):
        stage = str(err.stage).lower()
        if stage in retry_on:
            return True
        if "5xx" in retry_on and err.response is not None and int(err.response.status_code) >= 500:
            return True
        if "timeout" in retry_on and _is_timeout_error(err.original):
            return True
        return False

    if "timeout" in retry_on and _is_timeout_error(err):
        return True
    return False


def _is_timeout_error(err: BaseException | None) -> bool:
    if err is None:
        return False
    name = err.__class__.__name__.lower()
    if "timeout" in name:
        return True
    msg = str(err).lower()
    return "timed out" in msg or "timeout" in msg


def _err_message(err: BaseException | None) -> str:
    if err is None:
        return "unknown error"
    if isinstance(err, ExecuteError):
        return str(err.original) if err.original is not None else str(err)
    return str(err)


def _write_allure_for_success(
    writer: AllureResultsWriter,
    file_path: str,
    suite_name: str,
    case_name: str,
    start_ms: int,
    stop_ms: int,
    result: Any,
) -> None:
    req_dump = json.dumps({"meta": {"file": file_path}, "request": result.request}, ensure_ascii=False)
    resp_dump = json.dumps(
        {
            "status_code": result.response.status_code,
            "text": result.response.text,
            "json": result.response.json_data,
        },
        ensure_ascii=False,
    )
    t = result.timings_ms
    steps = [
        {
            "name": "request",
            "status": "passed",
            "stage": "finished",
            "start": t.get("case_start", start_ms),
            "stop": t.get("request_stop", stop_ms),
        },
        {
            "name": "validate",
            "status": "passed",
            "stage": "finished",
            "start": t.get("request_stop", start_ms),
            "stop": t.get("case_stop", stop_ms),
        },
    ]
    writer.write_case_result(
        suite_name=suite_name or Path(file_path).stem,
        case_name=case_name,
        file_path=file_path,
        status="passed",
        start_ms=start_ms,
        stop_ms=stop_ms,
        attachments=[
            ("request", "application/json", req_dump),
            ("response", "application/json", resp_dump),
        ],
        steps=steps,
    )


def _write_allure_for_failure(
    writer: AllureResultsWriter,
    file_path: str,
    suite_name: str,
    case_name: str,
    start_ms: int,
    stop_ms: int,
    err: BaseException | None,
) -> None:
    details = {"message": _err_message(err), "trace": traceback.format_exc()}
    if isinstance(err, ExecuteError):
        req_dump = json.dumps({"meta": {"file": file_path, "stage": err.stage}, "request": err.request}, ensure_ascii=False)
        resp_payload: dict[str, Any] | None = None
        if err.response is not None:
            resp_payload = {
                "status_code": err.response.status_code,
                "text": err.response.text,
                "json": err.response.json_data,
            }
        resp_dump = json.dumps(resp_payload, ensure_ascii=False)
        writer.write_case_result(
            suite_name=suite_name or Path(file_path).stem,
            case_name=case_name,
            file_path=file_path,
            status="failed",
            start_ms=start_ms,
            stop_ms=stop_ms,
            status_details=details,
            attachments=[("request", "application/json", req_dump), ("response", "application/json", resp_dump)],
            steps=[
                {
                    "name": "request",
                    "status": "failed" if err.stage == "request" else "passed",
                    "stage": "finished",
                    "start": start_ms,
                    "stop": stop_ms,
                },
                {
                    "name": "validate",
                    "status": "failed" if err.stage == "validation" else "passed",
                    "stage": "finished",
                    "start": start_ms,
                    "stop": stop_ms,
                },
            ],
        )
        return

    writer.write_case_result(
        suite_name=suite_name or Path(file_path).stem,
        case_name=case_name,
        file_path=file_path,
        status="failed",
        start_ms=start_ms,
        stop_ms=stop_ms,
        status_details=details,
        attachments=[("error", "text/plain", _err_message(err))],
        steps=[
            {
                "name": "run",
                "status": "failed",
                "stage": "finished",
                "start": start_ms,
                "stop": stop_ms,
            }
        ],
    )


def _write_allure_for_skipped(writer: AllureResultsWriter, file_path: str, suite_name: str, case_name: str, reason: str) -> None:
    t = now_ms()
    writer.write_case_result(
        suite_name=suite_name or Path(file_path).stem,
        case_name=case_name,
        file_path=file_path,
        status="skipped",
        start_ms=t,
        stop_ms=t,
        status_details={"message": reason},
        attachments=[("skip", "text/plain", reason)],
    )


def _setup_logging(level: str, log_file: str | None) -> None:
    resolved = str(level or "INFO").upper()
    lv = getattr(logging, resolved, logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        p = Path(log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(p, encoding="utf-8"))
    logging.basicConfig(
        level=lv,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        handlers=handlers,
        force=True,
    )
    LOG.debug("logging initialized level=%s file=%s", resolved, log_file)


def _version_text() -> str:
    try:
        v = metadata.version("PytestOps-framework")
    except Exception:
        v = "unknown"
    return f"ntf {v} (python {sys.version.split()[0]})"


def _collect_doctor_checks(config_path: str, *, profile: str | None) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    add("version", "PASS", _version_text())
    cnt = plugin_counts()
    add(
        "plugins",
        "PASS",
        "assertions={a} functions={f} transports={t} reporters={r} renderers={rr}".format(
            a=cnt["assertions"],
            f=cnt["functions"],
            t=cnt["transports"],
            r=cnt["reporters"],
            rr=cnt.get("renderers", 0),
        ),
    )
    add(
        "python",
        "PASS" if sys.version_info >= (3, 12) else "FAIL",
        f"{sys.version.split()[0]} (requires >=3.12)",
    )

    for pkg in ("pytest", "requests", "yaml", "jsonpath"):
        try:
            importlib.import_module(pkg)
            add(f"dep:{pkg}", "PASS", "installed")
        except Exception as e:
            add(f"dep:{pkg}", "FAIL", f"missing ({e})")

    allure_bin = shutil.which("allure")
    if allure_bin:
        add("allure-cli", "PASS", allure_bin)
    else:
        add("allure-cli", "WARN", "not found in PATH. install Allure commandline if needed.")

    cfg_file = Path(config_path)
    if cfg_file.exists():
        try:
            cfg = load_config(cfg_file, profile=profile)
            add("config", "PASS", f"base_url={cfg.base_url} timeout_s={cfg.timeout_s}")
        except Exception as e:
            add("config", "FAIL", f"load failed: {e}")
    else:
        add("config", "FAIL", f"not found: {cfg_file}")

    mock_entry = Path(__file__).resolve().parent.parent / "mock_server" / "base" / "flask_service.py"
    add("mock-entry", "PASS" if mock_entry.exists() else "FAIL", str(mock_entry))
    missing_mock = _check_mock_deps()
    if missing_mock:
        add("mock-deps", "WARN", "missing: " + ",".join(missing_mock))
    else:
        add("mock-deps", "PASS", "ok")

    for p in [Path("report"), Path(".ntf")]:
        try:
            p.mkdir(parents=True, exist_ok=True)
            test_file = p / ".doctor_write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            add(f"writable:{p}", "PASS", "ok")
        except Exception as e:
            add(f"writable:{p}", "FAIL", str(e))

    return checks


def _print_doctor_checks(checks: list[dict[str, str]]) -> None:
    for c in checks:
        print(f"[{c['status']}] {c['name']}: {c['detail']}")
    failed = [c for c in checks if c["status"] == "FAIL"]
    warns = [c for c in checks if c["status"] == "WARN"]
    print(f"doctor summary: total={len(checks)} fail={len(failed)} warn={len(warns)}")
    if failed:
        print("doctor next step: fix FAIL items first, then rerun `ntf doctor`.")


def _build_transport(name: str | None, cfg: Any) -> Any:
    if not name:
        return RequestsTransport(
            proxy=cfg.http_proxy,
            verify=cfg.http_verify,
            cert=cfg.http_cert,
            session_persist=cfg.http_session_persist,
        )
    plugins = transport_plugins()
    factory = plugins.get(name)
    if factory is None:
        raise SystemExit(f"transport plugin not found: {name}")
    try:
        return factory(cfg)
    except Exception as e:
        raise SystemExit(f"transport plugin init failed ({name}): {e}") from e


def _dispatch_reporter(name: str | None, *, summary: dict[str, Any], failures: list[dict[str, Any]]) -> None:
    if not name:
        return
    plugins = reporter_plugins()
    rep = plugins.get(name)
    if rep is None:
        raise SystemExit(f"reporter plugin not found: {name}")
    try:
        rep(summary, failures)
    except Exception as e:
        raise SystemExit(f"reporter plugin failed ({name}): {e}") from e


def _notify_dingding_run_yaml(
    *,
    summary: dict[str, Any],
    failures: list[dict[str, Any]],
    enabled: bool,
    webhook: str | None,
    secret: str | None,
    at_all: bool,
) -> None:
    env_enabled = str(os.getenv("NTF_DINGDING_ENABLED", "")).strip().lower() in {"1", "true", "yes", "y", "on"}
    if not enabled and not env_enabled:
        return

    wh = webhook or os.getenv("NTF_DINGDING_WEBHOOK")
    sec = secret or os.getenv("NTF_DINGDING_SECRET")
    if not wh or not sec:
        LOG.warning("dingding enabled but webhook/secret missing")
        return

    content_lines = [
        "[ntf run-yaml summary]",
        f"total={summary.get('total', 0)}",
        f"passed={summary.get('passed', 0)}",
        f"failed={summary.get('failed', 0)}",
        f"skipped={summary.get('skipped', 0)}",
    ]
    if failures:
        top = failures[:3]
        content_lines.append("top failures:")
        for x in top:
            content_lines.append(f"- {Path(str(x.get('file',''))).name}::{x.get('case_name','')} -> {x.get('error','')}")
    content = "\n".join(content_lines)
    try:
        DingDingBot(webhook=str(wh), secret=str(sec)).send_text(content, at_all=at_all)
    except Exception as e:
        LOG.warning("dingding notify failed: %s", e)


def _write_json(path: str, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_report(path: str, *, summary: dict[str, Any], failures: list[dict[str, Any]]) -> None:
    _write_json(path, {"summary": summary, "failures": failures})


def _read_pid(pid_path: Path) -> int | None:
    try:
        s = pid_path.read_text(encoding="utf-8").strip()
        return int(s) if s else None
    except Exception:
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _terminate_pid(pid: int) -> None:
    try:
        os.kill(pid, 15)
    except Exception:
        pass


def _migrate_check(path: str) -> dict[str, Any]:
    """Scan YAMLs and report schema compatibility issues.

    This is a lightweight checker (does not execute cases).
    """
    pp = Path(path)
    files: list[Path] = []
    if any(ch in path for ch in ["*", "?", "["]):
        files = [Path(p) for p in glob.glob(path, recursive=True)]
    elif pp.is_dir():
        files = list(pp.rglob("*.yaml")) + list(pp.rglob("*.yml"))
    else:
        files = [pp]

    issues: list[dict[str, Any]] = []
    total_cases = 0
    valid_files = 0

    for f in files:
        if not f.exists() or not f.is_file():
            continue

        if f.name.lower() in {"extract.yaml", "extract.yml"}:
            continue
        try:
            suite = load_yaml_suite(f)
            valid_files += 1
        except Exception as e:
            issues.append({"file": str(f), "type": "parse_error", "error": str(e)})
            continue

        for base, cases in suite:
            if not base.url:
                issues.append({"file": str(f), "type": "missing_base_url", "detail": "baseInfo.url empty"})

            for tc in cases:
                total_cases += 1
                if not tc.case_name:
                    issues.append({"file": str(f), "type": "missing_case_name"})
                if not tc.validation:
                    issues.append({"file": str(f), "case": tc.case_name, "type": "missing_validation"})
                if tc.extract_list and not isinstance(tc.extract_list, dict):
                    issues.append({"file": str(f), "case": tc.case_name, "type": "invalid_extract_list"})

    return {
        "summary": {
            "files": valid_files,
            "cases": total_cases,
            "issues": len(issues),
        },
        "issues": issues,
    }


def _parse_cookies(
    raw: Any,
    store: ExtractStore,
    *,
    functions: Any | None = None,
    renderer_name: str | None = None,
) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        # support ${func()} in cookies string
        try:
            rendered = build_renderer(
                RenderContext(extract_store=store),
                functions=functions,
                renderer_name=renderer_name,
            ).render(raw)
        except Exception:
            rendered = raw

        if isinstance(rendered, dict):
            return rendered

        if not isinstance(rendered, str):
            return None

        s = rendered.strip()
        if not s:
            return None
        # try json then python literal
        try:
            v = json.loads(s)
            return v if isinstance(v, dict) else None
        except Exception:
            pass
        try:
            v = ast.literal_eval(s)
            return v if isinstance(v, dict) else None
        except Exception:
            return None
    return None


def _check_mock_deps() -> list[str]:
    missing: list[str] = []
    try:
        import flask  # noqa: F401
    except Exception:
        missing.append("flask")
    try:
        import flask_jwt_extended  # noqa: F401
    except Exception:
        missing.append("flask-jwt-extended")
    try:
        import pandas  # noqa: F401
    except Exception:
        missing.append("pandas")
    return missing


def _mock_login(transport: RequestsTransport, base_url: str, *, user_name: str, passwd: str) -> str:
    url = base_url.rstrip("/") + "/dar/user/login"
    r = transport.request(
        method="POST",
        url=url,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        data={"user_name": user_name, "passwd": passwd},
        timeout_s=10,
    )
    if not isinstance(r.json_data, dict):
        raise SystemExit(f"mock login failed: invalid json response (status={r.status_code})")
    token = r.json_data.get("token")
    if not token:
        raise SystemExit(f"mock login failed: token missing (status={r.status_code})")
    return str(token)


def _load_debugtalk(path: str) -> Any:
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise SystemExit(f"debugtalk not found: {path}")

    # Try to make legacy debugtalk imports work (e.g. `from conf.setting import ...`).
    # We heuristically add the project root (containing `conf/`) to sys.path.
    inserted: list[str] = []
    candidates: list[Path] = [p.parent, p.parent.parent, p.parent.parent.parent]
    for c in candidates:
        try:
            if (c / "conf").is_dir() and str(c) not in sys.path:
                sys.path.insert(0, str(c))
                inserted.append(str(c))
        except Exception:
            pass
    # Always allow importing siblings relative to debugtalk file.
    if str(p.parent) not in sys.path:
        sys.path.insert(0, str(p.parent))
        inserted.append(str(p.parent))

    spec = importlib.util.spec_from_file_location("ntf_debugtalk", str(p))
    if spec is None or spec.loader is None:
        raise SystemExit(f"debugtalk load failed: {path}")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ModuleNotFoundError as e:
        print("debugtalk load failed: ModuleNotFoundError")
        print(f"- file: {path}")
        print(f"- missing module: {e.name}")
        if inserted:
            print("- sys.path added (for legacy imports):")
            for x in inserted:
                print(f"  - {x}")
        print("Fix tips:")
        print("- Ensure the old project root (containing conf/) is on PYTHONPATH, or pass a standalone debugtalk file.")
        print("- Or migrate the needed functions into ntf/renderer.py BuiltinFunctions.")
        raise SystemExit(1)
    except Exception:
        print("debugtalk load failed: unexpected error")
        print(f"- file: {path}")
        if inserted:
            print("- sys.path added (for legacy imports):")
            for x in inserted:
                print(f"  - {x}")
        print(traceback.format_exc())
        raise SystemExit(1)
    return mod


def _migrate_convert(src: str, dst: str) -> dict[str, Any]:
    src_p = Path(src)
    dst_p = Path(dst)
    if not src_p.exists() or not src_p.is_dir():
        raise SystemExit(f"src must be a directory: {src}")

    dst_p.mkdir(parents=True, exist_ok=True)

    files = list(src_p.rglob("*.yaml")) + list(src_p.rglob("*.yml"))
    files = [f for f in files if f.name.lower() not in {"extract.yaml", "extract.yml"}]

    issues: list[dict[str, Any]] = []
    copied = 0
    index: list[dict[str, str]] = []

    for f in files:
        rel = f.relative_to(src_p)
        out = dst_p / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(f, out)
            copied += 1
            index.append({"src": str(f), "dst": str(out)})
        except Exception as e:
            issues.append({"file": str(f), "type": "copy_error", "error": str(e)})

    return {
        "summary": {"files": len(files), "copied": copied, "issues": len(issues)},
        "index": index,
        "issues": issues,
    }
