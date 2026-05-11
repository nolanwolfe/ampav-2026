/**
 * Cloudflare Worker for timaeus.ai
 *
 * Routes:
 *   timaeus.ai/ampav*  →  ampav.timaeus.ai (Cloudflare Tunnel → ThinkPad)
 *   timaeus.ai/*       →  existing caard.co site (unchanged)
 *
 * Deploy this in the Cloudflare dashboard:
 *   Workers & Pages → Create Worker → paste this → Deploy
 *   Then: Workers & Pages → your worker → Settings → Triggers
 *   → Add route: timaeus.ai/*
 */

export default {
  async fetch(request) {
    const url = new URL(request.url);

    // Route /ampav and /ampav/* to the POS tunnel
    if (url.pathname === '/ampav' || url.pathname.startsWith('/ampav/')) {
      const posUrl = new URL(request.url);
      posUrl.hostname = 'ampav.timaeus.ai';

      // Strip the /ampav prefix so Flask sees / and /log etc.
      posUrl.pathname = url.pathname === '/ampav'
        ? '/'
        : url.pathname.slice('/ampav'.length);

      const init = {
        method: request.method,
        headers: request.headers,
        redirect: 'follow',
      };
      if (!['GET', 'HEAD'].includes(request.method)) {
        init.body = request.body;
      }

      return fetch(new Request(posUrl.toString(), init));
    }

    // Everything else passes through to the existing caard.co site
    return fetch(request);
  },
};
