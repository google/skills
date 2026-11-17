# Common Gerrit Hosts and Shortlink Mapping

Most Gerrit servers authenticate via standard Git HTTP credentials configured in
`~/.gitcookies` (`git config http.cookiefile`) or `~/.netrc`. See "Quick start
and authentication setup" in `SKILL.md` for credential setup instructions.

Never send authenticated `/a/` REST requests directly to a shortlink domain:
cookies are scoped to the review host and HTTP redirects drop `/a/`
authentication. `scripts/gerrit.py` automatically maps the shortlinks below to
their canonical Review Host URL.

## Common Public and Self-Hosted Gerrit Hosts

Host                   | Review Host URL                            | Public Shortlink Prefix
---------------------- | ------------------------------------------ | -----------------------
**Android (AOSP)**     | `https://android-review.googlesource.com`  | `https://r.android.com/`
**Chromium**           | `https://chromium-review.googlesource.com` | `https://crrev.com/c/`
**Fuchsia**            | `https://fuchsia-review.googlesource.com`  | `https://fxrev.dev/`
**Self-Hosted Gerrit** | `https://gerrit.{organization_domain}`     | N/A

For any host not listed above, derive `{host}` from the local git checkout
(`git config --get-regexp '^remote\..*\.(review|url)$'` or `.gitreview`) rather
than guessing, following the host-detection rules in `SKILL.md`. For
`*.googlesource.com` git remotes, the review host is the git host with `-review`
appended to the instance prefix (`https://{instance}.googlesource.com/{project}`
maps to `https://{instance}-review.googlesource.com`).
