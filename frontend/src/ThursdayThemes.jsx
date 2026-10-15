import { useEffect, useMemo, useState } from 'react';

const USER_COLORS = {
  alappatjoe: '#4ade80',
  danram: '#60a5fa',
  loganworsdell: '#fde047',
  samuelbattista: '#9ca3af',
  currydestroyer27: '#ffb085'
};

const getUserColor = (username) =>
  USER_COLORS[username?.toLowerCase()] || '#ffffff';

const getTodayString = () => {
  const today = new Date();
  return new Date(
    today.getTime() -
      today.getTimezoneOffset() * 60000
  )
    .toISOString()
    .split('T')[0];
};

const parseLocalDate = (value) => {
  const [year, month, day] = value
    .split('-')
    .map(Number);
  return new Date(year, month - 1, day);
};

const formatDate = (value) =>
  parseLocalDate(value).toLocaleDateString(
    undefined,
    {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      year: 'numeric'
    }
  );

const toDateString = (dateValue) =>
  new Date(
    dateValue.getTime() -
      dateValue.getTimezoneOffset() * 60000
  )
    .toISOString()
    .split('T')[0];

const getNextThursday = () => {
  const today = new Date();
  const daysUntilThursday =
    (4 - today.getDay() + 7) % 7;

  const next = new Date(today);
  next.setHours(0, 0, 0, 0);
  next.setDate(
    today.getDate() + daysUntilThursday
  );

  return toDateString(next);
};

const ROTATION_START_DATE = '2026-09-17';

const getThursdayDates = (count = 12) => {
  const first = parseLocalDate(
    getNextThursday()
  );

  return Array.from(
    { length: count },
    (_, index) => {
      const next = new Date(first);
      next.setDate(
        first.getDate() + index * 7
      );
      return toDateString(next);
    }
  );
};

const getAllThursdayDates = (futureCount = 12) => {
  const start = parseLocalDate(ROTATION_START_DATE);
  const futureDates = getThursdayDates(futureCount);
  const futureEnd = parseLocalDate(
    futureDates[futureDates.length - 1]
  );

  const dates = [];
  const cursor = new Date(start);

  while (cursor <= futureEnd) {
    dates.push(toDateString(cursor));
    cursor.setDate(cursor.getDate() + 7);
  }

  futureDates.forEach((dateValue) => {
    if (!dates.includes(dateValue)) {
      dates.push(dateValue);
    }
  });

  return dates.sort();
};

const statusMeta = {
  approved: {
    label: 'Approved',
    symbol: '✓',
    color: '#1db954',
    background:
      'rgba(29,185,84,0.12)'
  },
  denied: {
    label: 'Denied',
    symbol: '×',
    color: '#ff6b6b',
    background:
      'rgba(255,107,107,0.12)'
  },
  pending: {
    label: 'Voting',
    symbol: '•',
    color: '#facc15',
    background:
      'rgba(250,204,21,0.10)'
  },
  skipped: {
    label: 'Skipped',
    symbol: '—',
    color: '#9ca3af',
    background:
      'rgba(156,163,175,0.10)'
  }
};

const getStatusMeta = (status) =>
  statusMeta[status] || statusMeta.pending;

function ThemeVotePills({
  theme,
  onVote,
  isSaving
}) {
  if (!theme.exists || !theme.name) {
    return null;
  }

  return (
    <div
      style={{
        display: 'flex',
        gap: '0.5rem',
        flexWrap: 'wrap',
        alignItems: 'center'
      }}
    >
      {theme.votes.map((vote) => {
        const color = getUserColor(
          vote.username
        );

        return (
          <div
            key={vote.username}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.45rem',
              padding:
                '0.4rem 0.65rem',
              borderRadius: '999px',
              background:
                'var(--bg-card)',
              border: `1px solid ${color}50`
            }}
          >
            <span
              style={{
                color,
                fontSize: '0.78rem',
                fontWeight: 600
              }}
            >
              {vote.username}
            </span>
            <span
              style={{
                color: vote.in_favor
                  ? '#1db954'
                  : '#ff6b6b',
                fontSize: '0.8rem',
                fontWeight: 'bold'
              }}
            >
              {vote.in_favor
                ? 'IN FAVOR'
                : 'DENIED'}
            </span>
          </div>
        );
      })}

      {theme.current_user_vote === null &&
        theme.status === 'pending' && (
          <span
            style={{
              color:
                'var(--text-muted)',
              fontSize: '0.8rem'
            }}
          >
            Your vote is still open
          </span>
        )}
    </div>
  );
}

