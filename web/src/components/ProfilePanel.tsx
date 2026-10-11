// F9: the student's own profile: how many times each error category was hit, which
// ones get fuller explanations, and a reset button. The id is a random token kept
// in this browser (see api.ts); nothing here names the student.
import { useCallback, useEffect, useState } from "react";
import { getProfile, resetProfile, studentId } from "../api";
import type { ProfileView } from "../types";

interface Props {
  refreshKey: number; // bumped after each compile so the counts stay current
}

export default function ProfilePanel({ refreshKey }: Props) {
  const [open, setOpen] = useState(false);
  const [profile, setProfile] = useState<ProfileView | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setProfile(await getProfile());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, refreshKey, load]);

  async function onReset() {
    try {
      setProfile(await resetProfile());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section className="profile" aria-label="My error profile">
      <button type="button" className="related" aria-expanded={open} onClick={() => setOpen(!open)}>
        My profile
      </button>
      {open && (
        <div className="profile-body">
          <p className="note">
            Stored only on this computer under a random id (<code>{studentId()}</code>). A category you hit{" "}
            {profile?.threshold ?? 3} or more times gets fuller explanations with a worked example.
          </p>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {profile && profile.categories.length === 0 && <p className="note">No errors recorded yet.</p>}
          {profile && profile.categories.length > 0 && (
            <table aria-label="Error categories">
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Hits</th>
                  <th>Explanations</th>
                </tr>
              </thead>
              <tbody>
                {profile.categories.map((c) => (
                  <tr key={c.category}>
                    <td>{c.category}</td>
                    <td>{c.hits}</td>
                    <td>{c.depth === "full" ? "fuller, with example" : "short"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button type="button" onClick={onReset}>
            Reset my profile
          </button>
        </div>
      )}
    </section>
  );
}
