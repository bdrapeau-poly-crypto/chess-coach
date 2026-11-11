import { FormEvent, useState } from "react";
import { playerSignIn, playerSignOut } from "../api/client";
import type { PlayerAccount } from "../api/client";

export function AccountAccess({ account, onSignedIn, onSignedOut }: {
  account: PlayerAccount | null;
  onSignedIn: (account: PlayerAccount) => Promise<void>;
  onSignedOut: () => void;
}) {
  const [mode, setMode] = useState<"login" | "register" | null>(null);
  const [loginName, setLoginName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!mode) return;
    setBusy(true);
    setError("");
    try {
      const next = await playerSignIn(mode, loginName.trim().toLowerCase(), password);
      setPassword("");
      setMode(null);
      await onSignedIn(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not sign in");
    } finally { setBusy(false); }
  }

  async function signOut() {
    setBusy(true);
    setError("");
    try { await playerSignOut(); onSignedOut(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Could not sign out"); }
    finally { setBusy(false); }
  }

  return <section className="account-access" aria-label="Chess Coach account">
    {account ? <div className="account-actions">
      <span>Signed in as <strong>{account.login_name}</strong></span>
      <button className="text-button" disabled={busy} onClick={() => void signOut()} type="button">Sign out of account</button>
    </div> : <>
      <div className="account-actions">
        <button className="text-button" type="button" onClick={() => { setMode("login"); setError(""); }}>Sign in</button>
        <button className="text-button" type="button" onClick={() => { setMode("register"); setError(""); }}>Create account</button>
      </div>
      {!mode && <p className="player-note">Save your player workspace and return to existing analysis on any device.</p>}
      {mode && <form className="account-form" onSubmit={submit}>
        <h2>{mode === "register" ? "Create your Chess Coach account" : "Sign in to Chess Coach"}</h2>
        <label htmlFor="account-name">Account name</label>
        <input id="account-name" value={loginName} onChange={(e) => setLoginName(e.target.value)} autoComplete="username" autoCapitalize="none" spellCheck={false} minLength={3} maxLength={64} pattern="[a-zA-Z0-9_-]+" required />
        <label htmlFor="account-password">Chess Coach password</label>
        <input id="account-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "register" ? "new-password" : "current-password"} minLength={12} maxLength={128} required />
        <p className="player-note">Use a separate password of at least 12 characters. Keep it in your password manager. Password recovery is not available yet. This account saves a public player workspace and does not verify Chess.com ownership.</p>
        <div className="account-actions">
          <button disabled={busy} type="submit">{busy ? "Connecting…" : mode === "register" ? "Create account and sign in" : "Sign in to account"}</button>
          <button className="text-button" disabled={busy} type="button" onClick={() => { setPassword(""); setMode(null); }}>Cancel</button>
        </div>
      </form>}
    </>}
    {error && <p className="error" role="alert">{error}</p>}
  </section>;
}
