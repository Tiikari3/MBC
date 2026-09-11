import { useState, useEffect, useCallback } from 'react';
import './index.css';

const USER_COLORS = {
  alappatjoe: '#4ade80',
  danram: '#60a5fa',
  loganworsdell: '#fde047',
  samuelbattista: '#9ca3af',
  currydestroyer27: '#ffb085'
};

const getUserColor = (username) =>
  USER_COLORS[username?.toLowerCase()] || '#ffffff';

const getScoreColor = (score) => {
  const hue =
    120 -
    ((Math.max(1, Math.min(5, score)) - 1) * 30);

  return `hsl(${hue}, 80%, 60%)`;
};

export default function Daily({
  currentUser,
  onGoToLogin
}) {
  const getTodayString = () => {
    const today = new Date();

    return new Date(
      today.getTime() -
        today.getTimezoneOffset() * 60000
    )
      .toISOString()
      .split('T')[0];
  };

  const [selectedDate, setSelectedDate] =
    useState(getTodayString());

  const [targetSongs, setTargetSongs] =
    useState([]);

  const [myVotes, setMyVotes] =
    useState({});

  const [savedVotes, setSavedVotes] =
    useState({});

  const [totalUserCount, setTotalUserCount] =
    useState(5);

  const [isLoadingSongs, setIsLoadingSongs] =
    useState(true);

  const [voteError, setVoteError] =
    useState(null);

  const [submitStatus, setSubmitStatus] =
    useState(null);

  const [isSubmittingVotes, setIsSubmittingVotes] =
    useState(false);

  const [spotifyUrl, setSpotifyUrl] =
    useState('');

  const [previewData, setPreviewData] =
    useState(null);

  const [isPreviewing, setIsPreviewing] =
    useState(false);

  const [editingSong, setEditingSong] =
    useState(null);

  const [editSpotifyUrl, setEditSpotifyUrl] =
    useState('');

  const [editPreviewData, setEditPreviewData] =
    useState(null);

  const [isPreviewingEdit, setIsPreviewingEdit] =
    useState(false);

  const [isUpdatingSong, setIsUpdatingSong] =
    useState(false);

  const [isDeletingSong, setIsDeletingSong] =
    useState(false);

  const [confirmingDelete, setConfirmingDelete] =
    useState(false);

  const handleUnauthorized = useCallback(() => {
    localStorage.removeItem('moosic_token');
    localStorage.removeItem('moosic_user');
    onGoToLogin();
  }, [onGoToLogin]);

  const fetchDataForDate = useCallback(async () => {
    setIsLoadingSongs(true);
    setVoteError(null);

    try {
      const songsResponse = await fetch(
        `${import.meta.env.VITE_API_URL}/api/songs/daily/${selectedDate}`
      );

      if (!songsResponse.ok) {
        throw new Error(
          'Failed to load the daily results.'
        );
      }

      const songs = await songsResponse.json();

      setTargetSongs(songs);

      const statsResponse = await fetch(
        `${import.meta.env.VITE_API_URL}/api/stats`
      );

      if (statsResponse.ok) {
        const stats = await statsResponse.json();

        if (Array.isArray(stats.usernames)) {
          setTotalUserCount(
            stats.usernames.length
          );
        }
      }

      if (currentUser) {
        const token =
          localStorage.getItem('moosic_token');

        if (!token) {
          handleUnauthorized();
          return;
        }

        const myVotesResponse = await fetch(
          `${import.meta.env.VITE_API_URL}/api/votes/me/${selectedDate}`,
          {
            headers: {
              Authorization:
                `Bearer ${token}`
            }
          }
        );

        if (
          myVotesResponse.status === 401
        ) {
          handleUnauthorized();
          return;
        }

        if (myVotesResponse.ok) {
          const voteData =
            await myVotesResponse.json();

          setMyVotes(voteData);
          setSavedVotes(voteData);
        } else {
          setMyVotes({});
          setSavedVotes({});
        }
      } else {
        setMyVotes({});
        setSavedVotes({});
      }
    } catch (error) {
      console.error(
        'Failed to load daily results:',
        error
      );

      setVoteError(
        error.message ||
          'Failed to load the daily results.'
      );
    } finally {
      setIsLoadingSongs(false);
    }
  }, [
    selectedDate,
    currentUser,
    handleUnauthorized
  ]);

  useEffect(() => {
    fetchDataForDate();
  }, [fetchDataForDate]);

  const mySong = currentUser
    ? targetSongs.find(
        (song) =>
          Number(song.submitter_id) ===
          Number(currentUser.id)
      )
    : null;

  /*
   * Winner / current leader
   *
   * Lowest average wins.
   * Standard deviation breaks ties.
   */

  const songsWithVotes =
    targetSongs.filter(
      (song) =>
        Array.isArray(song.votes) &&
        song.votes.length > 0 &&
        song.average !== null &&
        song.average !== undefined
    );

  const sortedSongs =
    [...songsWithVotes].sort(
      (a, b) => {
        const averageDifference =
          Number(a.average) -
          Number(b.average);

        if (
          averageDifference !== 0
        ) {
          return averageDifference;
        }

        return (
          Number(a.stdev || 0) -
          Number(b.stdev || 0)
        );
      }
    );

  const winner =
    sortedSongs.length > 0
      ? sortedSongs[0]
      : null;

  const winnerHasAllVotes =
    Boolean(
      winner &&
        totalUserCount > 0 &&
        Array.isArray(winner.votes) &&
        winner.votes.length ===
          totalUserCount
    );

  const winnerColor = winner
    ? getUserColor(
        winner.submittedBy
      )
    : '#fde047';

  const allSongsPosted =
    targetSongs.length > 0 &&
    targetSongs.length ===
      totalUserCount;

  const allSongsHaveScores =
    targetSongs.length > 0 &&
    targetSongs.every(
      (song) =>
        myVotes[song.id] !== undefined
    );

  const hasChanges =
    JSON.stringify(myVotes) !==
    JSON.stringify(savedVotes);

  const hasExistingSaves =
    Object.keys(savedVotes).length >
    0;

  const canSubmitVotes =
    Boolean(currentUser) &&
    allSongsPosted &&
    allSongsHaveScores &&
    (
      hasChanges ||
      !hasExistingSaves
    );

  const handlePreview = async (event) => {
    event.preventDefault();

    if (!spotifyUrl) {
      return;
    }

    const token =
      localStorage.getItem(
        'moosic_token'
      );

    if (!token) {
      handleUnauthorized();
      return;
    }

    setSubmitStatus(null);
    setIsPreviewing(true);

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/api/songs/fetch-metadata`,
        {
          method: 'POST',
          headers: {
            'Content-Type':
              'application/json',
            Authorization:
              `Bearer ${token}`
          },
          body: JSON.stringify({
            url: spotifyUrl
          })
        }
      );

      if (
        response.status === 401
      ) {
        handleUnauthorized();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {
        setSubmitStatus(
          data.detail ||
            'Failed to fetch metadata.'
        );

        return;
      }

      setPreviewData(data);
    } catch (error) {
      console.error(error);

      setSubmitStatus(
        'Error connecting to Spotify.'
      );
    } finally {
      setIsPreviewing(false);
    }
  };

  const handleDatabaseSubmit =
    async () => {
      if (!previewData) {
        return;
      }

      const token =
        localStorage.getItem(
          'moosic_token'
        );

      if (!token) {
        handleUnauthorized();
        return;
      }

      setSubmitStatus(null);

      try {
        const response =
          await fetch(
            `${import.meta.env.VITE_API_URL}/api/songs`,
            {
              method: 'POST',
              headers: {
                'Content-Type':
                  'application/json',
                Authorization:
                  `Bearer ${token}`
              },
              body: JSON.stringify({
                title:
                  previewData.title,
                artist:
                  previewData.artist,
                spotify_url:
                  previewData.spotify_url ||
                  spotifyUrl,
                spotify_track_id:
                  previewData.spotify_track_id ||
                  null,
                submission_date:
                  selectedDate
              })
            }
          );

        if (
          response.status === 401
        ) {
          handleUnauthorized();
          return;
        }

        const data =
          await response.json();

        if (!response.ok) {
          setSubmitStatus(
            data.detail ||
              'Error saving track.'
          );

          return;
        }

        setSubmitStatus(
          `Success! "${data.title}" added for ${selectedDate}.`
        );

        setSpotifyUrl('');
        setPreviewData(null);

        await fetchDataForDate();
      } catch (error) {
        console.error(error);

        setSubmitStatus(
          'Error saving track.'
        );
      }
    };

  const startEditingSong = (song) => {
    setEditingSong(song);
    setEditSpotifyUrl(
      song.spotify_url || ''
    );
    setEditPreviewData(null);
    setSubmitStatus(null);

    setTimeout(() => {
      const editPanel =
        document.getElementById(
          'edit-song-panel'
        );

      if (editPanel) {
        editPanel.scrollIntoView({
          behavior: 'smooth',
          block: 'center'
        });
      }
    }, 50);
  };

  const cancelEditingSong = () => {
    setEditingSong(null);
    setEditSpotifyUrl('');
    setEditPreviewData(null);
    setSubmitStatus(null);
  };

  const handleEditPreview =
    async (event) => {
      event.preventDefault();

      if (!editSpotifyUrl) {
        return;
      }

      const token =
        localStorage.getItem(
          'moosic_token'
        );

      if (!token) {
        handleUnauthorized();
        return;
      }

      setSubmitStatus(null);
      setIsPreviewingEdit(true);

      try {
        const response =
          await fetch(
            `${import.meta.env.VITE_API_URL}/api/songs/fetch-metadata`,
            {
              method: 'POST',
              headers: {
                'Content-Type':
                  'application/json',
                Authorization:
                  `Bearer ${token}`
              },
              body: JSON.stringify({
                url: editSpotifyUrl
              })
            }
          );

        if (
          response.status === 401
        ) {
          handleUnauthorized();
          return;
        }

        const data =
          await response.json();

        if (!response.ok) {
          setSubmitStatus(
            data.detail ||
              'Failed to fetch metadata.'
          );

          return;
        }

        setEditPreviewData(data);
      } catch (error) {
        console.error(error);

        setSubmitStatus(
          'Error connecting to Spotify.'
        );
      } finally {
        setIsPreviewingEdit(false);
      }
    };

  const handleUpdateSong =
    async () => {
      if (
        !editingSong ||
        !editPreviewData
      ) {
        return;
      }

      const token =
        localStorage.getItem(
          'moosic_token'
        );

      if (!token) {
        handleUnauthorized();
        return;
      }

      setIsUpdatingSong(true);
      setSubmitStatus(null);

      try {
        const response =
          await fetch(
            `${import.meta.env.VITE_API_URL}/api/songs/${editingSong.id}`,
            {
              method: 'PUT',
              headers: {
                'Content-Type':
                  'application/json',
                Authorization:
                  `Bearer ${token}`
              },
              body: JSON.stringify({
                title:
                  editPreviewData.title,
                artist:
                  editPreviewData.artist,
                spotify_url:
                  editPreviewData.spotify_url ||
                  editSpotifyUrl,
                spotify_track_id:
                  editPreviewData.spotify_track_id ||
                  null
              })
            }
          );

        if (
          response.status === 401
        ) {
          handleUnauthorized();
          return;
        }

        const data =
          await response.json();

        if (!response.ok) {
          setSubmitStatus(
            data.detail ||
              'Failed to update song.'
          );

          return;
        }

        setEditingSong(null);
        setEditSpotifyUrl('');
        setEditPreviewData(null);

        setSubmitStatus(
          data.votes_reset
            ? 'Song updated. Votes for the old track were reset.'
            : 'Song updated successfully!'
        );

        await fetchDataForDate();
      } catch (error) {
        console.error(error);

        setSubmitStatus(
          'Error updating song.'
        );
      } finally {
        setIsUpdatingSong(false);
      }
    };

  const handleDeleteSong = async () => {
    if (!mySong) {
      return;
    }

    const token =
      localStorage.getItem('moosic_token');

    if (!token) {
      handleUnauthorized();
      return;
    }

    setIsDeletingSong(true);
    setSubmitStatus(null);

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/api/songs/${mySong.id}`,
        {
          method: 'DELETE',
          headers: {
            Authorization:
              `Bearer ${token}`
          }
        }
      );

      if (response.status === 401) {
        handleUnauthorized();
        return;
      }

      const data =
        await response.json().catch(
          () => ({})
        );

      if (!response.ok) {
        setSubmitStatus(
          data.detail ||
            'Failed to delete song.'
        );
        return;
      }

      setConfirmingDelete(false);
      setEditingSong(null);
      setEditSpotifyUrl('');
      setEditPreviewData(null);

      setSubmitStatus(
        'Success! Your song was deleted.'
      );

      await fetchDataForDate();
    } catch (error) {
      console.error(error);

      setSubmitStatus(
        'Error deleting song.'
      );
    } finally {
      setIsDeletingSong(false);
    }
  };  

  const handleScoreClick =
    (songId, score) => {
      if (!currentUser) {
        onGoToLogin();
        return;
      }

      setVoteError(null);

      setMyVotes(
        (previous) => {
          if (
            previous[songId] ===
            score
          ) {
            const next = {
              ...previous
            };

            delete next[songId];

            return next;
          }

          const scoreTaken =
            Object.entries(
              previous
            ).some(
              ([
                existingSongId,
                existingScore
              ]) =>
                Number(
                  existingSongId
                ) !==
                  Number(songId) &&
                Number(
                  existingScore
                ) ===
                  Number(score)
            );

          if (scoreTaken) {
            setVoteError(
              `Score ${score} is already assigned to another track.`
            );

            return previous;
          }

          return {
            ...previous,
            [songId]:
              score
          };
        }
      );
    };

  const handleSubmitBatchVotes =
    async () => {
      if (!canSubmitVotes) {
        return;
      }

      const token =
        localStorage.getItem(
          'moosic_token'
        );

      if (!token) {
        handleUnauthorized();
        return;
      }

      setIsSubmittingVotes(true);
      setVoteError(null);

      try {
        for (
          const song of targetSongs
        ) {
          const targetScore =
            myVotes[song.id];

          const previousScore =
            savedVotes[song.id];

          if (
            targetScore ===
            previousScore
          ) {
            continue;
          }

          let response;

          if (
            targetScore ===
            undefined
          ) {
            response =
              await fetch(
                `${import.meta.env.VITE_API_URL}/api/votes/${song.id}`,
                {
                  method:
                    'DELETE',
                  headers: {
                    Authorization:
                      `Bearer ${token}`
                  }
                }
              );
          } else {
            response =
              await fetch(
                `${import.meta.env.VITE_API_URL}/api/votes`,
                {
                  method:
                    'POST',
                  headers: {
                    'Content-Type':
                      'application/json',
                    Authorization:
                      `Bearer ${token}`
                  },
                  body:
                    JSON.stringify({
                      song_id:
                        song.id,
                      score:
                        targetScore
                    })
                }
              );
          }

          if (
            response.status ===
            401
          ) {
            handleUnauthorized();
            return;
          }

          if (!response.ok) {
            const data =
              await response
                .json()
                .catch(
                  () => ({})
                );

            throw new Error(
              data.detail ||
                'Failed to save votes.'
            );
          }
        }

        await fetchDataForDate();
      } catch (error) {
        console.error(error);

        setVoteError(
          error.message ||
            'Failed to save votes.'
        );
      } finally {
        setIsSubmittingVotes(false);
      }
    };

  const handleClearAllVotesLocally =
    () => {
      if (!currentUser) {
        onGoToLogin();
        return;
      }

      setMyVotes({});
      setVoteError(null);
    };

  return (
    <div
      style={{
        display:
          'flex',
        flexDirection:
          'column',
        gap:
          '1.5rem'
      }}
    >
      <section
        style={{
          background:
            'var(--bg-card)',
          padding:
            '1.5rem 2rem',
          borderRadius:
            'var(--border-radius-lg)',
          border:
            '1px solid var(--border-color)',
          display:
            'flex',
          justifyContent:
            'space-between',
          alignItems:
            'center',
          flexWrap:
            'wrap',
          gap:
            '1rem'
        }}
      >
        <div>
          <h2
            style={{
              margin: 0,
              fontSize:
                '1.5rem'
            }}
          >
            Daily Moosic
          </h2>

          <p
            style={{
              color:
                'var(--text-muted)',
              margin:
                '0.35rem 0 0',
              fontSize:
                '0.9rem'
            }}
          >
            Browse the songs and
            see exactly how everyone
            voted.
          </p>
        </div>

        <input
          type="date"
          value={selectedDate}
          onChange={(event) =>
            setSelectedDate(
              event.target.value
            )
          }
          style={{
            padding:
              '0.65rem 0.9rem',
            borderRadius:
              '8px',
            border:
              '1px solid var(--border-color)',
            background:
              'var(--bg-secondary)',
            color:
              'var(--text-main)',
            fontSize:
              '1rem'
          }}
        />
      </section>

      {!currentUser && (
        <section
          style={{
            background:
              'linear-gradient(135deg, rgba(29,185,84,0.12), rgba(29,185,84,0.04))',
            border:
              '1px solid rgba(29,185,84,0.35)',
            borderRadius:
              '14px',
            padding:
              '1rem 1.25rem',
            display:
              'flex',
            justifyContent:
              'space-between',
            alignItems:
              'center',
            gap:
              '1rem',
            flexWrap:
              'wrap'
          }}
        >
          <div>
            <strong>
              You're viewing Moosic
              in read-only mode.
            </strong>

            <div
              style={{
                color:
                  'var(--text-muted)',
                fontSize:
                  '0.9rem',
                marginTop:
                  '0.2rem'
              }}
            >
              You can see every
              song and every vote.
              Log in to participate.
            </div>
          </div>

          <button
            onClick={
              onGoToLogin
            }
            style={{
              background:
                'var(--accent-green)',
              color:
                '#000',
              border:
                'none',
              padding:
                '0.65rem 1.2rem',
              borderRadius:
                '8px',
              fontWeight:
                'bold',
              cursor:
                'pointer',
              whiteSpace:
                'nowrap'
            }}
          >
            Log In to Participate
          </button>
        </section>
      )}

      {currentUser && (
        <section
          style={{
            background:
              'var(--bg-card)',
            padding:
              '1.5rem',
            borderRadius:
              'var(--border-radius-lg)',
            border:
              '1px solid var(--border-color)'
          }}
        >
          {mySong ? (
            <div
              style={{
                display:
                  'flex',
                justifyContent:
                  'space-between',
                alignItems:
                  'center',
                gap:
                  '1rem',
                flexWrap:
                  'wrap'
              }}
            >
              <div>
                <div
                  style={{
                    fontSize:
                      '0.78rem',
                    color:
                      'var(--text-muted)',
                    textTransform:
                      'uppercase',
                    letterSpacing:
                      '0.08em'
                  }}
                >
                  Your submission
                </div>

                <h3
                  style={{
                    margin:
                      '0.35rem 0 0'
                  }}
                >
                  {mySong.title}
                </h3>

                <p
                  style={{
                    margin:
                      '0.25rem 0',
                    color:
                      'var(--text-muted)'
                  }}
                >
                  {mySong.artist}
                </p>

                {mySong.spotify_url && (
                  <a
                    href={
                      mySong.spotify_url
                    }
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      color:
                        'var(--accent-green)',
                      fontSize:
                        '0.85rem',
                      textDecoration:
                        'none'
                    }}
                  >
                    Open in Spotify
                  </a>
                )}
              </div>

              <div
  style={{
    display: 'flex',
    gap: '0.6rem',
    alignItems: 'center',
    flexWrap: 'wrap',
    justifyContent: 'flex-end'
  }}
>
  {!confirmingDelete ? (
    <>
      <button
        onClick={() =>
          startEditingSong(mySong)
        }
        style={{
          background:
            'transparent',
          color:
            'var(--accent-green)',
          border:
            '1px solid var(--accent-green)',
          padding:
            '0.6rem 1rem',
          borderRadius:
            '8px',
          fontWeight:
            'bold',
          cursor:
            'pointer'
        }}
      >
        Edit My Song
      </button>

      <button
        onClick={() =>
          setConfirmingDelete(true)
        }
        style={{
          background:
            'transparent',
          color:
            '#ff6b6b',
          border:
            '1px solid rgba(255,107,107,0.55)',
          padding:
            '0.6rem 1rem',
          borderRadius:
            '8px',
          fontWeight:
            'bold',
          cursor:
            'pointer'
        }}
      >
        Delete Song
      </button>
    </>
  ) : (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-end',
        gap: '0.65rem'
      }}
    >
      <div
        style={{
          color: '#ff8f8f',
          fontSize: '0.85rem',
          textAlign: 'right',
          maxWidth: '300px'
        }}
      >
        Delete your submission for this day?
        This will also remove its votes.
      </div>

      <div
        style={{
          display: 'flex',
          gap: '0.6rem'
        }}
      >
        <button
          onClick={() =>
            setConfirmingDelete(false)
          }
          disabled={isDeletingSong}
          style={{
            background:
              'transparent',
            color:
              'var(--text-muted)',
            border:
              '1px solid var(--border-color)',
            padding:
              '0.6rem 1rem',
            borderRadius:
              '8px',
            fontWeight:
              'bold',
            cursor:
              isDeletingSong
                ? 'not-allowed'
                : 'pointer'
          }}
        >
          Cancel
        </button>

        <button
          onClick={handleDeleteSong}
          disabled={isDeletingSong}
          style={{
            background:
              '#ff6b6b',
            color:
              '#111',
            border:
              'none',
            padding:
              '0.6rem 1rem',
            borderRadius:
              '8px',
            fontWeight:
              'bold',
            cursor:
              isDeletingSong
                ? 'not-allowed'
                : 'pointer',
            opacity:
              isDeletingSong
                ? 0.6
                : 1
          }}
        >
          {isDeletingSong
            ? 'Deleting…'
            : 'Delete Song'}
        </button>
      </div>
    </div>
  )}
</div>
            </div>
          ) : (
            <>
              <div
                style={{
                  marginBottom:
                    '0.8rem'
                }}
              >
                <h3
                  style={{
                    margin: 0
                  }}
                >
                  Submit a song for{' '}
                  {selectedDate}
                </h3>

                <p
                  style={{
                    color:
                      'var(--text-muted)',
                    margin:
                      '0.3rem 0 0',
                    fontSize:
                      '0.9rem'
                  }}
                >
                  Paste a Spotify
                  track link and
                  we'll pull the song
                  details automatically.
                </p>
              </div>

              <form
                onSubmit={
                  handlePreview
                }
                style={{
                  display:
                    'flex',
                  gap:
                    '0.75rem',
                  flexWrap:
                    'wrap'
                }}
              >
                <input
                  value={
                    spotifyUrl
                  }
                  onChange={(event) =>
                    setSpotifyUrl(
                      event.target
                        .value
                    )
                  }
                  placeholder="https://open.spotify.com/track/..."
                  required
                  style={{
                    flex:
                      1,
                    minWidth:
                      '260px',
                    padding:
                      '0.8rem 1rem',
                    borderRadius:
                      '8px',
                    border:
                      '1px solid var(--border-color)',
                    background:
                      'var(--bg-secondary)',
                    color:
                      'var(--text-main)',
                    fontSize:
                      '1rem'
                  }}
                />

                <button
                  type="submit"
                  disabled={
                    isPreviewing
                  }
                  style={{
                    background:
                      'var(--bg-secondary)',
                    color:
                      'var(--text-main)',
                    border:
                      '1px solid var(--border-color)',
                    padding:
                      '0 1.2rem',
                    borderRadius:
                      '8px',
                    fontWeight:
                      'bold',
                    cursor:
                      isPreviewing
                        ? 'not-allowed'
                        : 'pointer',
                    opacity:
                      isPreviewing
                        ? 0.6
                        : 1
                  }}
                >
                  {isPreviewing
                    ? 'Loading…'
                    : 'Preview'}
                </button>
              </form>

              {previewData && (
                <div
                  style={{
                    marginTop:
                      '1rem',
                    display:
                      'flex',
                    alignItems:
                      'center',
                    justifyContent:
                      'space-between',
                    gap:
                      '1rem',
                    padding:
                      '1rem',
                    borderRadius:
                      '10px',
                    background:
                      'var(--bg-primary)',
                    border:
                      '1px solid rgba(29,185,84,0.35)',
                    flexWrap:
                      'wrap'
                  }}
                >
                  <div
                    style={{
                      display:
                        'flex',
                      alignItems:
                        'center',
                      gap:
                        '1rem'
                    }}
                  >
                    {previewData.cover_art_url && (
                      <img
                        src={
                          previewData.cover_art_url
                        }
                        alt="Album artwork"
                        style={{
                          width:
                            72,
                          height:
                            72,
                          borderRadius:
                            8,
                          objectFit:
                            'cover'
                        }}
                      />
                    )}

                    <div>
                      <strong
                        style={{
                          fontSize:
                            '1.05rem'
                        }}
                      >
                        {
                          previewData.title
                        }
                      </strong>

                      <div
                        style={{
                          color:
                            'var(--text-muted)',
                          marginTop:
                            '0.2rem'
                        }}
                      >
                        {
                          previewData.artist
                        }
                      </div>

                      {previewData.album && (
                        <div
                          style={{
                            color:
                              'var(--text-muted)',
                            fontSize:
                              '0.8rem',
                            marginTop:
                              '0.15rem'
                          }}
                        >
                          {
                            previewData.album
                          }
                        </div>
                      )}
                    </div>
                  </div>

                  <button
                    onClick={
                      handleDatabaseSubmit
                    }
                    style={{
                      background:
                        'var(--accent-green)',
                      color:
                        '#000',
                      border:
                        'none',
                      padding:
                        '0.7rem 1.2rem',
                      borderRadius:
                        '8px',
                      fontWeight:
                        'bold',
                      cursor:
                        'pointer'
                    }}
                  >
                    Submit for{' '}
                    {selectedDate}
                  </button>
                </div>
              )}
            </>
          )}
        </section>
      )}

      {currentUser &&
        editingSong && (
          <section
            id="edit-song-panel"
            style={{
              background:
                'var(--bg-card)',
              padding:
                '1.5rem',
              borderRadius:
                'var(--border-radius-lg)',
              border:
                '1px solid rgba(29,185,84,0.5)',
              boxShadow:
                '0 8px 30px rgba(0,0,0,0.14)'
            }}
          >
            <div
              style={{
                display:
                  'flex',
                justifyContent:
                  'space-between',
                alignItems:
                  'flex-start',
                gap:
                  '1rem',
                marginBottom:
                  '1rem'
              }}
            >
              <div>
                <h3
                  style={{
                    margin: 0
                  }}
                >
                  Edit your song
                </h3>

                <p
                  style={{
                    color:
                      'var(--text-muted)',
                    margin:
                      '0.3rem 0 0',
                    fontSize:
                      '0.9rem'
                  }}
                >
                  Select a different
                  Spotify track.
                  Changing tracks
                  resets votes for
                  the old track.
                </p>
              </div>

              <button
                onClick={
                  cancelEditingSong
                }
                style={{
                  background:
                    'transparent',
                  color:
                    'var(--text-muted)',
                  border:
                    '1px solid var(--border-color)',
                  padding:
                    '0.45rem 0.8rem',
                  borderRadius:
                    '7px',
                  cursor:
                    'pointer'
                }}
              >
                Cancel
              </button>
            </div>

            <form
              onSubmit={
                handleEditPreview
              }
              style={{
                display:
                  'flex',
                gap:
                  '0.75rem',
                flexWrap:
                  'wrap'
              }}
            >
              <input
                value={
                  editSpotifyUrl
                }
                onChange={(event) =>
                  setEditSpotifyUrl(
                    event.target
                      .value
                  )
                }
                required
                placeholder="Paste the new Spotify track link"
                style={{
                  flex:
                    1,
                  minWidth:
                    '260px',
                  padding:
                    '0.8rem 1rem',
                  borderRadius:
                    '8px',
                  border:
                    '1px solid var(--border-color)',
                  background:
                    'var(--bg-secondary)',
                  color:
                    'var(--text-main)',
                  fontSize:
                    '1rem'
                }}
              />

              <button
                type="submit"
                disabled={
                  isPreviewingEdit
                }
                style={{
                  background:
                    'var(--bg-secondary)',
                  color:
                    'var(--text-main)',
                  border:
                    '1px solid var(--border-color)',
                  padding:
                    '0 1.1rem',
                  borderRadius:
                    '8px',
                  fontWeight:
                    'bold',
                  cursor:
                    isPreviewingEdit
                      ? 'not-allowed'
                      : 'pointer',
                  opacity:
                    isPreviewingEdit
                      ? 0.6
                      : 1
                }}
              >
                {isPreviewingEdit
                  ? 'Loading…'
                  : 'Preview New Song'}
              </button>
            </form>

            {editPreviewData && (
              <div
                style={{
                  marginTop:
                    '1rem',
                  display:
                    'flex',
                  justifyContent:
                    'space-between',
                  alignItems:
                    'center',
                  gap:
                    '1rem',
                  padding:
                    '1rem',
                  background:
                    'var(--bg-primary)',
                  borderRadius:
                    '10px',
                  flexWrap:
                    'wrap'
                }}
              >
                <div
                  style={{
                    display:
                      'flex',
                    alignItems:
                      'center',
                    gap:
                      '1rem'
                  }}
                >
                  {editPreviewData.cover_art_url && (
                    <img
                      src={
                        editPreviewData.cover_art_url
                      }
                      alt="New album artwork"
                      style={{
                        width:
                          72,
                        height:
                          72,
                        borderRadius:
                          8,
                        objectFit:
                          'cover'
                      }}
                    />
                  )}

                  <div>
                    <strong>
                      {
                        editPreviewData.title
                      }
                    </strong>

                    <div
                      style={{
                        color:
                          'var(--text-muted)',
                        marginTop:
                          '0.2rem'
                      }}
                    >
                      {
                        editPreviewData.artist
                      }
                    </div>

                    {editPreviewData.album && (
                      <div
                        style={{
                          color:
                            'var(--text-muted)',
                          fontSize:
                            '0.8rem',
                          marginTop:
                            '0.15rem'
                        }}
                      >
                        {
                          editPreviewData.album
                        }
                      </div>
                    )}
                  </div>
                </div>

                <button
                  onClick={
                    handleUpdateSong
                  }
                  disabled={
                    isUpdatingSong
                  }
                  style={{
                    background:
                      'var(--accent-green)',
                    color:
                      '#000',
                    border:
                      'none',
                    padding:
                      '0.7rem 1.2rem',
                    borderRadius:
                      '8px',
                    fontWeight:
                      'bold',
                    cursor:
                      isUpdatingSong
                        ? 'not-allowed'
                        : 'pointer',
                    opacity:
                      isUpdatingSong
                        ? 0.6
                        : 1
                  }}
                >
                  {isUpdatingSong
                    ? 'Saving…'
                    : 'Save Changes'}
                </button>
              </div>
            )}
          </section>
        )}

      {submitStatus && (
        <div
          style={{
            padding:
              '0.8rem 1rem',
            borderRadius:
              '9px',
            background:
              submitStatus
                .toLowerCase()
                .includes('success') ||
              submitStatus
                .toLowerCase()
                .includes('updated')
                ? 'rgba(46,213,115,0.1)'
                : 'rgba(255,71,87,0.1)',
            color:
              submitStatus
                .toLowerCase()
                .includes('success') ||
              submitStatus
                .toLowerCase()
                .includes('updated')
                ? '#2ed573'
                : '#ff4757',
            textAlign:
              'center',
            fontWeight:
              'bold'
          }}
        >
          {submitStatus}
        </div>
      )}

      <section
        style={{
          background:
            'var(--bg-card)',
          padding:
            '1.5rem',
          borderRadius:
            'var(--border-radius-lg)',
          border:
            '1px solid var(--border-color)'
        }}
      >
        <div
          style={{
            display:
              'flex',
            justifyContent:
              'space-between',
            alignItems:
              'flex-start',
            gap:
              '1rem',
            marginBottom:
              '1.25rem',
            flexWrap:
              'wrap'
          }}
        >
          <div>
            <h3
              style={{
                margin: 0
              }}
            >
              Daily Results
            </h3>

            <p
              style={{
                color:
                  'var(--text-muted)',
                margin:
                  '0.3rem 0 0',
                fontSize:
                  '0.9rem'
              }}
            >
              {targetSongs.length}/
              {totalUserCount}{' '}
              songs posted • public
              results
            </p>
          </div>

          {/* Winner indicator */}
          {winner ? (
            <div
              style={{
                display:
                  'flex',
                alignItems:
                  'center',
                gap:
                  '0.65rem',
                padding:
                  '0.55rem 0.9rem',
                borderRadius:
                  '999px',
                background:
                  `${winnerColor}18`,
                border:
                  `1px solid ${winnerColor}55`,
                boxShadow:
                  `0 0 18px ${winnerColor}12`
              }}
              title={`Winner: ${winner.submittedBy}`}
            >
              <span
                style={{
                  fontSize:
                    '1.15rem',
                  lineHeight:
                    1
                }}
              >
                👑
              </span>

              <div>
                <div
                  style={{
                    fontSize:
                      '0.68rem',
                    color:
                      'var(--text-muted)',
                    textTransform:
                      'uppercase',
                    letterSpacing:
                      '0.08em'
                  }}
                >
                  {winnerHasAllVotes
                    ? 'Winner'
                    : 'Current Leader'}
                </div>

                <strong
                  style={{
                    color:
                      winnerColor,
                    fontSize:
                      '0.9rem'
                  }}
                >
                  {winner.submittedBy}
                </strong>

                <span
                  style={{
                    marginLeft:
                      '0.45rem',
                    color:
                      'var(--text-muted)',
                    fontSize:
                      '0.78rem'
                  }}
                >
                  {Number(
                    winner.average
                  ).toFixed(2)}
                </span>
              </div>
            </div>
          ) : (
            !isLoadingSongs &&
            targetSongs.length >
              0 && (
              <div
                style={{
                  padding:
                    '0.55rem 0.9rem',
                  borderRadius:
                    '999px',
                  background:
                    'var(--bg-secondary)',
                  border:
                    '1px solid var(--border-color)',
                  color:
                    'var(--text-muted)',
                  fontSize:
                    '0.8rem'
                }}
              >
                No votes yet
              </div>
            )
          )}

          {currentUser &&
            targetSongs.length >
              0 && (
              <div
                style={{
                  display:
                    'flex',
                  gap:
                    '0.6rem',
                  flexWrap:
                    'wrap'
                }}
              >
                <button
                  onClick={
                    handleClearAllVotesLocally
                  }
                  style={{
                    background:
                      'transparent',
                    color:
                      '#ff4757',
                    border:
                      '1px solid #ff4757',
                    padding:
                      '0.5rem 0.8rem',
                    borderRadius:
                      '7px',
                    cursor:
                      'pointer',
                    fontSize:
                      '0.85rem'
                  }}
                >
                  Clear Selection
                </button>

                <button
                  onClick={
                    handleSubmitBatchVotes
                  }
                  disabled={
                    !canSubmitVotes ||
                    isSubmittingVotes
                  }
                  style={{
                    background:
                      canSubmitVotes
                        ? 'var(--accent-green)'
                        : 'var(--bg-secondary)',
                    color:
                      canSubmitVotes
                        ? '#000'
                        : 'var(--text-muted)',
                    border:
                      '1px solid var(--border-color)',
                    padding:
                      '0.5rem 1rem',
                    borderRadius:
                      '7px',
                    fontWeight:
                      'bold',
                    cursor:
                      canSubmitVotes &&
                      !isSubmittingVotes
                        ? 'pointer'
                        : 'not-allowed'
                  }}
                >
                  {isSubmittingVotes
                    ? 'Saving…'
                    : hasExistingSaves &&
                        !hasChanges
                      ? 'Submitted'
                      : hasExistingSaves
                        ? 'Re-submit Votes'
                        : 'Submit Votes'}
                </button>
              </div>
            )}
        </div>

        {voteError && (
          <div
            style={{
              marginBottom:
                '1rem',
              padding:
                '0.8rem 1rem',
              borderRadius:
                '8px',
              background:
                'rgba(255,71,87,0.1)',
              color:
                '#ff4757'
            }}
          >
            {voteError}
          </div>
        )}

        {isLoadingSongs ? (
          <div
            style={{
              textAlign:
                'center',
              color:
                'var(--text-muted)',
              padding:
                '2rem'
            }}
          >
            Loading daily results…
          </div>
        ) : targetSongs.length ===
          0 ? (
          <div
            style={{
              textAlign:
                'center',
              color:
                'var(--text-muted)',
              padding:
                '2rem'
            }}
          >
            No songs have been
            posted for{' '}
            {selectedDate} yet.
          </div>
        ) : (
          <div
            style={{
              display:
                'flex',
              flexDirection:
                'column',
              gap:
                '0.9rem'
            }}
          >
            {targetSongs.map(
              (song) => {
                const submitterColor =
                  getUserColor(
                    song.submittedBy
                  );

                const isMySong =
                  currentUser &&
                  Number(
                    song.submitter_id
                  ) ===
                    Number(
                      currentUser.id
                    );

                const isWinner =
                  Boolean(
                    winner &&
                    winner.id ===
                      song.id
                  );

                const average =
                  Number(
                    song.average || 0
                  );

                return (
                  <article
                    key={
                      song.id
                    }
                    style={{
                      background:
                        'var(--bg-primary)',
                      border:
                        isWinner
                          ? `1px solid ${winnerColor}66`
                          : '1px solid var(--border-color)',
                      borderRadius:
                        '12px',
                      padding:
                        '1rem',
                      display:
                        'flex',
                      flexDirection:
                        'column',
                      gap:
                        '0.9rem',
                      boxShadow:
                        isWinner
                          ? `0 0 18px ${winnerColor}10`
                          : 'none'
                    }}
                  >
                    <div
                      style={{
                        display:
                          'flex',
                        justifyContent:
                          'space-between',
                        alignItems:
                          'flex-start',
                        gap:
                          '1rem',
                        flexWrap:
                          'wrap'
                      }}
                    >
                      <div
                        style={{
                          minWidth:
                            0,
                          flex:
                            1
                        }}
                      >
                        <div
                          style={{
                            display:
                              'flex',
                            alignItems:
                              'center',
                            gap:
                              '0.5rem'
                          }}
                        >
                          {isWinner && (
                            <span
                              title={
                                winnerHasAllVotes
                                  ? 'Winner'
                                  : 'Current leader'
                              }
                              style={{
                                fontSize:
                                  '1rem'
                              }}
                            >
                              👑
                            </span>
                          )}

                          <h4
                            style={{
                              margin:
                                0,
                              fontSize:
                                '1.08rem',
                              color:
                                submitterColor
                            }}
                          >
                            {song.title}
                          </h4>
                        </div>

                        <div
                          style={{
                            color:
                              'var(--text-muted)',
                            marginTop:
                              '0.25rem',
                            fontSize:
                              '0.9rem'
                          }}
                        >
                          {song.artist}

                          <span
                            style={{
                              opacity:
                                0.75
                            }}
                          >
                            {' '}
                            • Submitted by{' '}
                          </span>

                          <strong
                            style={{
                              color:
                                submitterColor
                            }}
                          >
                            {
                              song.submittedBy
                            }
                          </strong>
                        </div>

                        <div
                          style={{
                            display:
                              'flex',
                            gap:
                              '0.75rem',
                            marginTop:
                              '0.45rem',
                            alignItems:
                              'center',
                            flexWrap:
                              'wrap'
                          }}
                        >
                          {song.spotify_url && (
                            <a
                              href={
                                song.spotify_url
                              }
                              target="_blank"
                              rel="noreferrer"
                              style={{
                                color:
                                  'var(--accent-green)',
                                fontSize:
                                  '0.8rem',
                                textDecoration:
                                  'none'
                              }}
                            >
                              Open in Spotify ↗
                            </a>
                          )}

                          <span
                            style={{
                              color:
                                'var(--text-muted)',
                              fontSize:
                                '0.8rem'
                            }}
                          >
                            {song.average !==
                            null &&
                            song.average !==
                              undefined
                              ? `Average ${average.toFixed(2)}`
                              : 'No votes yet'}

                            {song.vote_count
                              ? ` • ${song.vote_count} vote${song.vote_count === 1 ? '' : 's'}`
                              : ''}
                          </span>

                          {isMySong && (
                            <button
                              onClick={() =>
                                startEditingSong(
                                  song
                                )
                              }
                              style={{
                                background:
                                  'transparent',
                                color:
                                  'var(--accent-green)',
                                border:
                                  '1px solid var(--accent-green)',
                                padding:
                                  '0.25rem 0.6rem',
                                borderRadius:
                                  '6px',
                                fontSize:
                                  '0.75rem',
                                cursor:
                                  'pointer'
                              }}
                            >
                              Edit
                            </button>
                          )}
                        </div>
                      </div>

                      <div
                        style={{
                          textAlign:
                            'right',
                          minWidth:
                            '70px'
                        }}
                      >
                        {song.average !==
                          null &&
                          song.average !==
                            undefined && (
                            <>
                              <div
                                style={{
                                  fontSize:
                                    '1.35rem',
                                  fontWeight:
                                    'bold',
                                  color:
                                    getScoreColor(
                                      average
                                    )
                                }}
                              >
                                {average.toFixed(
                                  2
                                )}
                              </div>

                              <div
                                style={{
                                  fontSize:
                                    '0.72rem',
                                  color:
                                    'var(--text-muted)'
                                }}
                              >
                                average
                              </div>
                            </>
                          )}
                      </div>
                    </div>

                    <div
                      style={{
                        display:
                          'flex',
                        justifyContent:
                          'space-between',
                        alignItems:
                          'center',
                        gap:
                          '1rem',
                        flexWrap:
                          'wrap'
                      }}
                    >
                      <div
                        style={{
                          fontSize:
                            '0.76rem',
                          color:
                            'var(--text-muted)',
                          textTransform:
                            'uppercase',
                          letterSpacing:
                            '0.08em'
                        }}
                      >
                        {currentUser
                          ? 'Your vote'
                          : 'Voting'}
                      </div>

                      <div
                        style={{
                          display:
                            'flex',
                          gap:
                            '0.4rem',
                          alignItems:
                            'center',
                          opacity:
                            currentUser
                              ? 1
                              : 0.65
                        }}
                      >
                        {[1, 2, 3, 4, 5].map(
                          (score) => {
                            const selected =
                              Boolean(
                                currentUser
                              ) &&
                              myVotes[
                                song.id
                              ] ===
                                score;

                            const baseColor =
                              getScoreColor(
                                score
                              );

                            return (
                              <button
                                key={
                                  score
                                }
                                onClick={() =>
                                  handleScoreClick(
                                    song.id,
                                    score
                                  )
                                }
                                disabled={
                                  !currentUser
                                }
                                title={
                                  currentUser
                                    ? `Give ${song.title} a ${score}`
                                    : 'Log in to vote'
                                }
                                style={{
                                  width:
                                    38,
                                  height:
                                    38,
                                  borderRadius:
                                    '9px',
                                  border:
                                    `2px solid ${
                                      selected
                                        ? baseColor
                                        : `${baseColor}55`
                                    }`,
                                  background:
                                    selected
                                      ? baseColor
                                      : 'transparent',
                                  color:
                                    selected
                                      ? '#000'
                                      : baseColor,
                                  fontWeight:
                                    'bold',
                                  cursor:
                                    currentUser
                                      ? 'pointer'
                                      : 'not-allowed',
                                  transition:
                                    'all 0.15s ease'
                                }}
                              >
                                {score}
                              </button>
                            );
                          }
                        )}
                      </div>
                    </div>

                    <div
                      style={{
                        borderTop:
                          '1px solid var(--border-color)',
                        paddingTop:
                          '0.8rem'
                      }}
                    >
                      <div
                        style={{
                          fontSize:
                            '0.76rem',
                          textTransform:
                            'uppercase',
                          letterSpacing:
                            '0.08em',
                          color:
                            'var(--text-muted)',
                          marginBottom:
                            '0.55rem'
                        }}
                      >
                        Everyone's Votes
                      </div>

                      {song.votes?.length ? (
                        <div
                          style={{
                            display:
                              'flex',
                            gap:
                              '0.5rem',
                            flexWrap:
                              'wrap'
                          }}
                        >
                          {song.votes.map(
                            (vote) => {
                              const voterColor =
                                getUserColor(
                                  vote.username
                                );

                              return (
                                <div
                                  key={`${song.id}-${vote.username}`}
                                  style={{
                                    display:
                                      'flex',
                                    alignItems:
                                      'center',
                                    gap:
                                      '0.45rem',
                                    padding:
                                      '0.4rem 0.65rem',
                                    borderRadius:
                                      '999px',
                                    background:
                                      'var(--bg-card)',
                                    border:
                                      `1px solid ${voterColor}50`
                                  }}
                                >
                                  <span
                                    style={{
                                      color:
                                        voterColor,
                                      fontSize:
                                        '0.82rem',
                                      fontWeight:
                                        '600'
                                    }}
                                  >
                                    {
                                      vote.username
                                    }
                                  </span>

                                  <strong
                                    style={{
                                      color:
                                        getScoreColor(
                                          vote.score
                                        ),
                                      fontSize:
                                        '0.85rem'
                                    }}
                                  >
                                    {
                                      vote.score
                                    }
                                  </strong>
                                </div>
                              );
                            }
                          )}
                        </div>
                      ) : (
                        <span
                          style={{
                            color:
                              'var(--text-muted)',
                            fontSize:
                              '0.85rem'
                          }}
                        >
                          No votes have been
                          submitted yet.
                        </span>
                      )}
                    </div>
                  </article>
                );
              }
            )}
          </div>
        )}
      </section>
    </div>
  );
}