function ThemeCard({
  theme,
  currentUser,
  onSaveTheme,
  onVote,
  onSkip,
  busyDate,
  editingDate,
  isPast,
  setEditingDate,
  editName,
  setEditName,
  editDescription,
  setEditDescription
}) {
  const status = getStatusMeta(
    theme.status
  );
  const isProposer =
    currentUser &&
    Number(currentUser.id) ===
      Number(theme.proposer_id);
  const canEdit =
    !isPast &&
    isProposer &&
    theme.status === 'pending';
  const hasTheme =
    Boolean(theme.exists && theme.name);
  const isBusy = busyDate === theme.date;
  const isEditing =
    editingDate === theme.date;

  const beginEditing = () => {
    setEditingDate(theme.date);
    setEditName(theme.name || '');
    setEditDescription(
      theme.description || ''
    );
  };

  return (
    <article
      style={{
        background:
          'var(--bg-card)',
        border:
          `1px solid ${
            theme.status === 'approved'
              ? 'rgba(29,185,84,0.35)'
              : 'var(--border-color)'
          }`,
        borderRadius:
          'var(--border-radius-lg)',
        padding: '1.35rem',
        boxShadow:
          '0 8px 30px rgba(0,0,0,0.12)'
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent:
            'space-between',
          gap: '1rem',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          marginBottom: '1rem'
        }}
      >
        <div>
          <div
            style={{
              color:
                'var(--text-muted)',
              fontSize: '0.76rem',
              textTransform:
                'uppercase',
              letterSpacing:
                '0.08em',
              marginBottom:
                '0.35rem'
            }}
          >
            {formatDate(theme.date)}
          </div>
          <h3
            style={{
              margin: 0,
              fontSize: '1.35rem'
            }}
          >
            {hasTheme
              ? theme.name
              : theme.status ===
                'skipped'
              ? 'Thursday skipped'
              : 'Theme not proposed yet'}
          </h3>
          <div
            style={{
              marginTop: '0.45rem',
              color:
                'var(--text-muted)',
              fontSize: '0.88rem'
            }}
          >
            Proposer:{' '}
            <strong
              style={{
                color:
                  getUserColor(
                    theme.proposer_username ||
                      theme.expected_proposer_username
                  )
              }}
            >
              {theme.proposer_username ||
                theme.expected_proposer_username ||
                'No users'}
            </strong>
          </div>
        </div>

        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding:
              '0.4rem 0.7rem',
            borderRadius: '999px',
            color: status.color,
            background:
              status.background,
            border:
              `1px solid ${status.color}40`,
            fontSize: '0.78rem',
            fontWeight: '700'
          }}
        >
          <span>{status.symbol}</span>
          {status.label}
        </span>
      </div>

      {hasTheme && (
        <div
          style={{
            marginBottom: '1rem'
          }}
        >
          <p
            style={{
              margin: 0,
              lineHeight: 1.6,
              color:
                'var(--text-main)',
              whiteSpace: 'pre-wrap'
            }}
          >
            {theme.description}
          </p>
        </div>
      )}

      {!hasTheme &&
        theme.status === 'pending' &&
        currentUser &&
        !isProposer && (
          <div
            style={{
              color:
                'var(--text-muted)',
              padding:
                '0.85rem 1rem',
              borderRadius: '10px',
              background:
                'var(--bg-secondary)',
              border:
                '1px solid var(--border-color)',
              marginBottom: '1rem'
            }}
          >
            Waiting for{' '}
            <strong
              style={{
                color:
                  getUserColor(
                    theme.expected_proposer_username
                  )
              }}
            >
              {theme.expected_proposer_username ||
                'the assigned proposer'}
            </strong>{' '}
            to pitch the theme.
          </div>
        )}

      {isEditing ? (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem',
            marginBottom: '1rem'
          }}
        >
          <input
            value={editName}
            onChange={(event) =>
              setEditName(
                event.target.value
              )
            }
            placeholder="Theme name"
            maxLength={100}
            style={{
              padding:
                '0.75rem 0.9rem',
              borderRadius: '8px',
              border:
                '1px solid var(--border-color)',
              background:
                'var(--bg-secondary)',
              color:
                'var(--text-main)',
              fontSize: '1rem'
            }}
          />
          <textarea
            value={editDescription}
            onChange={(event) =>
              setEditDescription(
                event.target.value
              )
            }
            placeholder="Describe what the theme means and what counts"
            rows={4}
            maxLength={600}
            style={{
              padding:
                '0.75rem 0.9rem',
              borderRadius: '8px',
              border:
                '1px solid var(--border-color)',
              background:
                'var(--bg-secondary)',
              color:
                'var(--text-main)',
              fontSize: '1rem',
              resize: 'vertical',
              fontFamily: 'inherit'
            }}
          />
          <div
            style={{
              display: 'flex',
              gap: '0.6rem',
              justifyContent:
                'flex-end',
              flexWrap: 'wrap'
            }}
          >
            <button
              onClick={() =>
                setEditingDate(null)
              }
              disabled={isBusy}
              style={{
                background:
                  'transparent',
                color:
                  'var(--text-muted)',
                border:
                  '1px solid var(--border-color)',
                padding:
                  '0.6rem 1rem',
                borderRadius: '8px',
                fontWeight: 'bold',
                cursor: isBusy
                  ? 'not-allowed'
                  : 'pointer'
              }}
            >
              Cancel
            </button>
            <button
              onClick={() =>
                onSaveTheme(theme.date)
              }
              disabled={
                isBusy ||
                !editName.trim() ||
                !editDescription.trim()
              }
              style={{
                background:
                  'var(--accent-green)',
                color: '#000',
                border: 'none',
                padding:
                  '0.6rem 1rem',
                borderRadius: '8px',
                fontWeight: 'bold',
                cursor:
                  isBusy ||
                  !editName.trim() ||
                  !editDescription.trim()
                    ? 'not-allowed'
                    : 'pointer',
                opacity:
                  isBusy ||
                  !editName.trim() ||
                  !editDescription.trim()
                    ? 0.55
                    : 1
              }}
            >
              {isBusy
                ? 'Saving…'
                : 'Save Theme'}
            </button>
          </div>
        </div>
      ) : (
        <>
          {canEdit &&
            currentUser && (
              <div
                style={{
                  display: 'flex',
                  gap: '0.6rem',
                  flexWrap: 'wrap',
                  marginBottom:
                    '1rem'
                }}
              >
                <button
                  onClick={beginEditing}
                  style={{
                    background:
                      'transparent',
                    color:
                      'var(--accent-green)',
                    border:
                      '1px solid var(--accent-green)',
                    padding:
                      '0.55rem 0.9rem',
                    borderRadius: '8px',
                    fontWeight: 'bold',
                    cursor: 'pointer'
                  }}
                >
                  {hasTheme
                    ? 'Edit Theme'
                    : 'Propose Theme'}
                </button>
              </div>
            )}

          {!isPast &&
            theme.status === 'pending' &&
            hasTheme &&
            currentUser && (
              <div
                style={{
                  display: 'flex',
                  gap: '0.65rem',
                  flexWrap: 'wrap',
                  alignItems: 'center',
                  marginBottom: '1rem'
                }}
              >
                <button
                  onClick={() =>
                    onVote(
                      theme.date,
                      true
                    )
                  }
                  disabled={isBusy}
                  style={{
                    background:
                      theme.current_user_vote === true
                        ? '#1db954'
                        : 'transparent',
                    color:
                      theme.current_user_vote === true
                        ? '#000'
                        : '#1db954',
                    border:
                      '1px solid #1db954',
                    padding:
                      '0.6rem 1rem',
                    borderRadius: '8px',
                    fontWeight: 'bold',
                    cursor: isBusy
                      ? 'not-allowed'
                      : 'pointer'
                  }}
                >
                  ✓ In favor
                </button>

                <button
                  onClick={() =>
                    onVote(
                      theme.date,
                      false
                    )
                  }
                  disabled={isBusy}
                  style={{
                    background:
                      theme.current_user_vote === false
                        ? '#ff6b6b'
                        : 'transparent',
                    color:
                      theme.current_user_vote === false
                        ? '#000'
                        : '#ff6b6b',
                    border:
                      '1px solid #ff6b6b',
                    padding:
                      '0.6rem 1rem',
                    borderRadius: '8px',
                    fontWeight: 'bold',
                    cursor: isBusy
                      ? 'not-allowed'
                      : 'pointer'
                  }}
                >
                  × Denied
                </button>
              </div>
            )}

          {theme.exists &&
            theme.status !==
              'pending' &&
            theme.status !==
              'skipped' && (
              <div
                style={{
                  marginBottom: '1rem',
                  color:
                    'var(--text-muted)',
                  fontSize: '0.85rem'
                }}
              >
                Voting is closed — this proposal was{' '}
                <strong
                  style={{
                    color: status.color
                  }}
                >
                  {theme.status}
                </strong>
                .
              </div>
            )}
        </>
      )}

      {hasTheme && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns:
                'repeat(3, minmax(0, 1fr))',
              gap: '0.6rem',
              marginBottom:
                '1rem'
            }}
          >
            <div
              style={{
                padding: '0.65rem',
                borderRadius: '9px',
                background:
                  'rgba(29,185,84,0.08)',
                border:
                  '1px solid rgba(29,185,84,0.18)'
              }}
            >
              <div
                style={{
                  color:
                    'var(--text-muted)',
                  fontSize: '0.72rem',
                  textTransform:
                    'uppercase'
                }}
              >
                In favor
              </div>
              <strong
                style={{
                  color: '#1db954',
                  fontSize: '1.1rem'
                }}
              >
                {theme.yes_count}
              </strong>
            </div>

            <div
              style={{
                padding: '0.65rem',
                borderRadius: '9px',
                background:
                  'rgba(255,107,107,0.08)',
                border:
                  '1px solid rgba(255,107,107,0.18)'
              }}
            >
              <div
                style={{
                  color:
                    'var(--text-muted)',
                  fontSize: '0.72rem',
                  textTransform:
                    'uppercase'
                }}
              >
                Denied
              </div>
              <strong
                style={{
                  color: '#ff6b6b',
                  fontSize: '1.1rem'
                }}
              >
                {theme.no_count}
              </strong>
            </div>

            <div
              style={{
                padding: '0.65rem',
                borderRadius: '9px',
                background:
                  'var(--bg-secondary)',
                border:
                  '1px solid var(--border-color)'
              }}
            >
              <div
                style={{
                  color:
                    'var(--text-muted)',
                  fontSize: '0.72rem',
                  textTransform:
                    'uppercase'
                }}
              >
                Majority
              </div>
              <strong
                style={{
                  fontSize: '1.1rem'
                }}
              >
                {theme.majority_needed}
              </strong>
            </div>
          </div>

          <ThemeVotePills
            theme={theme}
            onVote={onVote}
            isSaving={isBusy}
          />
        </>
      )}

      {currentUser &&
        !isPast &&
        !isEditing &&
        theme.status === 'pending' && (
          <div
            style={{
              marginTop: '1rem',
              paddingTop: '1rem',
              borderTop:
                '1px solid var(--border-color)',
              display: 'flex',
              justifyContent:
                'space-between',
              gap: '0.75rem',
              flexWrap: 'wrap',
              alignItems: 'center'
            }}
          >
            <div
              style={{
                color:
                  'var(--text-muted)',
                fontSize: '0.78rem'
              }}
            >
              {theme.vote_count}{' '}
              {theme.vote_count === 1
                ? 'vote'
                : 'votes'}{' '}
              · {theme.majority_needed}{' '}
              needed to approve
            </div>

            <button
              onClick={() =>
                onSkip(theme.date)
              }
              disabled={isBusy}
              style={{
                background:
                  'transparent',
                color:
                  'var(--text-muted)',
                border:
                  '1px solid var(--border-color)',
                padding:
                  '0.5rem 0.8rem',
                borderRadius: '7px',
                fontWeight: '600',
                fontSize: '0.78rem',
                cursor: isBusy
                  ? 'not-allowed'
                  : 'pointer'
              }}
            >
              Mark Thursday skipped
            </button>
          </div>
        )}

      {currentUser &&
        !isPast &&
        theme.status === 'skipped' && (
          <div
            style={{
              marginTop: '1rem',
              paddingTop: '1rem',
              borderTop:
                '1px solid var(--border-color)'
            }}
          >
            <div
              style={{
                color:
                  'var(--text-muted)',
                fontSize: '0.82rem',
                marginBottom:
                  '0.6rem'
              }}
            >
              This Thursday is marked as a holiday / no-theme date.
            </div>
            <button
              onClick={() =>
                onSkip(theme.date, false)
              }
              disabled={isBusy}
              style={{
                background:
                  'transparent',
                color:
                  'var(--accent-green)',
                border:
                  '1px solid var(--accent-green)',
                padding:
                  '0.5rem 0.8rem',
                borderRadius: '7px',
                fontWeight: '600',
                fontSize: '0.78rem',
                cursor: isBusy
                  ? 'not-allowed'
                  : 'pointer'
              }}
            >
              {isBusy
                ? 'Updating…'
                : 'Unskip Thursday'}
            </button>
          </div>
        )}

      {isPast && (
        <div
          style={{
            marginTop: '1rem',
            paddingTop: '1rem',
            borderTop:
              '1px solid var(--border-color)',
            color: 'var(--text-muted)',
            fontSize: '0.78rem'
          }}
        >
          Historical theme · view only
        </div>
      )}
    </article>
  );
}

