// Login com Amazon Cognito (Hosted UI, Authorization Code + PKCE, sem client secret)
// Desativado se window.API_CONFIG.cognito.domain / clientId estiverem vazios.
// shortcut: sem refresh token; quando o access token expira (1h) a API retorna 401 e o usuario loga de novo.

const Auth = (() => {
  const cfg = window.API_CONFIG?.cognito || {};
  const enabled = Boolean(cfg.domain && cfg.clientId);
  const redirectUri = window.location.origin + window.location.pathname;
  const TOKEN_KEY = 'archiq_access_token';
  const VERIFIER_KEY = 'archiq_pkce_verifier';

  const b64url = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  function getToken() {
    return sessionStorage.getItem(TOKEN_KEY);
  }

  async function login() {
    const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
    sessionStorage.setItem(VERIFIER_KEY, verifier);
    const challenge = b64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)));
    const params = new URLSearchParams({
      response_type: 'code', client_id: cfg.clientId, redirect_uri: redirectUri,
      scope: 'openid email', code_challenge_method: 'S256', code_challenge: challenge,
    });
    window.location.assign(`${cfg.domain}/oauth2/authorize?${params}`);
  }

  function logout() {
    sessionStorage.removeItem(TOKEN_KEY);
    const params = new URLSearchParams({ client_id: cfg.clientId, logout_uri: redirectUri });
    window.location.assign(`${cfg.domain}/logout?${params}`);
  }

  // Troca o ?code= do retorno do Hosted UI pelo access token
  async function handleRedirect() {
    const code = new URLSearchParams(window.location.search).get('code');
    if (!code) return;
    window.history.replaceState({}, '', redirectUri);
    const verifier = sessionStorage.getItem(VERIFIER_KEY);
    sessionStorage.removeItem(VERIFIER_KEY);
    const response = await fetch(`${cfg.domain}/oauth2/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'authorization_code', client_id: cfg.clientId,
        code, redirect_uri: redirectUri, code_verifier: verifier || '',
      }),
    });
    if (response.ok) sessionStorage.setItem(TOKEN_KEY, (await response.json()).access_token);
  }

  function renderButton() {
    const bar = document.getElementById('authBar');
    if (!bar) return;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn-auth';
    btn.textContent = getToken() ? 'Sair' : 'Entrar';
    btn.addEventListener('click', getToken() ? logout : login);
    bar.replaceChildren(btn);
  }

  const ready = enabled
    ? handleRedirect().catch((e) => console.error('Falha no login Cognito:', e)).finally(renderButton)
    : Promise.resolve();

  return {
    enabled, ready, login,
    // Header Authorization para as chamadas da API (vazio se o login estiver desativado)
    headers: () => (enabled && getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    // Chamado quando a API responde 401: token ausente/expirado
    expired() { sessionStorage.removeItem(TOKEN_KEY); renderButton(); },
  };
})();
