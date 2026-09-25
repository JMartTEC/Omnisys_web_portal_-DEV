// Sesión y guard de rutas. Angular -> AuthService + AuthGuard (canActivate).
(function () {
  const C = window.GD_CONFIG;
  const S = window.localStorageSafe;

  window.GD_AUTH = {
    user() { try { return JSON.parse(S.get(C.USER_KEY) || "null"); } catch (e) { return null; } },
    token() { return S.get(C.TOKEN_KEY); },
    isLogged() { return !!this.token() && !!this.user(); },
    async login(username, password) {
      const r = await window.GD_API.login(username, password);
      S.set(C.TOKEN_KEY, r.access_token);
      S.set(C.USER_KEY, JSON.stringify(r.user));
      return r.user;
    },
    logout(expired) {
      S.del(C.TOKEN_KEY); S.del(C.USER_KEY);
      window.location.href = "index.html" + (expired ? "?expirada=1" : "");
    },
    // Llamar al inicio de cada página protegida
    guard() {
      if (!this.isLogged()) {
        const next = encodeURIComponent(location.pathname.split("/").pop() + location.search);
        window.location.replace("index.html?next=" + next);
        return false;
      }
      return true;
    },
    canUpload(gobierno) {
      const u = this.user();
      return !!u && (u.rol === "admin" || u.gobierno === gobierno);
    }
  };
})();
