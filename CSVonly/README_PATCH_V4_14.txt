V4.14 patch notes

- Fixes stale review page behavior:
  * Every valid /print request now replaces the previous pending review job.
  * If the new request auto-prints, old review pages redirect back to Status instead of showing the old batch.
  * If the new request needs review, old review pages redirect to the new /review/<job_id> URL.

- Adds clearer multi-interface support:
  * The server still binds to 0.0.0.0:5000, meaning all active IPv4 interfaces.
  * Startup now prints a best-effort list of usable URLs.
  * Status page shows detected local access URLs for Wi-Fi, Ethernet, USB-Ethernet, and localhost when Python can see them.

Note: If an expected Ethernet address does not appear, Flask may still be listening on it. Confirm with ipconfig and try http://<ethernet-ip>:5000. Windows Firewall can still block inbound connections per network profile.
