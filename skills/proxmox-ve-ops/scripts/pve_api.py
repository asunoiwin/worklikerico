#!/usr/bin/env python3
"""Safety-gated Proxmox VE REST client using only the Python standard library."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import ssl
import sys
import time
from typing import Any, Dict, Iterable, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


SECRET_MARKERS = ("password", "passwd", "secret", "token", "ticket", "csrf", "private", "key")
READ_METHODS = {"GET", "HEAD", "OPTIONS"}


class PVEClientError(RuntimeError):
    pass


def is_secret_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(marker in lowered for marker in SECRET_MARKERS)


def scrub_known_secrets(text: str, secret_values: Iterable[str]) -> str:
    cleaned = text
    unique = {secret for secret in secret_values if secret}
    for secret in sorted(unique, key=len, reverse=True):
        cleaned = cleaned.replace(secret, "<redacted>")
    return cleaned


def redact(value: Any, key: str = "", secret_values: Iterable[str] = ()) -> Any:
    if key and is_secret_key(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k), secret_values) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item, secret_values=secret_values) for item in value]
    if isinstance(value, str):
        return scrub_known_secrets(value, secret_values)
    return value


def parse_params(values: Iterable[str]) -> List[Tuple[str, str]]:
    result: List[Tuple[str, str]] = []
    for value in values:
        if "=" not in value:
            raise PVEClientError(f"invalid --param {value!r}; expected KEY=VALUE")
        key, item = value.split("=", 1)
        if not key:
            raise PVEClientError("parameter key must not be empty")
        if is_secret_key(key):
            raise PVEClientError(
                f"refusing secret-like command-line parameter {key!r}; "
                "process arguments and shell history are not a protected secret channel"
            )
        result.append((key, item))
    return result


def require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise PVEClientError(f"required environment variable {name} is not set")
    return value


def parse_base_url(raw_url: str) -> Tuple[str, str, int]:
    parsed = urlsplit(raw_url)
    if parsed.scheme.lower() != "https":
        raise PVEClientError("PVE_API_URL must use https; insecure HTTP is not allowed")
    if not parsed.hostname:
        raise PVEClientError("PVE_API_URL must include a hostname")
    if parsed.username or parsed.password:
        raise PVEClientError("PVE_API_URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise PVEClientError("PVE_API_URL must not contain a query or fragment")
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise PVEClientError(f"PVE_API_URL has an invalid port: {exc}") from None
    path = parsed.path.rstrip("/")
    if path.endswith("/api2/json"):
        path = path[: -len("/api2/json")]
    base_url = urlunsplit(("https", parsed.netloc, path, "", "")).rstrip("/")
    return base_url, parsed.hostname, port


def normalize_base_url(raw_url: str) -> str:
    return parse_base_url(raw_url)[0]


def normalize_api_path(path: str) -> str:
    if not path.startswith("/"):
        raise PVEClientError("API path must start with /")
    if "?" in path or "#" in path:
        raise PVEClientError("put query values in --param, not in the API path")
    if any(segment in {".", ".."} for segment in path.split("/")):
        raise PVEClientError("relative path segments are not allowed")
    return path


def normalize_fingerprint(value: str) -> str:
    compact = re.sub(r"[^0-9A-Fa-f]", "", value)
    if len(compact) != 64:
        raise PVEClientError("PVE_TLS_SHA256 must contain exactly one SHA-256 fingerprint")
    return compact.lower()


def observe_certificate(host: str, port: int) -> Tuple[str, str]:
    try:
        pem = ssl.get_server_certificate((host, port))
        der = ssl.PEM_cert_to_DER_cert(pem)
    except (OSError, ssl.SSLError, ValueError) as exc:
        raise PVEClientError(f"could not retrieve the server certificate: {exc}") from None
    return pem, hashlib.sha256(der).hexdigest()


def format_fingerprint(compact: str) -> str:
    return ":".join(compact[index : index + 2].upper() for index in range(0, 64, 2))


def build_context(host: str, port: int) -> ssl.SSLContext:
    ca_file = os.environ.get("PVE_CA_FILE", "")
    pinned = os.environ.get("PVE_TLS_SHA256", "")
    if ca_file and pinned:
        raise PVEClientError("set only one of PVE_CA_FILE or PVE_TLS_SHA256")
    if ca_file:
        if not os.path.isabs(ca_file):
            raise PVEClientError("PVE_CA_FILE must be an absolute path")
        if not os.path.isfile(ca_file):
            raise PVEClientError(f"PVE_CA_FILE does not exist or is not a file: {ca_file}")
        return ssl.create_default_context(cafile=ca_file)
    if not pinned:
        return ssl.create_default_context()

    expected = normalize_fingerprint(pinned)
    pem, actual = observe_certificate(host, port)
    if actual != expected:
        raise PVEClientError(
            "server certificate fingerprint mismatch: "
            f"expected {format_fingerprint(expected)}, got {format_fingerprint(actual)}"
        )
    partial_chain = getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", None)
    if partial_chain is None:
        raise PVEClientError("this Python/OpenSSL runtime cannot verify a pinned partial certificate chain")
    context = ssl.create_default_context()
    context.load_verify_locations(cadata=pem)
    context.verify_flags |= partial_chain
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def safe_error_body(raw: str, secret_values: Iterable[str] = ()) -> str:
    if not raw:
        return "empty response"
    try:
        parsed = json.loads(raw)
        return json.dumps(
            redact(parsed, secret_values=secret_values), ensure_ascii=False, sort_keys=True
        )
    except json.JSONDecodeError:
        compact = " ".join(scrub_known_secrets(raw, secret_values).split())
        return compact[:500] if compact else "non-JSON response"


def print_json(value: Any, stream: Any = sys.stdout) -> None:
    print(json.dumps(redact(value), ensure_ascii=False, indent=2, sort_keys=True), file=stream)


def extract_data(response: Any) -> Any:
    if isinstance(response, dict) and "data" in response:
        return response["data"]
    return response


def auth_environment() -> Tuple[str, str, str]:
    token_id = os.environ.get("PVE_API_TOKEN_ID", "")
    token_secret = os.environ.get("PVE_API_TOKEN_SECRET", "")
    if bool(token_id) != bool(token_secret):
        raise PVEClientError("PVE_API_TOKEN_ID and PVE_API_TOKEN_SECRET must be set together")
    if token_id:
        if "=" in token_id or "\n" in token_id or "\r" in token_id:
            raise PVEClientError("PVE_API_TOKEN_ID has an invalid format")
        if "\n" in token_secret or "\r" in token_secret:
            raise PVEClientError("PVE_API_TOKEN_SECRET has an invalid format")
        return "api-token", "api-token", f"PVEAPIToken={token_id}={token_secret}"

    username = os.environ.get("PVE_USERNAME", "root@pam")
    if not username or "\n" in username or "\r" in username or "=" in username:
        raise PVEClientError("PVE_USERNAME has an invalid format")
    return "password-ticket", username, ""


class PVEClient:
    def __init__(self) -> None:
        self.base_url, host, port = parse_base_url(require_env("PVE_API_URL"))
        self.context = build_context(host, port)
        self.auth_mode, self.identity, self.authorization = auth_environment()
        self.ticket = ""
        self.csrf = ""
        self._secret_values: List[str] = []
        if self.authorization:
            self._secret_values.extend(
                [self.authorization, self.authorization.split("=", 2)[-1]]
            )
        if self.auth_mode == "password-ticket":
            self._login()

    def _login(self) -> None:
        try:
            password = getpass.getpass(f"PVE password for {self.identity}: ")
        except (EOFError, OSError) as exc:
            raise PVEClientError(f"could not read password from the terminal: {exc}") from None
        if not password:
            raise PVEClientError("password must not be empty")
        try:
            response = self._request(
                "POST",
                "/access/ticket",
                [("username", self.identity), ("password", password)],
                authenticated=False,
                extra_secrets=[password],
            )
        finally:
            password = ""
        data = extract_data(response)
        if not isinstance(data, dict) or not data.get("ticket"):
            raise PVEClientError("login response did not contain a PVE authentication ticket")
        self.ticket = str(data["ticket"])
        self.csrf = str(data.get("CSRFPreventionToken", ""))
        self._secret_values.extend([self.ticket, self.csrf])

    def request(
        self, method: str, path: str, params: List[Tuple[str, str]] | None = None
    ) -> Any:
        return self._request(method, path, params or [], authenticated=True)

    def _request(
        self,
        method: str,
        path: str,
        params: List[Tuple[str, str]],
        authenticated: bool,
        extra_secrets: Iterable[str] = (),
    ) -> Any:
        method = method.upper()
        path = normalize_api_path(path)
        url = f"{self.base_url}/api2/json{path}"
        body = None
        if method in READ_METHODS:
            if params:
                url = f"{url}?{urlencode(params)}"
        else:
            body = urlencode(params).encode("utf-8")

        request = Request(url=url, data=body, method=method)
        request.add_header("Accept", "application/json")
        if body is not None:
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
        if authenticated:
            if self.auth_mode == "api-token":
                request.add_header("Authorization", self.authorization)
            else:
                request.add_header("Cookie", f"PVEAuthCookie={self.ticket}")
                if method not in READ_METHODS:
                    if not self.csrf:
                        raise PVEClientError("password-ticket write request is missing a CSRF token")
                    request.add_header("CSRFPreventionToken", self.csrf)

        try:
            with urlopen(request, context=self.context, timeout=30) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            detail = safe_error_body(raw, [*self._secret_values, *extra_secrets])
            raise PVEClientError(f"HTTP {exc.code} {exc.reason}: {detail}") from None
        except URLError as exc:
            raise PVEClientError(f"connection failed: {exc.reason}") from None
        except TimeoutError:
            raise PVEClientError("connection timed out; inspect task history before retrying a mutation") from None

        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise PVEClientError("server returned a non-JSON response") from None


def preview_identity() -> Dict[str, str]:
    mode, identity, _ = auth_environment()
    return {"auth_mode": mode, "identity": identity}


def preview(method: str, path: str, params: List[Tuple[str, str]], confirm: str | None) -> None:
    base_url = normalize_base_url(require_env("PVE_API_URL"))
    sanitized: Dict[str, Any] = {
        "dry_run": True,
        "identity": preview_identity(),
        "method": method,
        "url": f"{base_url}/api2/json{normalize_api_path(path)}",
        "params": dict(params),
        "contacts_server": False,
    }
    if confirm:
        sanitized["confirmation_contract"] = confirm
    print_json(sanitized)


def command_observe_cert(args: argparse.Namespace) -> int:
    base_url, host, port = parse_base_url(require_env("PVE_API_URL"))
    _, fingerprint = observe_certificate(host, port)
    print_json(
        {
            "url": base_url,
            "sha256_fingerprint": format_fingerprint(fingerprint),
            "verified": False,
            "next_step": "compare this fingerprint with a trusted PVE console or certificate record before setting PVE_TLS_SHA256",
        }
    )
    return 0


def command_get(args: argparse.Namespace) -> int:
    params = parse_params(args.param)
    response = PVEClient().request("GET", args.path, params)
    print_json(response)
    return 0


def command_request(args: argparse.Namespace) -> int:
    method = args.method.upper()
    params = parse_params(args.param)
    if method in READ_METHODS:
        raise PVEClientError("use the get subcommand for read-only requests")
    if args.dry_run:
        preview(method, args.path, params, args.confirm)
        return 0
    if os.environ.get("PVE_ALLOW_MUTATION") != "1":
        raise PVEClientError(
            "mutation blocked; preview with --dry-run, then set PVE_ALLOW_MUTATION=1 "
            "only for an explicitly approved operation"
        )
    if not args.confirm or not args.confirm.strip():
        raise PVEClientError("mutation blocked; --confirm must name the target and action")
    response = PVEClient().request(method, args.path, params)
    print_json(response)
    return 0


def task_path(node: str, upid: str, suffix: str) -> str:
    if not node or "/" in node or node in {".", ".."}:
        raise PVEClientError("node must be one exact node name")
    if not upid.startswith("UPID:"):
        raise PVEClientError("task identifier must start with UPID:")
    return f"/nodes/{quote(node, safe='')}/tasks/{quote(upid, safe='')}/{suffix}"


def command_task_log(args: argparse.Namespace) -> int:
    if args.limit <= 0:
        raise PVEClientError("--limit must be positive")
    response = PVEClient().request(
        "GET", task_path(args.node, args.upid, "log"), [("limit", str(args.limit))]
    )
    print_json(response)
    return 0


def command_wait_task(args: argparse.Namespace) -> int:
    if args.timeout <= 0 or args.interval <= 0:
        raise PVEClientError("--timeout and --interval must be positive")
    client = PVEClient()
    status_path = task_path(args.node, args.upid, "status")
    deadline = time.monotonic() + args.timeout
    last_status: Any = None

    while time.monotonic() < deadline:
        response = client.request("GET", status_path)
        status = extract_data(response)
        last_status = status
        if isinstance(status, dict) and status.get("status") == "stopped":
            print_json(response)
            exit_status = status.get("exitstatus")
            if exit_status == "OK":
                return 0
            try:
                log_response = client.request("GET", task_path(args.node, args.upid, "log"))
                print("task log:", file=sys.stderr)
                print_json(log_response, stream=sys.stderr)
            except PVEClientError as exc:
                print(f"warning: could not retrieve task log: {exc}", file=sys.stderr)
            raise PVEClientError(f"task stopped with exitstatus={exit_status!r}")
        time.sleep(args.interval)

    if last_status is not None:
        print_json({"last_task_status": last_status})
    raise PVEClientError(
        "task wait timed out; the operation outcome is unknown, so inspect task status before retrying"
    )


def select_fields(items: Any, fields: List[str]) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [
        {key: item.get(key) for key in fields if key in item}
        for item in items
        if isinstance(item, dict)
    ]


def command_inventory(args: argparse.Namespace) -> int:
    if args.task_limit <= 0:
        raise PVEClientError("--task-limit must be positive")
    client = PVEClient()
    failures: List[str] = []

    def probe(
        label: str,
        path: str,
        transform: Any = lambda value: value,
        params: List[Tuple[str, str]] | None = None,
    ) -> Dict[str, Any]:
        try:
            value = extract_data(client.request("GET", path, params or []))
            return {"ok": True, "data": transform(value)}
        except (PVEClientError, TypeError, ValueError) as exc:
            failures.append(label)
            return {"ok": False, "error": str(exc)}

    result: Dict[str, Any] = {
        "auth": {
            "mode": client.auth_mode,
            "identity": client.identity,
            "credentials_persisted": False,
        },
        "version": probe("version", "/version"),
        "cluster_status": probe(
            "cluster_status",
            "/cluster/status",
            lambda rows: select_fields(
                rows, ["type", "name", "nodeid", "online", "local", "quorate", "version"]
            ),
        ),
        "cluster_resources": probe(
            "cluster_resources",
            "/cluster/resources",
            lambda rows: {
                "count": len(rows) if isinstance(rows, list) else 0,
                "by_type": {
                    kind: sum(1 for row in rows if row.get("type") == kind)
                    for kind in sorted(
                        {row.get("type") for row in rows if isinstance(row, dict) and row.get("type")}
                    )
                }
                if isinstance(rows, list)
                else {},
            },
        ),
        "nodes": probe(
            "nodes",
            "/nodes",
            lambda rows: select_fields(
                rows,
                ["node", "status", "uptime", "cpu", "maxcpu", "mem", "maxmem", "disk", "maxdisk", "ssl_fingerprint"],
            ),
        ),
        "ha": probe(
            "ha",
            "/cluster/ha/status/current",
            lambda rows: {
                "count": len(rows) if isinstance(rows, list) else 0,
                "items": select_fields(rows, ["type", "id", "node", "status", "state"]),
            },
        ),
        "replication": probe(
            "replication",
            "/cluster/replication",
            lambda rows: {"count": len(rows) if isinstance(rows, list) else 0},
        ),
        "backup_jobs": probe(
            "backup_jobs",
            "/cluster/backup",
            lambda rows: {"count": len(rows) if isinstance(rows, list) else 0},
        ),
        "cluster_firewall": probe(
            "cluster_firewall",
            "/cluster/firewall/rules",
            lambda rows: {"rule_count": len(rows) if isinstance(rows, list) else 0},
        ),
        "access_users": probe(
            "access_users",
            "/access/users",
            lambda rows: {
                "count": len(rows) if isinstance(rows, list) else 0,
                "root_enabled": any(
                    row.get("userid") == "root@pam" and row.get("enable", 1)
                    for row in rows
                    if isinstance(row, dict)
                )
                if isinstance(rows, list)
                else False,
            },
        ),
    }

    node_rows = result["nodes"].get("data", []) if result["nodes"].get("ok") else []
    result["per_node"] = {}
    for node_row in node_rows:
        node = node_row.get("node")
        if not node:
            continue
        prefix = f"/nodes/{quote(str(node), safe='')}"
        result["per_node"][node] = {
            "status": probe(
                f"{node}.status",
                prefix + "/status",
                lambda row: {
                    key: row.get(key)
                    for key in ["pveversion", "kversion", "uptime", "cpu", "loadavg", "memory", "rootfs", "swap"]
                    if isinstance(row, dict) and key in row
                },
            ),
            "qemu": probe(
                f"{node}.qemu",
                prefix + "/qemu",
                lambda rows: select_fields(
                    rows, ["vmid", "name", "status", "uptime", "cpu", "cpus", "mem", "maxmem", "disk", "maxdisk"]
                ),
            ),
            "lxc": probe(
                f"{node}.lxc",
                prefix + "/lxc",
                lambda rows: select_fields(
                    rows, ["vmid", "name", "status", "uptime", "cpu", "cpus", "mem", "maxmem", "disk", "maxdisk"]
                ),
            ),
            "storage": probe(
                f"{node}.storage",
                prefix + "/storage",
                lambda rows: select_fields(
                    rows, ["storage", "type", "active", "enabled", "content", "used", "avail", "total"]
                ),
            ),
            "network": probe(
                f"{node}.network",
                prefix + "/network",
                lambda rows: select_fields(
                    rows,
                    ["iface", "type", "active", "autostart", "address", "cidr", "gateway", "bridge_ports", "bond_slaves", "vlan-id"],
                ),
            ),
            "services": probe(
                f"{node}.services",
                prefix + "/services",
                lambda rows: select_fields(rows, ["name", "service", "state", "desc"]),
            ),
            "recent_tasks": probe(
                f"{node}.recent_tasks",
                prefix + "/tasks",
                lambda rows: select_fields(
                    rows, ["upid", "type", "status", "exitstatus", "user", "starttime", "endtime"]
                ),
                [("limit", str(args.task_limit))],
            ),
        }

    result["summary"] = {
        "ok": not failures,
        "failed_probes": failures,
        "read_only": True,
    }
    print_json(result)
    critical = {"version", "nodes", "cluster_status"}
    return 1 if critical.intersection(failures) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safety-gated Proxmox VE REST client. Tokens come from the environment; passwords use a no-echo prompt."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    cert_parser = subparsers.add_parser(
        "observe-cert", help="observe an unverified server certificate fingerprint for out-of-band comparison"
    )
    cert_parser.set_defaults(handler=command_observe_cert)

    inventory_parser = subparsers.add_parser(
        "inventory", help="run a read-only cluster, node, guest, storage, network, service, and task inventory"
    )
    inventory_parser.add_argument(
        "--task-limit", type=int, default=10, help="recent tasks per node (default: 10)"
    )
    inventory_parser.set_defaults(handler=command_inventory)

    get_parser = subparsers.add_parser("get", help="perform an authenticated read-only GET request")
    get_parser.add_argument("path", help="API path beginning with /, excluding /api2/json")
    get_parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    get_parser.set_defaults(handler=command_get)

    request_parser = subparsers.add_parser("request", help="preview or perform a non-read request")
    request_parser.add_argument("method", choices=["POST", "PUT", "DELETE", "post", "put", "delete"])
    request_parser.add_argument("path", help="API path beginning with /, excluding /api2/json")
    request_parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    request_parser.add_argument("--dry-run", action="store_true", help="print a sanitized plan without connecting")
    request_parser.add_argument(
        "--confirm", help="target-specific approval contract, for example node=pve,vmid=101,action=start"
    )
    request_parser.set_defaults(handler=command_request)

    log_parser = subparsers.add_parser("task-log", help="retrieve a task log without changing task state")
    log_parser.add_argument("node", help="node that owns the task")
    log_parser.add_argument("upid", help="complete task identifier beginning with UPID:")
    log_parser.add_argument("--limit", type=int, default=100, help="maximum task-log lines (default: 100)")
    log_parser.set_defaults(handler=command_task_log)

    wait_parser = subparsers.add_parser("wait-task", help="poll a UPID until it reaches a terminal state")
    wait_parser.add_argument("node", help="node that owns the task")
    wait_parser.add_argument("upid", help="complete task identifier beginning with UPID:")
    wait_parser.add_argument("--timeout", type=float, default=600.0, help="maximum seconds to wait (default: 600)")
    wait_parser.add_argument("--interval", type=float, default=2.0, help="poll interval in seconds (default: 2)")
    wait_parser.set_defaults(handler=command_wait_task)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except PVEClientError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("error: interrupted; inspect task status before retrying any mutation", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
