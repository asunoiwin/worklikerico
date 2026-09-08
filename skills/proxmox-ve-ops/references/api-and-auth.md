# Proxmox VE API and Authentication

## Official Sources

- Current REST API Viewer: https://pve.proxmox.com/pve-docs/api-viewer/
- Current Administration Guide: https://pve.proxmox.com/pve-docs/pve-admin-guide.pdf
- `pvedaemon(8)`: https://pve.proxmox.com/pve-docs/pvedaemon.8.html
- Cluster filesystem (`pmxcfs`): https://pve.proxmox.com/pve-docs-9-beta/chapter-pmxcfs.html
- Network configuration: https://pve.proxmox.com/wiki/Network_Configuration

Always prefer documentation matching the installed major version. The API Viewer generated from that installation or release is authoritative for paths and parameters.

## Choose the Interface

Use the HTTPS REST API for remote automation. The public API normally listens on TCP 8006 through `pveproxy`. The internal API daemon listens locally on `127.0.0.1:85`; do not expose it as a replacement for `pveproxy`.

Use `pvesh` locally when shell access to the exact node is explicitly allowed. It uses the same API model and avoids remote token transport. Use `qm`, `pct`, `pvesm`, and other supported CLIs for focused local operations, but inspect the installed version's help first.

Do not mutate `/etc/pve` directly when a supported API or CLI exists. It is `pmxcfs`, a quorum-backed cluster filesystem that may become read-only without quorum and contains security-sensitive cluster state.

## Environment Contract

The bundled wrapper supports password-ticket and API-token authentication.

Password-ticket mode defaults to `root@pam` and reads the password from a no-echo terminal prompt:

```text
PVE_API_URL=https://pve.example:8006
PVE_USERNAME=root@pam                                      # optional; this is the default
PVE_CA_FILE=/absolute/path/to/proxmox-cluster-ca.pem       # preferred for a private CA
```

API-token mode is selected only when both token variables are present:

```text
PVE_API_URL=https://pve.example:8006
PVE_API_TOKEN_ID=operator@pve!codex
PVE_API_TOKEN_SECRET=secret-value
PVE_CA_FILE=/absolute/path/to/proxmox-cluster-ca.pem
```

For an environment where the private CA file is unavailable, use an explicitly verified leaf-certificate pin:

```text
PVE_TLS_SHA256=AA:BB:CC:...:FF
```

Requirements:

- `PVE_API_URL` must use HTTPS and must not contain user information, a query, or a fragment.
- Use `PVE_CA_FILE` for a private Proxmox cluster CA. With a publicly trusted certificate, omit both TLS variables and use the system trust store.
- Use `PVE_TLS_SHA256` only after comparing the fingerprint through a trusted PVE console, host shell, or existing certificate record. The wrapper pins that exact certificate and still verifies its hostname or IP SAN.
- Set only one of `PVE_CA_FILE` and `PVE_TLS_SHA256`.
- Export secrets only for the current process or protected session. Do not place them in the skill, repository, service unit, shell profile, command history, or transcript.
- Do not define `PVE_PASSWORD`. Password mode deliberately uses `getpass` so the password is not placed in arguments, environment variables, or output.
- Password mode exchanges the password for an in-memory PVE ticket and CSRF token. API-token mode sends `Authorization: PVEAPIToken=<token-id>=<token-secret>`. Neither credential is printed.
- Do not use `curl -k`, Python `verify=False`, or an unverified fallback.

## Privileged and Scoped Token Models

Many production PVE environments standardize host administration on `root@pam`. This skill supports that model and may use a root-owned API token when the user authorizes it. Treat every write as fully privileged: show the identity class, exact target, operation, impact, and rollback before execution. Never expose the root password or token secret.

When separation of duties is required, create a dedicated service user and API token. Keep token privilege separation enabled so the token can use only the intersection of its own ACLs and the backing user's permissions.

Separate roles by purpose:

- inventory and monitoring: read-only permissions such as `PVEAuditor` on the smallest useful path;
- guest lifecycle: only the required VM power/config privileges, ideally limited to a pool or exact guests;
- backup or storage: separate role scoped to the required storage and guests;
- cluster, network, permission, and update administration: temporary or separately governed credentials.

Do not silently switch between root and scoped identities. State which model is active. For scoped tokens, do not disable privilege separation merely to make a token work; diagnose the missing ACL instead.

## Response and Task Semantics

Successful API responses normally wrap their payload in a top-level `data` field. Mutation endpoints may return a UPID string rather than a completed result.

A returned UPID means the worker task was accepted, not that it succeeded. Poll:

```text
GET /nodes/{node}/tasks/{upid}/status
```

Wait until `status` is `stopped`, then require `exitstatus` equal to `OK`. Retrieve the task log on failure before considering a retry.

## Bundled Wrapper

Observe the currently presented certificate before first connection:

```bash
python3 scripts/pve_api.py observe-cert
```

This observation is not trusted by itself. Compare it out of band, then set `PVE_TLS_SHA256` or install the cluster CA.

Run a sanitized read-only inventory:

```bash
python3 scripts/pve_api.py inventory
```

Run focused read-only requests:

```bash
python3 scripts/pve_api.py get /version
python3 scripts/pve_api.py get /nodes
python3 scripts/pve_api.py get /cluster/resources --param type=vm
```

Retrieve the log for a known task:

```bash
python3 scripts/pve_api.py task-log pve 'UPID:pve:...'
```

Preview a mutation without contacting the server:

```bash
python3 scripts/pve_api.py request POST /nodes/pve/qemu/101/status/start --dry-run
```

Execute only after a target-specific permission prompt and approval. `PVE_ALLOW_MUTATION=1` is an execution latch, not a substitute for that approval:

```bash
PVE_ALLOW_MUTATION=1 python3 scripts/pve_api.py request POST \
  /nodes/pve/qemu/101/status/start \
  --confirm 'cluster=prod,node=pve,vmid=101,action=start'
```

Wait for an asynchronous task:

```bash
python3 scripts/pve_api.py wait-task pve 'UPID:pve:...'
```

The wrapper intentionally rejects secret-like parameters supplied on the command line because command arguments can enter shell history and process listings. Password login is supported through the no-echo prompt; operations that create or change other secrets still require a purpose-built protected input path.

## Local CLI Discipline

Before using a local command:

1. confirm `hostname`, PVE version, cluster membership, quorum, and the object's current owner;
2. inspect `pvesh usage <path>`, `qm help`, `pct help`, or the installed man page;
3. produce a sanitized dry plan;
4. run one approved mutation;
5. capture the task or command result and verify through the API as well as the workload.

Do not assume command syntax copied from another PVE major version is current.
