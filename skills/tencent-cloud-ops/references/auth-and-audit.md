# Authentication, least privilege, and audit evidence

## Official sources

- [CAM supported-service and authorization-granularity overview](https://cloud.tencent.com/document/product/598/67350)
- [CVM CAM interface authorization details](https://cloud.tencent.com/document/product/598/57095)
- [VPC CAM interface authorization details](https://cloud.tencent.com/document/product/598/57179)
- [CAM roles and temporary credentials](https://cloud.tencent.com/document/product/598/19421)
- [STS interface authorization](https://cloud.tencent.com/document/product/598/70020)
- [TCCLI common parameters](https://cloud.tencent.com/document/product/440/129328)
- [TCCLI configuration behavior](https://cloud.tencent.com/document/product/440/34012)
- [Tencent Cloud Python SDK credential management](https://cloud.tencent.com/document/sdk/Python)
- [Python SDK temporary-token constructor](https://github.com/TencentCloud/tencentcloud-sdk-python/blob/master/tencentcloud/common/credential.py)
- [CloudAudit product functions](https://cloud.tencent.com/document/product/629/11933)
- [CloudAudit API 3.0 overview](https://cloud.tencent.com/document/product/629/35332)

## Credential policy

Prefer, in order:

1. A CVM workload role or another managed workload identity when code runs on an authorized cloud workload.
2. STS role assumption with a short session and a session policy narrower than the role's maximum permission.
3. A least-privilege sub-user credential only when temporary credentials are unavailable.

Do not use a known root-account permanent key for mutations. When the user explicitly authorizes a bounded read-only query, use the supplied sub-user key directly if temporary credentials are unavailable. Do not persist it in a profile, source file, `.env`, memory, or report.

For role assumption, constrain both the role's permission policy and trust policy. Limit `sts:AssumeRole` to the exact role and add time/IP conditions where appropriate. Never grant unrestricted role assumption.

## Build a minimal CAM policy

1. Start with only the read actions needed to inventory the dependency graph.
2. Add only the exact mutation actions in the approved plan.
3. Use the CAM interface table to distinguish resource-level from operation-level actions. Use `*` only where the specific API is operation-level and therefore cannot accept a resource ARN.
4. Constrain region, source network, session duration, tags, and resource paths when the product supports them.
5. Separate inventory and mutation roles when possible. Expire or detach the mutation permission after the change.
6. Treat an authorization error as a policy-design problem. Do not respond by adding a product-wide wildcard.

The action names in [api-map.md](api-map.md) are the starting allowlist, not a ready-made policy. Confirm current authorization granularity in CAM because API support changes over time.

## One-time injection without persistence

For an explicitly authorized read-only action, use credentials from the active request once through stdin/PTY or the current process environment and proceed. Do not require the user to repeat them. Prefer the simplest direct transport that works; do not introduce a named pipe, GUI flow, sub-agent, or separate broker only to move the credential.

Keep handling proportional: do not echo or save the value, clear runtime variables after use, and give at most one short rotation reminder after the result when the credential appeared in conversation. Do not turn credential hygiene into the main task.

For TCCLI, use `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY`, and, for STS, `TENCENTCLOUD_TOKEN` only in the current process. TCCLI supports the token field for temporary credentials. Keep authentication out of command arguments because arguments may be stored in shell history or exposed in process listings.

Before use:

- disable shell tracing;
- ensure no command wrapper prints environment variables;
- confirm the TCCLI version and selected profile behavior;
- pass `--region` explicitly and verify the first call is read-only;
- avoid `--debug`, verbose HTTP logging, and request-header dumps.

After use, unset the credential variables and close the shell. Do not run a command that prints their values to “verify” injection.

For SDK code, construct the credential from process environment values. Include the third token argument for STS and omit it for a permanent sub-user pair. Prefer workload-role providers where available because they refresh temporary credentials automatically.

## Sanitized operation record

Record one line or structured object per API request with:

- UTC and local timestamp;
- operator/session label, never an authentication value;
- service, action, API version, and region;
- target resource type and masked identifier;
- approved change ticket or user-confirmation reference;
- redacted parameter summary and hash of the canonical redacted payload;
- request ID, outcome, error code, and retry/idempotency token hash;
- pre-state, post-state, validation, and rollback outcome.

Never record environment dumps, authentication headers, raw CLI invocations containing secrets, instance login secrets, complete private addressing plans, or unredacted API responses.

## CloudAudit verification

CloudAudit records event time, operator, event name/source, region, resource, source IP, error code, event ID, and request ID. Recent history is available in the console; API 3.0 exposes `DescribeEvents` and `LookUpEvents`-style retrieval in the product API surface.

Use the API request ID as the primary correlation key. Audit delivery can lag the control-plane response, so bounded retry is valid; absence immediately after a call is not proof that the call was unaudited. Do not change or disable audit trails as part of an unrelated infrastructure task.

## Output redaction

Mask identifiers while retaining enough information to correlate, for example `<RESOURCE_TYPE>:…<LAST4>`. Summarize IPs as role plus network class, such as `public endpoint` or `private subnet member`, unless the user explicitly needs the value in a live operational message. Never persist a live identifier in this skill directory.
