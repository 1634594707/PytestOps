from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import ast
import shutil
import importlib.util
import importlib
import traceback
from pathlib import Path
from typing import Any

from ntf.assertions import AssertionEngine
from ntf.config import load_config
from ntf.executor import RequestExecutor
from ntf.extract import ExtractStore
from ntf.http import RequestsTransport
from ntf.yaml_case import load_yaml_suite

import pytest


def main() -> None:
    argv = sys.argv[1:]
    if "..." in argv and ("run-yaml" in argv or "migrate" in argv):
        print("Detected '...' placeholder in command. Please remove it and provide the real arguments.")
        print("Example:")
        print("  ntf run-yaml --config configs/default.yaml --cases tests/data --report report/run-yaml.json")
        raise SystemExit(2)

    parser = argparse.ArgumentParser(prog="ntf")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run")
    run.add_argument("--config", default=str(Path("configs/default.yaml")))
    run.add_argument("--allure-dir", default=None, help="If set, pass --alluredir to pytest.")
    run.add_argument(
        "--allure-clean",
        action="store_true",
        help="If set, pass --clean-alluredir (requires --allure-dir).",
    )

    run_yaml = sub.add_parser("run-yaml")
    run_yaml.add_argument("--config", default=str(Path("configs/default.yaml")))
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

    ns, unknown_args = parser.parse_known_args()

    if ns.cmd == "run":
        # Forward anything after `--` to pytest. Using parse_known_args keeps compatibility
        # with the common pattern: `ntf run ... -- -k xxx`.
        args = []
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
        raise SystemExit(pytest.main(args))

    if ns.cmd == "run-yaml":
        if unknown_args:
            raise SystemExit(f"Unknown arguments for run-yaml: {unknown_args}")
        cfg = load_config(ns.config)

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

        transport = RequestsTransport()
        engine = AssertionEngine()
        executor = RequestExecutor(
            base_url=cfg.base_url,
            timeout_s=cfg.timeout_s,
            transport=transport,
            extract_store=store,
            assertion_engine=engine,
            functions=functions,
        )

        if ns.mock_login:
            token = _mock_login(transport, cfg.base_url, user_name=ns.mock_user, passwd=ns.mock_pass)
            store.set("token", token)

        total = 0
        passed = 0
        failed = 0

        failures: list[dict[str, Any]] = []

        for f in uniq_files:
            suite = load_yaml_suite(f)
            for base, cases in suite:
                cookies = _parse_cookies(base.cookies, store, functions=functions)
                for tc in cases:
                    if include_case_re and not include_case_re.search(tc.case_name):
                        continue
                    if exclude_case_re and exclude_case_re.search(tc.case_name):
                        continue
                    total += 1
                    try:
                        executor.execute(
                            method=base.method,
                            url=base.url,
                            headers=base.header,
                            cookies=cookies,
                            request_kwargs=tc.request,
                            extract=tc.extract,
                            extract_list=tc.extract_list,
                            validation=tc.validation,
                        )
                        passed += 1
                    except Exception as e:
                        failed += 1
                        msg = str(e)
                        print(f"[FAIL] {Path(f).name} :: {tc.case_name} -> {msg}")
                        failures.append(
                            {
                                "file": f,
                                "case_name": tc.case_name,
                                "error": msg,
                            }
                        )
                        if not ns.continue_on_fail:
                            summary = {"total": total, "passed": passed, "failed": failed}
                            print(f"Summary: total={total} passed={passed} failed={failed}")
                            if ns.report:
                                _write_report(ns.report, summary=summary, failures=failures)
                            raise SystemExit(1)

        summary = {"total": total, "passed": passed, "failed": failed}
        print(f"Summary: total={total} passed={passed} failed={failed}")
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


def _parse_cookies(raw: Any, store: ExtractStore, *, functions: Any | None = None) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        # support ${func()} in cookies string
        try:
            from ntf.renderer import RenderContext, Renderer

            rendered = Renderer(RenderContext(extract_store=store), functions=functions).render(raw)
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