export default function ThursdayThemes({
  currentUser,
  onGoToLogin
}) {
  const dates = useMemo(
    () => getAllThursdayDates(12),
    []
  );

  const startDate = ROTATION_START_DATE;
  const endDate = dates[dates.length - 1];

  const [themes, setThemes] = useState([]);
  const [isLoading, setIsLoading] =
    useState(true);
  const [loadError, setLoadError] =
    useState(null);
  const [busyDate, setBusyDate] =
    useState(null);
  const [editingDate, setEditingDate] =
    useState(null);
  const [editName, setEditName] =
    useState('');
  const [editDescription, setEditDescription] =
    useState('');

  const todayString = getTodayString();

  const pastThemes = themes
    .filter(
      (theme) =>
        theme.date < todayString &&
        (theme.exists || theme.status === 'skipped')
    )
    .sort((a, b) =>
      b.date.localeCompare(a.date)
    );

  const upcomingThemes = themes
    .filter((theme) => theme.date >= todayString)
    .sort((a, b) =>
      a.date.localeCompare(b.date)
    );

  const fetchThemes = async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const token = localStorage.getItem(
        'moosic_token'
      );

      const headers = token
        ? {
            Authorization: `Bearer ${token}`
          }
        : {};

      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/api/themes?start_date=${startDate}&end_date=${endDate}`,
        { headers }
      );

      if (!response.ok) {
        const data = await response
          .json()
          .catch(() => ({}));
        throw new Error(
          data.detail ||
            'Failed to load Thursday themes.'
        );
      }

      setThemes(await response.json());
    } catch (error) {
      console.error(error);
      setLoadError(
        error.message ||
          'Failed to load Thursday themes.'
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchThemes();
  }, [startDate, endDate]);

  const handleSaveTheme = async (targetDate) => {
    if (!currentUser) {
      onGoToLogin();
      return;
    }

    if (
      !editName.trim() ||
      !editDescription.trim()
    ) {
      return;
    }

    const token = localStorage.getItem(
      'moosic_token'
    );

    if (!token) {
      onGoToLogin();
      return;
    }

    setBusyDate(targetDate);

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/api/themes/${targetDate}`,
        {
          method: 'PUT',
          headers: {
            'Content-Type':
              'application/json',
            Authorization:
              `Bearer ${token}`
          },
          body: JSON.stringify({
            name: editName.trim(),
            description:
              editDescription.trim()
          })
        }
      );

      if (response.status === 401) {
        localStorage.removeItem(
          'moosic_token'
        );
        localStorage.removeItem(
          'moosic_user'
        );
        onGoToLogin();
        return;
      }

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        alert(
          data.detail ||
            'Failed to save theme.'
        );
        return;
      }

      setEditingDate(null);
      setEditName('');
      setEditDescription('');
      await fetchThemes();
    } catch (error) {
      console.error(error);
      alert('Error saving theme.');
    } finally {
      setBusyDate(null);
    }
  };

  const handleVote = async (
    targetDate,
    inFavor
  ) => {
    if (!currentUser) {
      onGoToLogin();
      return;
    }

    const theme = themes.find(
      (item) => item.date === targetDate
    );

    if (
      theme?.current_user_vote === inFavor
    ) {
      await handleDeleteVote(targetDate);
      return;
    }

    const token = localStorage.getItem(
      'moosic_token'
    );

    if (!token) {
      onGoToLogin();
      return;
    }

    setBusyDate(targetDate);

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/api/themes/${targetDate}/vote`,
        {
          method: 'POST',
          headers: {
            'Content-Type':
              'application/json',
            Authorization:
              `Bearer ${token}`
          },
          body: JSON.stringify({
            in_favor: inFavor
          })
        }
      );

      if (response.status === 401) {
        localStorage.removeItem(
          'moosic_token'
        );
        localStorage.removeItem(
          'moosic_user'
        );
        onGoToLogin();
        return;
      }

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        alert(
          data.detail ||
            'Failed to record vote.'
        );
        return;
      }

      setThemes((previous) =>
        previous.map((item) =>
          item.date === targetDate
            ? data
            : item
        )
      );
    } catch (error) {
      console.error(error);
      alert('Error saving theme vote.');
    } finally {
      setBusyDate(null);
    }
  };

  const handleDeleteVote = async (
    targetDate
  ) => {
    const token = localStorage.getItem(
      'moosic_token'
    );

    if (!token) {
      onGoToLogin();
      return;
    }

    setBusyDate(targetDate);

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/api/themes/${targetDate}/vote`,
        {
          method: 'DELETE',
          headers: {
            Authorization:
              `Bearer ${token}`
          }
        }
      );

      if (response.status === 401) {
        localStorage.removeItem(
          'moosic_token'
        );
        localStorage.removeItem(
          'moosic_user'
        );
        onGoToLogin();
        return;
      }

      if (!response.ok) {
        const data = await response
          .json()
          .catch(() => ({}));
        alert(
          data.detail ||
            'Failed to remove vote.'
        );
        return;
      }

      await fetchThemes();
    } catch (error) {
      console.error(error);
      alert('Error removing theme vote.');
    } finally {
      setBusyDate(null);
    }
  };

  const handleSkip = async (
    targetDate,
    skipped = true
  ) => {
    if (!currentUser) {
      onGoToLogin();
      return;
    }

    const message = skipped
      ? `Mark ${formatDate(targetDate)} as skipped? Any pending theme votes will be cleared.`
      : `Unskip ${formatDate(targetDate)} and reopen it for a theme?`;

    if (!window.confirm(message)) {
      return;
    }

    const token = localStorage.getItem(
      'moosic_token'
    );

    if (!token) {
      onGoToLogin();
      return;
    }

    setBusyDate(targetDate);

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/api/themes/${targetDate}/skip`,
        {
          method: 'POST',
          headers: {
            'Content-Type':
              'application/json',
            Authorization:
              `Bearer ${token}`
          },
          body: JSON.stringify({
            skipped
          })
        }
      );

      if (response.status === 401) {
        localStorage.removeItem(
          'moosic_token'
        );
        localStorage.removeItem(
          'moosic_user'
        );
        onGoToLogin();
        return;
      }

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        alert(
          data.detail ||
            'Failed to update Thursday status.'
        );
        return;
      }

      setThemes((previous) =>
        previous.map((item) =>
          item.date === targetDate
            ? data
            : item
        )
      );
    } catch (error) {
      console.error(error);
      alert(
        'Error updating Thursday status.'
      );
    } finally {
      setBusyDate(null);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '1.5rem'
      }}
    >
      <section
        style={{
          background:
            'color-mix(in srgb, var(--accent-green) 12%, var(--bg-card))',
          border:
            '1px solid color-mix(in srgb, var(--accent-green) 45%, var(--border-color))',
          borderRadius:
            'var(--border-radius-lg)',
          padding: '1.5rem 1.6rem'
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent:
              'space-between',
            gap: '1rem',
            alignItems: 'flex-start',
            flexWrap: 'wrap'
          }}
        >
          <div>
            <div
              style={{
                fontSize: '0.78rem',
                color:
                  'var(--accent-green)',
                textTransform:
                  'uppercase',
                letterSpacing:
                  '0.1em',
                fontWeight: '700',
                marginBottom: '0.35rem'
              }}
            >
              Thursday rotation
            </div>
            <h2
              style={{
                margin: 0,
                fontSize: '1.55rem'
              }}
            >
              Thursday Themes
            </h2>
            <p
              style={{
                margin:
                  '0.4rem 0 0',
                color:
                  'var(--text-muted)',
                lineHeight: 1.5,
                maxWidth: '720px'
              }}
            >
              Each Thursday gets one rotating proposer. The group votes on the proposal, and a strict majority decides whether the theme is approved. Holiday Thursdays can be skipped.
            </p>
          </div>
        </div>
      </section>

      {!currentUser && (
        <section
          style={{
            background:
              'var(--bg-card)',
            border:
              '1px solid var(--border-color)',
            borderRadius:
              'var(--border-radius-lg)',
            padding: '1rem 1.25rem',
            display: 'flex',
            justifyContent:
              'space-between',
            alignItems: 'center',
            gap: '1rem',
            flexWrap: 'wrap'
          }}
        >
          <div
            style={{
              color:
                'var(--text-muted)'
            }}
          >
            You're viewing themes in read-only mode. Log in to propose, vote, or skip a Thursday.
          </div>
          <button
            onClick={onGoToLogin}
            onMouseEnter={(e) => {
              e.currentTarget.style.filter = 'brightness(1.15)';
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow =
                '0 5px 12px rgba(0, 0, 0, 0.22)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.filter = 'none';
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = 'none';
            }}
            style={{
              background: 'var(--accent-green)',
              color: 'var(--accent-button-text)',
              border: 'none',
              padding: '0.65rem 1rem',
              borderRadius: '8px',
              fontWeight: 'bold',
              cursor: 'pointer',
              transition: 'all 0.18s ease'
            }}
          >
            Log in to participate
          </button>
        </section>
      )}

      {isLoading ? (
        <div
          style={{
            padding: '2rem',
            textAlign: 'center',
            color:
              'var(--text-muted)'
          }}
        >
          Loading Thursday themes…
        </div>
      ) : loadError ? (
        <div
          style={{
            padding: '1.2rem',
            borderRadius: '12px',
            border:
              '1px solid rgba(255,107,107,0.35)',
            background:
              'rgba(255,107,107,0.08)',
            color: '#ff8f8f'
          }}
        >
          {loadError}
        </div>
      ) : (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '2rem'
          }}
        >
          <section>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-end',
                gap: '1rem',
                flexWrap: 'wrap',
                marginBottom: '0.9rem'
              }}
            >
              <div>
                <div
                  style={{
                    color: 'var(--accent-green)',
                    fontSize: '0.72rem',
                    textTransform: 'uppercase',
                    letterSpacing: '0.1em',
                    fontWeight: '800',
                    marginBottom: '0.2rem'
                  }}
                >
                  Coming up
                </div>
                <h2
                  style={{
                    margin: 0,
                    fontSize: '1.35rem'
                  }}
                >
                  Upcoming Thursdays
                </h2>
              </div>
              <span
                style={{
                  color: 'var(--text-muted)',
                  fontSize: '0.78rem'
                }}
              >
                Next 12 Thursdays · updates automatically
              </span>
            </div>

            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '1rem'
              }}
            >
              {upcomingThemes.map((theme) => (
                <ThemeCard
                  key={theme.date}
                  theme={theme}
                  currentUser={currentUser}
                  onSaveTheme={handleSaveTheme}
                  onVote={handleVote}
                  onSkip={handleSkip}
                  busyDate={busyDate}
                  editingDate={editingDate}
                  isPast={false}
                  setEditingDate={setEditingDate}
                  editName={editName}
                  setEditName={setEditName}
                  editDescription={editDescription}
                  setEditDescription={setEditDescription}
                />
              ))}
            </div>
          </section>

          <section>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-end',
                gap: '1rem',
                flexWrap: 'wrap',
                marginBottom: '0.9rem'
              }}
            >
              <div>
                <div
                  style={{
                    color: 'var(--text-muted)',
                    fontSize: '0.72rem',
                    textTransform: 'uppercase',
                    letterSpacing: '0.1em',
                    fontWeight: '800',
                    marginBottom: '0.2rem'
                  }}
                >
                  Archive
                </div>
                <h2
                  style={{
                    margin: 0,
                    fontSize: '1.35rem'
                  }}
                >
                  Past Thursdays
                </h2>
              </div>
              <span
                style={{
                  color: 'var(--text-muted)',
                  fontSize: '0.78rem'
                }}
              >
                Historical record · view only
              </span>
            </div>

            {pastThemes.length === 0 ? (
              <div
                style={{
                  padding: '1rem',
                  borderRadius: '10px',
                  border: '1px solid var(--border-color)',
                  color: 'var(--text-muted)',
                  background: 'var(--bg-card)'
                }}
              >
                No past Thursdays have been recorded yet.
              </div>
            ) : (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '1rem'
                }}
              >
                {pastThemes.map((theme) => (
                  <ThemeCard
                    key={theme.date}
                    theme={theme}
                    currentUser={currentUser}
                    onSaveTheme={handleSaveTheme}
                    onVote={handleVote}
                    onSkip={handleSkip}
                    busyDate={busyDate}
                    editingDate={editingDate}
                    isPast={true}
                    setEditingDate={setEditingDate}
                    editName={editName}
                    setEditName={setEditName}
                    editDescription={editDescription}
                    setEditDescription={setEditDescription}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

export function ThursdayThemeBanner({
  currentUser,
  onGoToThemes
}) {
  const [theme, setTheme] =
    useState(null);
  const [isLoading, setIsLoading] =
    useState(true);

  const targetDate = getNextThursday();

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setIsLoading(true);

      try {
        const token = localStorage.getItem(
          'moosic_token'
        );

        const response = await fetch(
          `${import.meta.env.VITE_API_URL}/api/themes/${targetDate}`,
          {
            headers: token
              ? {
                  Authorization:
                    `Bearer ${token}`
                }
              : {}
          }
        );

        if (!response.ok) {
          throw new Error(
            'Failed to load Thursday theme.'
          );
        }

        const data = await response.json();

        if (!cancelled) {
          setTheme(data);
        }
      } catch (error) {
        console.error(error);
        if (!cancelled) {
          setTheme(null);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    load();

    return () => {
      cancelled = true;
    };
  }, [targetDate, currentUser?.id]);

  if (isLoading || !theme) {
    return null;
  }

  const isSkipped =
    theme.status === 'skipped';
  const hasTheme = Boolean(
    theme.exists && theme.name
  );

  if (!isSkipped && !hasTheme) {
    return null;
  }

  const isApproved =
    theme.status === 'approved';
  const isPending =
    theme.status === 'pending';

  return (
    <section
      style={{
        background: isSkipped
          ? 'var(--bg-card)'
          : isApproved
          ? 'linear-gradient(135deg, rgba(29,185,84,0.14), rgba(29,185,84,0.035))'
          : 'linear-gradient(135deg, rgba(250,204,21,0.12), rgba(250,204,21,0.025))',
        border: isSkipped
          ? '1px solid var(--border-color)'
          : isApproved
          ? '1px solid rgba(29,185,84,0.35)'
          : '1px solid rgba(250,204,21,0.30)',
        borderRadius:
          'var(--border-radius-lg)',
        padding: '1.15rem 1.25rem',
        marginBottom: '1.5rem',
        display: 'flex',
        justifyContent:
          'space-between',
        alignItems: 'center',
        gap: '1rem',
        flexWrap: 'wrap'
      }}
    >
      <div style={{ flex: 1 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            marginBottom: '0.35rem',
            flexWrap: 'wrap'
          }}
        >
          <span
            style={{
              fontSize: '0.72rem',
              color: isSkipped
                ? 'var(--text-muted)'
                : isApproved
                ? '#1db954'
                : '#facc15',
              textTransform:
                'uppercase',
              letterSpacing:
                '0.1em',
              fontWeight: '800'
            }}
          >
            {isSkipped
              ? 'Thursday skipped'
              : isApproved
              ? 'Thursday Theme'
              : 'Thursday Theme Proposal'}
          </span>
          <span
            style={{
              fontSize: '0.75rem',
              color:
                'var(--text-muted)'
            }}
          >
            {formatDate(
              theme.date
            )}
          </span>
        </div>

        {!isSkipped && (
          <>
            <h3
              style={{
                margin: 0,
                fontSize: '1.15rem'
              }}
            >
              {theme.name}
            </h3>
            <p
              style={{
                margin:
                  '0.3rem 0 0',
                color:
                  'var(--text-muted)',
                lineHeight: 1.45
              }}
            >
              {theme.description}
            </p>
            <div
              style={{
                marginTop: '0.4rem',
                fontSize: '0.78rem',
                color:
                  'var(--text-muted)'
              }}
            >
              Proposed by{' '}
              <strong
                style={{
                  color:
                    getUserColor(
                      theme.proposer_username
                    )
                }}
              >
                {theme.proposer_username}
              </strong>
              {isPending && (
                <>
                  {' '}· {theme.yes_count}{' '}
                  in favor · {theme.no_count}{' '}
                  denied · {theme.majority_needed}{' '}
                  needed
                </>
              )}
            </div>
          </>
        )}

        {isSkipped && (
          <p
            style={{
              margin: 0,
              color:
                'var(--text-muted)'
            }}
          >
            No theme this Thursday. Enjoy the holiday/week off.
          </p>
        )}
      </div>

      <button
        onClick={onGoToThemes}
        style={{
          background:
            'transparent',
          color: isApproved
            ? '#1db954'
            : 'var(--text-main)',
          border:
            `1px solid ${
              isApproved
                ? '#1db954'
                : 'var(--border-color)'
            }`,
          padding:
            '0.55rem 0.85rem',
          borderRadius: '8px',
          fontWeight: 'bold',
          cursor: 'pointer',
          whiteSpace: 'nowrap'
        }}
      >
        View Thursday Themes
      </button>
    </section>
  );
}
