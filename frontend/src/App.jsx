import { useEffect, useState, useCallback } from 'react';
import './App.css';

const REPORT_URL = '/api/report';

const STATUS_META = {
  pass: { label: 'Clean sheet', card: 'none', color: 'var(--pass)', bg: 'var(--pass-bg)' },
  recover: { label: 'Advantage played', card: 'blue', color: 'var(--recover)', bg: 'var(--recover-bg)' },
  quarantine: { label: 'Caution', card: 'yellow', color: 'var(--caution)', bg: 'var(--caution-bg)' },
  fail: { label: 'Sent off', card: 'red', color: 'var(--sent-off)', bg: 'var(--sent-off-bg)' },
  warning: { label: 'Advisory', card: 'yellow', color: 'var(--caution)', bg: 'var(--caution-bg)' },
};

function statusMeta(status) {
  return STATUS_META[status?.toLowerCase()] ?? {
    label: 'Unknown',
    card: 'none',
    color: 'var(--text)',
    bg: 'var(--code-bg)',
    };
}

function formatTimestamp(isoString) {
  if (!isoString) return 'unknown time';
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return isoString;
  return date.toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
    });
}

function useTheme() {
  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') return 'light';
    const stored = window.localStorage?.getItem('sentinel-theme');
    if (stored === 'light' || stored === 'dark') return stored;
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage?.setItem('sentinel-theme', theme);
    } catch {
      // Private browsing or storage disabled, theme just won't persist.
    }
    }, [theme]);

  return [theme, () => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))];
}

function Card({ kind }) {
  if (kind === 'none') return null;
  return <span className={`ref-card ref-card--${kind}`} aria-hidden="true" />;
}

function StatCell({ label, value }) {
  return (
    <div className="stat-cell">
      <span className="stat-value">{value ?? 0}</span>
      <span className="stat-label">{label}</span>
    </div>
    );
}

export default function App() {
  const [theme, toggleTheme] = useTheme();
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchReport = useCallback(() => {
    setLoading(true);
    setError(null);

    fetch(REPORT_URL)
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body?.error || `request failed with status ${response.status}`);
        }
        return response.json();
        })
      .then((data) => setReport(data))
      .catch((err) => setError(err.message || 'could not reach the Sentinel server'))
      .finally(() => setLoading(false));
    }, []);

  useEffect(() => {
    fetchReport();
    }, [fetchReport]);

  const meta = statusMeta(report?.status);
  const records = report?.records ?? {};
  const validationErrors = report?.validation?.errors ?? [];
  const drift = report?.drift ?? { detected: false, missing: [], unexpected: [] };
  const duplicates = report?.duplicates ?? [];

  return (
    <div className="sentinel">
      <header className="sentinel-header">
        <div className="eyebrow">Football Data Sentinel</div>
        <h1>Match report</h1>
        <p className="subtitle">Self-healing validation for scraped Championship data</p>
        <button
          type="button"
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          {theme === 'dark' ? 'Light mode' : 'Dark mode'}
        </button>
      </header>

      {loading && <p className="state-line">Reading the latest run…</p>}

      {!loading && error && (
        <div className="state-line state-line--error">
          <p>Sentinel server unreachable: {error}</p>
          <button type="button" onClick={fetchReport}>Retry</button>
        </div>
        )}

      {!loading && !error && report && (
        <>
          <section className="status-panel" style={{ background: meta.bg, borderColor: meta.color }}>
            <Card kind={meta.card} />
            <div>
              <div className="status-word" style={{ color: meta.color }}>
                {report.status?.toUpperCase() ?? 'UNKNOWN'}
              </div>
              <div className="status-label">{meta.label}</div>
            </div>
            <button type="button" className="refresh-button" onClick={fetchReport}>
              Refresh
            </button>
          </section>

          <section className="stat-strip">
            <StatCell label="Raw rows" value={records.raw} />
            <StatCell label="Player rows" value={records.player_rows} />
            <StatCell label="Recovered" value={records.recovered} />
            <StatCell label="Quarantined" value={records.quarantined} />
            <StatCell label="Trusted" value={records.final_trusted} />
          </section>

          <section className="detail-grid">
            <div className="detail-card">
              <h2>Schema drift</h2>
              {drift.detected ? (
                <>
                  {drift.missing?.length > 0 && (
                    <p><strong>Missing:</strong> {drift.missing.join(', ')}</p>
                    )}
                  {drift.unexpected?.length > 0 && (
                    <p><strong>Unexpected:</strong> {drift.unexpected.join(', ')}</p>
                    )}
                </>
                ) : (
                <p className="ok-line">No schema drift detected.</p>
                )}
            </div>

            <div className="detail-card">
              <h2>Validation errors</h2>
              {validationErrors.length > 0 ? (
                <ul className="error-list">
                  {validationErrors.slice(0, 12).map((err, index) => (
                    <li key={index}>{err}</li>
                    ))}
                  {validationErrors.length > 12 && (
                    <li className="error-list-more">
                      +{validationErrors.length - 12} more, see data/quarantine/players.json
                    </li>
                    )}
                </ul>
                ) : (
                <p className="ok-line">Dataset fully validated.</p>
                )}
            </div>
          </section>

          {duplicates.length > 0 && (
            <section className="detail-card">
              <h2>Possible duplicates</h2>
              <ul className="error-list">
                {duplicates.slice(0, 8).map((dup, index) => (
                  <li key={index}>
                    {dup.player_name ?? 'unknown player'}
                    {dup.squads ? ` — ${dup.squads.join(', ')}` : ''}
                    {dup.likely_transfer ? ' (likely transfer)' : ''}
                  </li>
                  ))}
              </ul>
            </section>
            )}

          <footer className="sentinel-footer">
            <span>
              schema {report?.schema?.name ?? 'unknown'} v{report?.schema?.version ?? '?'}
            </span>
            <span>collected {formatTimestamp(report?.collected_at)}</span>
          </footer>
        </>
        )}
    </div>
    );
}
