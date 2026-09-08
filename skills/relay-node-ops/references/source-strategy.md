# China-network source strategy

Use the quickest working route:

1. Try the catalog URL on the Linux target.
2. If GitHub/raw.githubusercontent.com is blocked, use `prepare_installer.sh ROLE --china-source`. It tries jsDelivr and then a raw-file proxy, and rewrites later GitHub release/raw/API requests to `gh-proxy.com`.
3. If both public routes fail, download and inspect on the controller, copy with SCP, then use `prepare_installer.sh ROLE --local-script FILE --china-source`.
4. Always print the resolved source, original SHA-256, adapted SHA-256, and adapter before execution.

Do not use `ghfast.top` as the default: the mainland mobile probe was poor. Do not choose GOST's built-in Aliyun OSS mirror: it was unavailable from every measured mainland node. Measurements and hashes are in [china-source-validation.md](china-source-validation.md).

Keep one cached copy per role under `/var/cache/relay-node-ops`. This makes later manual maintenance possible even if the upstream URL is temporarily unavailable. A changed upstream SHA-256 is a review signal, not an automatic failure, because these upstream scripts are mutable. Revalidate public mirrors when hashes change or the recorded reachability check is stale.
