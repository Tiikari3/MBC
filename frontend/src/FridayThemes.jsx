import { useCallback, useEffect, useMemo, useState } from 'react';

const API_URL = import.meta.env.VITE_API_URL;
const tokenFromStorage = () => localStorage.getItem('moosic_token');

async function apiRequest(path, options = {}) {
  const token = tokenFromStorage();
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Something went wrong. Please try again.');
  return data;
}

const buttonStyle = (active = false, disabled = false) => ({
  border: `1px solid ${active ? 'var(--accent-green)' : 'var(--border-color)'}`,
  background: active ? 'color-mix(in srgb, var(--accent-green) 16%, var(--bg-card))' : 'var(--bg-card)',
  color: 'var(--text-primary)',
  borderRadius: '10px',
  padding: '0.7rem 1rem',
  fontWeight: 650,
  cursor: disabled ? 'not-allowed' : 'pointer',
  opacity: disabled ? 0.55 : 1,
});

const cardStyle = {
  border: '1px solid var(--border-color)',
  borderRadius: '14px',
  background: 'var(--bg-card)',
  padding: '1.1rem',
};

function ProposalCard({ proposal, onVote, busy }) {
  const decided = proposal.status === 'approved' || proposal.status === 'denied';
  return (
    <article style={cardStyle}>
      <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <h3 style={{ margin: '0 0 0.35rem', fontSize: '1.1rem' }}>{proposal.name}</h3>
          <p style={{ margin: '0 0 0.7rem', color: 'var(--text-muted)', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{proposal.description}</p>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
            Proposed by {proposal.proposer_username} · {proposal.vote_count} vote{proposal.vote_count === 1 ? '' : 's'}
          </div>
        </div>
        <span style={{ fontSize: '0.75rem', fontWeight: 750, borderRadius: '999px', padding: '0.35rem 0.6rem', color: proposal.status === 'approved' ? '#26864b' : proposal.status === 'denied' ? '#c14d4d' : 'var(--text-muted)', background: proposal.status === 'approved' ? 'rgba(38,134,75,.12)' : proposal.status === 'denied' ? 'rgba(193,77,77,.12)' : 'var(--bg-secondary)' }}>
          {proposal.status === 'approved' ? 'Approved · on wheel' : proposal.status === 'denied' ? 'Not approved' : 'Open for voting'}
        </span>
      </div>
      <div style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap', alignItems: 'center', marginTop: '1rem' }}>
        <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>👍 {proposal.yes_count} · 👎 {proposal.no_count}</span>
        {!decided && <>
          <button type="button" style={buttonStyle(proposal.current_user_vote === true, busy)} disabled={busy} onClick={() => onVote(proposal, true)}>👍 Vote yes</button>
          <button type="button" style={buttonStyle(proposal.current_user_vote === false, busy)} disabled={busy} onClick={() => onVote(proposal, false)}>👎 Vote no</button>
        </>}
        {decided && <span style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>Voting is closed.</span>}
      </div>
    </article>
  );
}

export default function FridayThemes({ currentUser, onGoToLogin }) {
  const [tab, setTab] = useState('proposals');
  const [proposals, setProposals] = useState([]);
  const [wheel, setWheel] = useState({ available: [], latest_selection: null, can_spin: false });
  const [history, setHistory] = useState([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [spinning, setSpinning] = useState(false);
  const [wheelRotation, setWheelRotation] = useState(0);
  const [lastWinner, setLastWinner] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const loggedIn = Boolean(currentUser && tokenFromStorage());
  const wheelColors = ['#3F8058', '#3268A5', '#AD5275', '#8054A6', '#A95038', '#946A13'];
  const wheelGradient = useMemo(() => {
    const count = Math.max(wheel.available.length, 1);
    const segment = 360 / count;
    const stops = Array.from({ length: count }, (_, i) => `${wheelColors[i % wheelColors.length]} ${i * segment}deg ${(i + 1) * segment}deg`);
    return `conic-gradient(${stops.join(', ')})`;
  }, [wheel.available.length]);

  const refreshAll = useCallback(async () => {
    if (!loggedIn) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const [proposalData, wheelData, historyData] = await Promise.all([
        apiRequest('/api/friday-themes/proposals'),
        apiRequest('/api/friday-themes/wheel'),
        apiRequest('/api/friday-themes/history'),
      ]);
      setProposals(proposalData);
      setWheel(wheelData);
      setHistory(historyData);
    } catch (err) {
      setError(err.message || 'Could not load Friday Themes.');
    } finally {
      setLoading(false);
    }
  }, [loggedIn]);

  useEffect(() => { refreshAll(); }, [refreshAll]);

  const submitProposal = async (event) => {
    event.preventDefault();
    if (!loggedIn) { onGoToLogin?.(); return; }
    setSubmitting(true); setError(''); setNotice('');
    try {
      await apiRequest('/api/friday-themes/proposals', {
        method: 'POST', body: JSON.stringify({ name: name.trim(), description: description.trim() }),
      });
      setName(''); setDescription('');
      setNotice('Your theme proposal has been added for voting.');
      await refreshAll();
    } catch (err) { setError(err.message); }
    finally { setSubmitting(false); }
  };

  const castVote = async (proposal, inFavor) => {
    if (!loggedIn) { onGoToLogin?.(); return; }
    setBusyId(proposal.id); setError(''); setNotice('');
    try {
      if (proposal.current_user_vote === inFavor) {
        await apiRequest(`/api/friday-themes/proposals/${proposal.id}/vote`, { method: 'DELETE' });
      } else {
        await apiRequest(`/api/friday-themes/proposals/${proposal.id}/vote`, {
          method: 'POST', body: JSON.stringify({ in_favor: inFavor }),
        });
      }
      await refreshAll();
    } catch (err) { setError(err.message); }
    finally { setBusyId(null); }
  };

  const spinWheel = async () => {
    if (!wheel.can_spin || spinning) return;
    setSpinning(true); setError(''); setNotice(''); setLastWinner(null);
    const spinAnimation = new Promise(resolve => setTimeout(resolve, 3000));
    const startingRotation = wheelRotation;
    setWheelRotation(startingRotation + 1440 + Math.floor(Math.random() * 720) + 360);
    try {
      const [result] = await Promise.all([
        apiRequest('/api/friday-themes/wheel/spin', { method: 'POST' }),
        spinAnimation,
      ]);
      setLastWinner(result.selection);
      setNotice(`The selected theme is “${result.selection.name}”!`);
      await refreshAll();
    } catch (err) {
      await spinAnimation;
      setError(err.message);
    } finally { setSpinning(false); }
  };

  const tabs = [
    { id: 'proposals', label: 'Proposals & Voting' },
    { id: 'wheel', label: 'Theme Wheel' },
    { id: 'history', label: 'Theme History' },
  ];

  if (!loggedIn) {
    return <section style={{ ...cardStyle, padding: '1.5rem' }}>
      <h2 style={{ marginTop: 0 }}>Friday Themes</h2>
      <p style={{ color: 'var(--text-muted)', lineHeight: 1.6 }}>Sign in to propose themes, vote with the club, view the wheel, and see past selections.</p>
      <button type="button" style={buttonStyle(true)} onClick={() => onGoToLogin?.()}>Log in to continue</button>
    </section>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
      <section style={{ ...cardStyle, padding: '1.4rem 1.5rem', background: 'color-mix(in srgb, var(--accent-green) 8%, var(--bg-card))' }}>
        <div style={{ color: 'var(--accent-green)', fontSize: '0.76rem', fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: '0.4rem' }}>MusicBookClub · Weekly tradition</div>
        <h2 style={{ margin: 0, fontSize: '1.6rem' }}>Friday Themes</h2>
        <p style={{ margin: '0.55rem 0 0', color: 'var(--text-muted)', lineHeight: 1.6, maxWidth: '760px' }}>Suggest a theme whenever inspiration strikes, vote on the club’s ideas, and let the wheel pick a winning theme. Approved themes are only selected once.</p>
      </section>

      <nav aria-label="Friday Themes sections" style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {tabs.map(item => <button key={item.id} type="button" style={buttonStyle(tab === item.id)} onClick={() => setTab(item.id)}>{item.label}</button>)}
      </nav>

      {error && <div role="alert" style={{ ...cardStyle, color: '#c14d4d', borderColor: 'rgba(193,77,77,.45)' }}>{error}</div>}
      {notice && <div role="status" style={{ ...cardStyle, color: 'var(--accent-green)', borderColor: 'color-mix(in srgb, var(--accent-green) 45%, var(--border-color))' }}>{notice}</div>}
      {loading ? <p style={{ color: 'var(--text-muted)' }}>Loading Friday Themes…</p> : <>
        {tab === 'proposals' && <div style={{ display: 'grid', gap: '1rem' }}>
          <form onSubmit={submitProposal} style={{ ...cardStyle, display: 'grid', gap: '0.85rem' }}>
            <div><h3 style={{ margin: '0 0 0.3rem' }}>Propose a theme</h3><p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.9rem' }}>Any signed-in club member can submit a proposal at any time.</p></div>
            <label style={{ display: 'grid', gap: '0.4rem', fontWeight: 650 }}>Theme name
              <input value={name} onChange={e => setName(e.target.value)} maxLength={100} required placeholder="e.g. Anime opening songs" style={{ padding: '0.8rem', border: '1px solid var(--border-color)', borderRadius: '9px', background: 'var(--bg-primary)', color: 'var(--text-primary)', font: 'inherit' }} />
            </label>
            <label style={{ display: 'grid', gap: '0.4rem', fontWeight: 650 }}>Description
              <textarea value={description} onChange={e => setDescription(e.target.value)} maxLength={1000} required rows={3} placeholder="What makes this a fun theme for the club?" style={{ padding: '0.8rem', border: '1px solid var(--border-color)', borderRadius: '9px', background: 'var(--bg-primary)', color: 'var(--text-primary)', font: 'inherit', resize: 'vertical' }} />
            </label>
            <div><button type="submit" disabled={submitting || !name.trim() || !description.trim()} style={buttonStyle(true, submitting || !name.trim() || !description.trim())}>{submitting ? 'Submitting…' : 'Submit proposal'}</button></div>
          </form>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.7rem', alignItems: 'baseline', flexWrap: 'wrap' }}><h3 style={{ margin: 0 }}>Club proposals</h3><span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>A strict majority of votes cast decides each proposal; ties remain open.</span></div>
          {proposals.length === 0 ? <div style={cardStyle}><p style={{ margin: 0, color: 'var(--text-muted)' }}>No proposals yet. Add the first one above!</p></div> : proposals.map(proposal => <ProposalCard key={proposal.id} proposal={proposal} onVote={castVote} busy={busyId === proposal.id} />)}
        </div>}

        {tab === 'wheel' && <section style={{ ...cardStyle, display: 'grid', gap: '1rem', justifyItems: 'center', textAlign: 'center', padding: '1.5rem' }}>
          <div style={{ width: '100%' }}><h3 style={{ margin: '0 0 0.35rem' }}>The Theme Wheel</h3><p style={{ margin: 0, color: 'var(--text-muted)' }}>{wheel.available.length} approved unused theme{wheel.available.length === 1 ? '' : 's'} available</p></div>
          <div style={{ position: 'relative', width: 'min(76vw, 330px)', aspectRatio: '1', display: 'grid', placeItems: 'center' }}>
            <div aria-label="Theme wheel" role="img" style={{ width: '100%', height: '100%', borderRadius: '50%', border: '7px solid var(--bg-card)', boxShadow: '0 8px 26px rgba(0,0,0,.18)', background: wheelGradient, transform: `rotate(${wheelRotation}deg)`, transition: spinning ? 'transform 3s cubic-bezier(.12,.75,.15,1)' : 'transform 0.2s ease', display: 'grid', placeItems: 'center' }}>
              <div style={{ width: '38%', aspectRatio: '1', borderRadius: '50%', background: 'var(--bg-card)', border: '3px solid var(--border-color)', display: 'grid', placeItems: 'center', color: 'var(--text-primary)', fontWeight: 850, fontSize: '0.9rem' }}>MBC</div>
            </div>
            <div style={{ position: 'absolute', top: '-4px', left: 'calc(50% - 14px)', width: 0, height: 0, borderLeft: '14px solid transparent', borderRight: '14px solid transparent', borderTop: '30px solid var(--text-primary)', zIndex: 2 }} />
          </div>
          {wheel.available.length === 0 && <p style={{ color: 'var(--text-muted)', maxWidth: '480px' }}>There are no approved unused themes yet. Approved proposals will automatically appear here.</p>}
          <button type="button" disabled={!wheel.can_spin || spinning || wheel.available.length === 0} onClick={spinWheel} style={buttonStyle(true, !wheel.can_spin || spinning || wheel.available.length === 0)}>{spinning ? 'Spinning…' : 'Spin the wheel'}</button>
          {!wheel.can_spin && <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem' }}>Only an authorized wheel spinner can run the draw.</p>}
          {lastWinner && <div style={{ ...cardStyle, width: '100%', maxWidth: '500px', borderColor: 'var(--accent-green)' }}><div style={{ color: 'var(--accent-green)', fontWeight: 800, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Selected theme</div><h2 style={{ margin: '0.4rem 0' }}>{lastWinner.name}</h2><p style={{ margin: 0, color: 'var(--text-muted)' }}>{lastWinner.description}</p></div>}
          {wheel.available.length > 0 && <div style={{ width: '100%', textAlign: 'left', marginTop: '0.4rem' }}><h4 style={{ margin: '0 0 0.65rem' }}>On the wheel</h4><div style={{ display: 'grid', gap: '0.55rem' }}>{wheel.available.map((item, index) => <div key={item.id} style={{ display: 'flex', gap: '0.65rem', alignItems: 'center', borderBottom: '1px solid var(--border-color)', padding: '0.5rem 0' }}><span style={{ width: '12px', height: '12px', borderRadius: '50%', background: wheelColors[index % wheelColors.length], flexShrink: 0 }} /><span style={{ fontWeight: 650 }}>{item.name}</span><span style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginLeft: 'auto' }}>{item.proposer_username}</span></div>)}</div></div>}
        </section>}

        {tab === 'history' && <section style={{ display: 'grid', gap: '0.8rem' }}><div><h3 style={{ margin: '0 0 0.3rem' }}>Theme History</h3><p style={{ margin: 0, color: 'var(--text-muted)' }}>Past wheel selections are saved here and cannot be selected again.</p></div>
          {history.length === 0 ? <div style={cardStyle}><p style={{ margin: 0, color: 'var(--text-muted)' }}>No themes have been selected by the wheel yet.</p></div> : history.map((item, index) => <article key={`${item.id}-${item.selected_at}`} style={cardStyle}><div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.8rem', flexWrap: 'wrap' }}><h3 style={{ margin: 0 }}>{item.name}</h3><span style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>#{history.length - index}</span></div><p style={{ margin: '0.55rem 0', color: 'var(--text-muted)', lineHeight: 1.5 }}>{item.description}</p><div style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>Selected {item.selected_at ? new Date(item.selected_at).toLocaleString() : 'date unavailable'} · proposed by {item.proposer_username} · spun by {item.spun_by || 'Unknown'}</div></article>)}
        </section>}
      </>}
    </div>
  );
}
