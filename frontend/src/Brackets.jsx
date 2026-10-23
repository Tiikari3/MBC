import { useCallback, useEffect, useState } from 'react';
import './index.css';

const USER_COLORS = {
  loganworsdell: '#9fc5e8',
  parker: '#b4a7d6',
  papipetro: '#dd7e6b',
  rosey0316: '#ffc7ce',
  typiont814: '#93c47d',
  westonmiller: '#ffe599',
  awesomegear3: '#f6b26b',
  flocco: '#b7e1cd',
};

const getUserColor = (username) =>
  USER_COLORS[username?.toLowerCase()] || '#ffffff';

const API = import.meta.env.VITE_API_URL;
const MONTHS = [
  'January', 'February', 'March', 'April',
  'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'
];

export default function Brackets({ currentUser, onGoToLogin }) {
  const [brackets, setBrackets] = useState([]);
  const [years, setYears] = useState([]);
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [month, setMonth] = useState(String(new Date().getMonth() + 1));
  const [bracketType, setBracketType] = useState('month');
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const token = localStorage.getItem('moosic_token');

  const apiRequest = useCallback(async (path, options = {}) => {
    const response = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${localStorage.getItem('moosic_token')}`,
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    });

    const data = await response.json().catch(() => ({}));

    if (response.status === 401) {
      onGoToLogin?.();
      throw new Error('Please log in again to continue.');
    }

    if (!response.ok) {
      throw new Error(data.detail || 'The bracket request failed.');
    }

    return data;
  }, [onGoToLogin]);

  const loadData = useCallback(async ({ silent = false } = {}) => {
    if (!localStorage.getItem('moosic_token')) {
      setLoading(false);
      return;
    }

    if (!silent) {
      setLoading(true);
    }

    try {
      const [bracketData, yearData, permissions] = await Promise.all([
        apiRequest('/api/brackets'),
        apiRequest('/api/brackets/available-years'),
        apiRequest('/api/brackets/permissions'),
      ]);

      setBrackets(bracketData);
      setYears(yearData.years || []);
      setIsAdmin(Boolean(permissions.is_admin));

      if (!silent) {
        setError('');
      }
    
    } catch (err) {
      // Don't repeatedly flash an error during background refreshes.
      if (!silent) {
        setError(err.message);
      }
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }, [apiRequest]);

  useEffect(() => {
    const refreshInterval = setInterval(() => {
      // Refresh the data without showing the full-page loading state.
      loadData({ silent: true });
    }, 5000);

    return () => clearInterval(refreshInterval);
  }, [loadData]);

  const selectedBracket = brackets.find((item) =>
    item.year === Number(year) &&
    item.bracket_type === bracketType &&
    (bracketType === 'year' || item.month === Number(month))
  );

  const saveBracket = (updated) => {
    setBrackets((previous) => {
      const exists = previous.some((item) => item.id === updated.id);
      return exists
        ? previous.map((item) => item.id === updated.id ? updated : item)
        : [...previous, updated];
    });
  };

  const createBracket = async () => {
    setBusy(true);
    setError('');
    setNotice('');

    try {
      const created = await apiRequest('/api/brackets', {
        method: 'POST',
        body: JSON.stringify({
          bracket_type: bracketType,
          year: Number(year),
          month: bracketType === 'month' ? Number(month) : null,
        }),
      });

      saveBracket(created);
      setNotice('Bracket created successfully.');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const changeTarget = async (value) => {
    if (!selectedBracket) return;

    setBusy(true);
    setError('');
    setNotice('');

    try {
      const updated = await apiRequest(
        `/api/brackets/${selectedBracket.id}/voter-target`,
        {
          method: 'PUT',
          body: JSON.stringify({ voter_target: Number(value) }),
        }
      );

      saveBracket(updated);
      setNotice(`Voting target changed to ${value}.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const castVote = async (match, songId) => {
    if (!currentUser) {
      onGoToLogin?.();
      return;
    }

    setBusy(true);
    setError('');
    setNotice('');

    try {
      const updated = await apiRequest(
        `/api/brackets/${selectedBracket.id}/matches/${match.id}/vote`,
        {
          method: 'POST',
          body: JSON.stringify({ song_id: songId }),
        }
      );

      saveBracket(updated);
      setNotice('Your vote has been saved.');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const cardStyle = {
    background: 'var(--bg-card)',
    border: '1px solid var(--border-color)',
    borderRadius: '12px',
    padding: '1rem',
  };

  const buttonStyle = (active = false) => ({
    background: active ? 'var(--accent-green)' : 'var(--bg-secondary)',
    color: active ? 'var(--accent-button-text)' : 'var(--text-main)',
    border: '1px solid var(--border-color)',
    borderRadius: '8px',
    padding: '0.65rem 0.9rem',
    cursor: 'pointer',
    fontWeight: 700,
  });

  const selectStyle = {
    background: 'var(--bg-secondary)',
    color: 'var(--text-main)',
    border: '1px solid var(--border-color)',
    borderRadius: '8px',
    padding: '0.65rem',
    fontSize: '1rem',
  };

  if (!token || !currentUser) {
    return (
      <section style={cardStyle}>
        <h2 style={{ marginTop: 0 }}>Brackets</h2>
        <p>Log in to vote in Song of the Month and Song of the Year brackets.</p>
        <button style={buttonStyle(true)} onClick={onGoToLogin}>
          Log in
        </button>
      </section>
    );
  }

  const yearOptions = [...new Set([
    ...years,
    ...brackets.map((item) => item.year),
    new Date().getFullYear(),
  ])].sort((a, b) => b - a);

  const rounds = selectedBracket
    ? [...new Set(selectedBracket.matches.map((match) => match.round_number))]
        .sort((a, b) => a - b)
    : [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <section style={{ ...cardStyle, padding: '1.4rem' }}>
        <h2 style={{ margin: 0 }}>Brackets</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: 0 }}>
          Vote head-to-head. Winners advance until one song becomes champion.
        </p>

        <div style={{
          display: 'flex',
          gap: '0.8rem',
          flexWrap: 'wrap',
          alignItems: 'center',
          marginTop: '1.2rem',
        }}>
          <label>
            Year{' '}
            <select
              value={year}
              onChange={(event) => setYear(event.target.value)}
              style={selectStyle}
            >
              {yearOptions.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </label>

          {isAdmin && selectedBracket && selectedBracket.status !== 'complete' && (
            <label>
              Voter target{' '}
              <select
                value={selectedBracket.voter_target}
                disabled={busy}
                onChange={(event) => changeTarget(event.target.value)}
                style={selectStyle}
              >
                {[1, 2, 3, 4, 5, 6, 7, 8].map((number) => (
                  <option key={number} value={number}>{number}</option>
                ))}
              </select>
            </label>
          )}
        </div>
      </section>

      <nav aria-label="Bracket type" style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <button
          style={buttonStyle(bracketType === 'month')}
          onClick={() => setBracketType('month')}
        >
          Song of the Month
        </button>
        <button
          style={buttonStyle(bracketType === 'year')}
          onClick={() => setBracketType('year')}
        >
          Song of the Year
        </button>
      </nav>

      {bracketType === 'month' && (
        <nav aria-label="Bracket month" style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
          {MONTHS.map((name, index) => (
            <button
              key={name}
              style={buttonStyle(month === String(index + 1))}
              onClick={() => setMonth(String(index + 1))}
            >
              {name.slice(0, 3)}
            </button>
          ))}
        </nav>
      )}

      {error && (
        <div role="alert" style={{ ...cardStyle, color: '#ff6b6b' }}>
          {error}
        </div>
      )}
      {notice && (
        <div role="status" style={{ ...cardStyle, color: 'var(--accent-green)' }}>
          {notice}
        </div>
      )}

      {loading ? (
        <section style={cardStyle}>Loading brackets…</section>
      ) : selectedBracket ? (
        <>
          <section style={cardStyle}>
            <h3 style={{ marginTop: 0 }}>
              {bracketType === 'year'
                ? `${year} Song of the Year`
                : `${MONTHS[Number(month) - 1]} ${year} · Song of the Month`}
            </h3>
            <p style={{ color: 'var(--text-muted)' }}>
              {selectedBracket.status === 'complete'
                ? 'Bracket completed'
                : `Target: ${selectedBracket.voter_target} votes per matchup. Ties stay open for an additional vote.`}
            </p>

            {selectedBracket.champion && (
              <div style={{
                padding: '1rem',
                borderRadius: '10px',
                background: 'var(--bg-secondary)',
                border: '1px solid var(--accent-green)',
              }}>
                <strong>🏆 Champion</strong>
                <div style={{ fontSize: '1.15rem', marginTop: '0.4rem' }}>
                  {selectedBracket.champion.title} — {selectedBracket.champion.artist}
                </div>
              </div>
            )}
          </section>

          {rounds.map((roundNumber) => {
            const matches = selectedBracket.matches.filter((match) => {
              if (match.round_number !== roundNumber) {
                return false;
              }

              // Hide automatic Round 1 byes from the visible bracket.
              const isRoundOneBye =
                match.round_number === 1 &&
                match.status === 'complete' &&
                match.winner_song_id != null &&
                (!match.song_a || !match.song_b);

              return !isRoundOneBye;
            });

            if (matches.length === 0) {
              return null;
            }

            return (
              <section key={roundNumber} style={cardStyle}>
                <h3 style={{ marginTop: 0 }}>Round {roundNumber}</h3>

                <div style={{ display: 'grid', gap: '1rem' }}>
                  {matches.map((match) => {
                    const a = match.song_a;
                    const b = match.song_b;
                    const tied = match.song_a_votes === match.song_b_votes;

                    return (
                      <article
                        key={match.id}
                        style={{
                          background: 'var(--bg-primary)',
                          border: '1px solid var(--border-color)',
                          borderRadius: '10px',
                          padding: '1rem',
                        }}
                      >
                        <div style={{
                          display: 'grid',
                          gridTemplateColumns: 'minmax(0, 1fr) auto minmax(0, 1fr)',
                          gap: '0.7rem',
                          alignItems: 'stretch',
                        }}>
                          {[a, b].map((song, index) => {
                            const songId = song?.id;
                            const count = index === 0
                              ? match.song_a_votes
                              : match.song_b_votes;
                            const voters = index === 0
                              ? match.song_a_voters
                              : match.song_b_voters;
                            const won = songId === match.winner_song_id;

                            const hasVotedForThisSong =
                              songId != null &&
                              match.current_user_vote_song_id === songId;

                            const canVote =
                              match.status === 'open' &&
                              songId != null;

                            const disabled =
                              busy ||
                              !canVote ||
                              hasVotedForThisSong;

                            const songColor = getUserColor(song?.submittedBy);
                            const songColumn = index === 0 ? '1' : '3';
                            
                            return (
                              <div key={songId || `bye-${index}`} style={{
                                gridColumn: songColumn,
                                gridRow: '1',
                                border: `1px solid ${songColor}`,
                                borderRadius: '8px',
                                padding: '0.8rem',
                                minWidth: 0,
                                backgroundColor: song ? `${songColor}33` : 'transparent',
                              }}>
                                <div style={{ fontWeight: 800 }}>
                                  {song
                                    ? `${song.title} — ${song.artist}`
                                    : match.status === 'pending'
                                      ? 'TBD'
                                      : 'BYE'}
                                </div>

                                {song && (
                                  <>
                                    <div style={{
                                      fontSize: '1.4rem',
                                      fontWeight: 800,
                                      margin: '0.5rem 0',
                                    }}>
                                      {count} {count === 1 ? 'vote' : 'votes'}
                                    </div>

                                    {song.spotify_url && (
                                      <a
                                        href={song.spotify_url}
                                        target="_blank"
                                        rel="noreferrer"
                                        style={{ color: 'var(--accent-green)' }}
                                      >
                                        Listen on Spotify
                                      </a>
                                    )}

                                    {match.status == 'open' && (
                                      <button
                                        type="button"
                                        disabled={disabled}
                                        onClick={() => castVote(match, songId)}
                                        style={{
                                          ...buttonStyle(hasVotedForThisSong),
                                          display: 'block',
                                          width: '100%',
                                          marginTop: '0.8rem',
                                          opacity: disabled ? 0.7 : 1,
                                        }}
                                      >
                                        {hasVotedForThisSong ? 'Voted' : 'Vote for this song'}
                                      </button>
                                    )}

                                    {won && (
                                      <div style={{
                                        color: 'var(--accent-green)',
                                        fontWeight: 800,
                                        marginTop: '0.5rem',
                                      }}>
                                        Winner · Advances
                                      </div>
                                    )}

                                    <div style={{
                                      marginTop: '0.8rem',
                                      fontSize: '0.85rem',
                                      color: 'var(--text-muted)',
                                    }}>
                                      <strong>Voted for this song:</strong>
                                      {voters.length ? (
                                        <ul style={{ margin: '0.35rem 0 0', paddingLeft: '1.2rem' }}>
                                          {voters.map((voter) => (
                                            <li key={voter.user_id}>{voter.username}</li>
                                          ))}
                                        </ul>
                                      ) : (
                                        <div>No votes yet</div>
                                      )}
                                    </div>
                                  </>
                                )}
                              </div>
                            );
                          })}

                          <div style={{
                            alignSelf: 'center',
                            fontWeight: 800,
                            color: 'var(--text-muted)',
                            gridColumn: '2',
                            gridRow: '1',
                            textAlign: 'center',
                          }}>
                            VS
                          </div>
                        </div>

                        {match.status === 'open' && (
                          <p style={{ color: 'var(--text-muted)', marginBottom: 0 }}>
                            {tied
                              ? `${match.votes_cast} vote${match.votes_cast === 1 ? '' : 's'} cast — tied, matchup remains open`
                              : `${match.votes_cast} vote${match.votes_cast === 1 ? '' : 's'} cast — first song to reach ${Math.floor(selectedBracket.voter_target / 2) + 1} votes wins`}
                          </p>
                        )}
                      </article>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </>
      ) : (
        <section style={cardStyle}>
          <h3 style={{ marginTop: 0 }}>No bracket created yet</h3>
          <p style={{ color: 'var(--text-muted)' }}>
            {bracketType === 'year'
              ? `Create the ${year} Song of the Year bracket from every regular daily competition winner that year.`
              : `Create the ${MONTHS[Number(month) - 1]} ${year} Song of the Month bracket from every regular daily competition winner that month.`}
          </p>

          {isAdmin ? (
            <button
              type="button"
              disabled={busy}
              onClick={createBracket}
              style={{ ...buttonStyle(true), opacity: busy ? 0.6 : 1 }}
            >
              {busy ? 'Creating…' : 'Create bracket'}
            </button>
          ) : (
            <p>Ask the bracket administrator to create this bracket.</p>
          )}
        </section>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button type="button" onClick={loadData} style={buttonStyle(false)}>
          Refresh brackets
        </button>
      </div>
    </div>
  );
}