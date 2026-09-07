# Loop ROS deployment

Updated 2026-09-05. Authorized host: `root@8.134.90.171`, SSH port 22 using existing agent keys. Root login succeeded after the user granted access. Project directory: `/root/workspaces/LoopROS`.

Status: staged, not publicly served. `staging/loopros-server-stage-20260905/` contains the generated wheel, latest.json, bootstrap.py, install.sh, public website assets and selected docs, without user credentials or runtime databases. Provisional base URL: `https://8.134.90.171/LoopROS`; unusable until TLS is resolved. Rebuild with the final authorized HTTPS hostname before publishing.

Nginx runs as www, configured under `/www/server/nginx/conf/nginx.conf` and `/www/server/panel/vhost/nginx/`. The existing Mingle vhost names both mingle.box2ai.com and 8.134.90.171. Do not replace it or remove its HTTPS redirect. `/root` is not traversable by www; do not broaden root-directory permissions to serve static files. Select a dedicated public directory or narrowly scoped serving arrangement after hostname confirmation.

No nginx configuration, existing web content, TLS certificate or services were modified. Final hostname/valid TLS remains unresolved; no curl -k / verification bypass. Server project README.md mirrors this record. Source workflow: docs/RELEASES.md. Staging copies of earlier docs describe prior state; this record supersedes them.

2026-09-05 user reconfirmed the server IP `8.134.90.171`. The website preview now shows `https://8.134.90.171/LoopROS/install.sh` with a pending-HTTPS notice. Read-only recheck: SSH succeeds; HTTP install URL returns 301 to HTTPS; HTTPS returns curl error 60, certificate subject does not match the IP. Nginx also has a separate `loopmaster.box2ai.com` vhost; that hostname has not been selected by the user for this release. No server configuration or public files changed in this check.
