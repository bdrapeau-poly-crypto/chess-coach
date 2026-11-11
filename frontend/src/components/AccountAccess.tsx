import { FormEvent, useState } from "react";
import { generateRecoveryCodes, playerSignIn, playerSignOut, resetPlayerPassword } from "../api/client";
import type { PlayerAccount } from "../api/client";

type Mode = "login" | "register" | "reset" | "codes" | null;

export function AccountAccess({ account, onSignedIn, onSignedOut }: {
  account: PlayerAccount | null;
  onSignedIn: (account: PlayerAccount) => Promise<void>;
  onSignedOut: () => void;
}) {
  const [mode, setMode] = useState<Mode>(null);
  const [loginName, setLoginName] = useState("");
  const [password, setPassword] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [codes, setCodes] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function choose(next: Mode) {
    setMode(next); setPassword(""); setRecoveryCode(""); setError(""); setMessage("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!mode) return;
    setBusy(true); setError(""); setMessage("");
    try {
      if (mode === "codes") {
        const result = await generateRecoveryCodes(password);
        setCodes(result.recovery_codes);
        setMode(null);
      } else if (mode === "reset") {
        const result = await resetPlayerPassword(loginName.trim().toLowerCase(), recoveryCode, password);
        onSignedOut();
        setCodes(result.recovery_codes);
        setMessage("Password reset. Save your replacement recovery codes, then sign in with your new password.");
        setMode("login");
      } else {
        const next = await playerSignIn(mode, loginName.trim().toLowerCase(), password);
        setCodes(next.recovery_codes ?? []);
        setMode(null);
        await onSignedIn(next);
      }
      setPassword(""); setRecoveryCode("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not complete account request");
    } finally { setBusy(false); }
  }

  async function signOut() {
    setBusy(true); setError("");
    try { await playerSignOut(); setCodes([]); choose(null); onSignedOut(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Could not sign out"); }
    finally { setBusy(false); }
  }

  return <section className="account-access" aria-label="Chess Coach account">
    <div className="account-actions">
      {account ? <>
        <span>Signed in as <strong>{account.login_name}</strong></span>
        <button className="text-button" disabled={busy} onClick={() => choose("codes")} type="button">Generate recovery codes</button>
        <button className="text-button" disabled={busy} onClick={() => void signOut()} type="button">Sign out of account</button>
      </> : <>
        <button className="text-button" disabled={busy} type="button" onClick={() => choose("login")}>Sign in</button>
        <button className="text-button" disabled={busy} type="button" onClick={() => choose("register")}>Create account</button>
        <button className="text-button" disabled={busy} type="button" onClick={() => choose("reset")}>Forgot password?</button>
      </>}
    </div>
    {!account && !mode && <p className="player-note">Save your player workspace and return to existing analysis on any device.</p>}
    {codes.length > 0 && <aside className="recovery-panel" aria-label="Your recovery codes">
      <h2>Save your recovery codes</h2>
      <p>Store these in your password manager. They are shown only now. A password reset replaces all codes and signs out every device.</p>
      <ul>{codes.map(code => <li key={code}><code>{code}</code></li>)}</ul>
      <button disabled={busy} type="button" onClick={() => setCodes([])}>I have saved these codes</button>
    </aside>}
    {mode && <form className="account-form" onSubmit={submit}>
      <h2>{mode === "register" ? "Create your Chess Coach account" : mode === "reset" ? "Reset your password" : mode === "codes" ? "Generate replacement recovery codes" : "Sign in to Chess Coach"}</h2>
      {mode !== "codes" && <>
        <label htmlFor="account-name">Account name</label>
        <input id="account-name" value={loginName} onChange={e => setLoginName(e.target.value)} autoComplete="username" autoCapitalize="none" spellCheck={false} minLength={3} maxLength={64} pattern="[a-zA-Z0-9_-]+" required />
      </>}
      {mode === "reset" && <>
        <label htmlFor="recovery-code">Recovery code</label>
        <input id="recovery-code" value={recoveryCode} onChange={e => setRecoveryCode(e.target.value)} autoComplete="off" autoCapitalize="none" spellCheck={false} minLength={32} maxLength={64} required />
        <p className="player-note">Use a code you saved earlier. Without a recovery code, this app cannot reset your password.</p>
      </>}
      <label htmlFor="account-password">{mode === "reset" ? "New Chess Coach password" : mode === "codes" ? "Current Chess Coach password" : "Chess Coach password"}</label>
      <input id="account-password" type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete={mode === "register" || mode === "reset" ? "new-password" : "current-password"} minLength={12} maxLength={128} required />
      <p className="player-note">Use a separate password of at least 12 characters. This account saves a public player workspace and does not verify Chess.com ownership.</p>
      {mode === "codes" && <p className="player-note">Generating codes invalidates your previous codes. Save the replacement set before leaving this page.</p>}
      <div className="account-actions">
        <button disabled={busy} type="submit">{busy ? "Connecting…" : mode === "register" ? "Create account and sign in" : mode === "reset" ? "Reset password" : mode === "codes" ? "Generate codes" : "Sign in to account"}</button>
        <button className="text-button" disabled={busy} type="button" onClick={() => choose(null)}>Cancel</button>
      </div>
    </form>}
    {message && <p role="status">{message}</p>}
    {error && <p className="error" role="alert">{error}</p>}
  </section>;
}
