# Reverse proxy contract

Run with `--upstream http://127.0.0.1:8000`. Only the configured origin is contacted.

The `/api` prefix is stripped: `/api/users` becomes `/users`; `/api` and `/api/` become `/`. The `/static` prefix is also stripped before resolving files inside the document root. `/apiculture` is an ordinary local-file path, not a proxy route.

Paths are decoded once by request parsing, then encoded when building the upstream request. Query strings will be forwarded unchanged. A backend URL must be an origin without a path, credentials, query, or fragment.

Connection-specific fields are removed in both directions, including every name listed in `Connection`. Message lengths and connection policy are rebuilt for each hop. Rules follow [HTTP semantics §7.6.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-7.6.1) and [HTTP/1.1 framing](https://www.rfc-editor.org/rfc/rfc9112.html#section-6.3).

Upstream `Host` is the configured backend authority. Incoming `Forwarded` and all `X-Forwarded-*` values are discarded. The proxy generates `X-Forwarded-For` from the accepted peer IP, `X-Forwarded-Host` from the client Host field, and `X-Forwarded-Proto` from the frontend protocol. The original Host is client-supplied metadata; backends must not treat it as an authorization decision. This policy assumes a direct client connection and does not trust an external proxy chain.

`--upstream-connect-timeout` defaults to 2 seconds. `--upstream-response-timeout` defaults to 10 seconds and bounds header reading and body reading separately; informational replies share the header deadline. Upstream writes have that socket timeout per write. These are independent of frontend header/body/write/idle deadlines. OS hostname resolution may exceed socket connection deadlines; use configured numeric addresses when strict DNS-free timing matters.
