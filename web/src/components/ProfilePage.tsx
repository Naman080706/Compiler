// The student's own page (#/profile): the analytics dashboard, how many times each error category was
// hit (F9), and a reset button. The id is a random token kept in this browser (see api.ts).
import { useCallback, useEffect, useState } from "react";
import { getAnalytics, getProfile, resetProfile, studentId } from "../api";
import type { Analytics, ProfileView } from "../types";
import Dashboard from "./Dashboard";

interface Props {
  refreshKey: number; // bumped after each compile so the numbers stay current
}

export default function ProfilePage({ refreshKey }: Props) {
  const [profile, setProfile] = useState<ProfileView | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [p, a] = await Promise.all([getProfile(), getAnalytics(30)]);
      setProfile(p);
      setAnalytics(a);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [refreshKey, load]);

  async function onReset() {
    try {
      await resetProfile();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <main className="profile-page" aria-label="My profile">
      <div className="profile-inner">
        <h2 className="page-title">My profile</h2>
        <section className="howto" aria-label="How your profile works">
          <h3 className="phase-heading">How your profile works</h3>
          <dl>
            <dt>What is tracked</dt>
            <dd>
              Every time you press Compile, the assistant notes whether the program compiled, how many errors and
              warnings it had, and which kinds of mistakes caused them. Only these counts are kept. Your code is never
              stored.
            </dd>
            <dt>How explanations adapt</dt>
            <dd>
              Each error belongs to a category, such as <em>missing-semicolon</em> or <em>undeclared-identifier</em>.
              When you make the same kind of mistake {profile?.threshold ?? 3} or more times, pressing{" "}
              <strong>Explain</strong> in Auto mode gives a fuller, beginner-friendly explanation with a short worked
              example. Kinds of mistakes you rarely make keep short, to-the-point explanations. Choosing Beginner or
              Expert in the header always overrides this.
            </dd>
            <dt>Privacy</dt>
            <dd>
              Everything is stored on this computer under a random id (<code>{studentId()}</code>), not your name, and
              it is never sent to the AI model. Reset clears it all.
            </dd>
          </dl>
        </section>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        <h3 className="phase-heading">Progress</h3>
        {analytics ? <Dashboard data={analytics} /> : !error && <p className="note">Loading...</p>}

        <h3 className="phase-heading">Error categories</h3>
        {profile && profile.categories.length === 0 && <p className="note">No errors recorded yet.</p>}
        {profile && profile.categories.length > 0 && (
          <table aria-label="Error categories">
            <thead>
              <tr>
                <th>Category</th>
                <th>Hits</th>
                <th>Explanation style</th>
              </tr>
            </thead>
            <tbody>
              {profile.categories.map((c) => (
                <tr key={c.category}>
                  <td>{c.category}</td>
                  <td>{c.hits}</td>
                  <td>{c.depth === "full" ? "Fuller, with a worked example" : `Short (fuller after ${profile.threshold})`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p>
          <button type="button" onClick={onReset}>
            Reset my profile
          </button>
        </p>
      </div>
    </main>
  );
}
