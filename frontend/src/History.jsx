import { useState, useEffect, useRef, useCallback } from 'react';
import './index.css';

const USER_COLORS = {
  'alappatjoe': '#4ade80',      
  'danram': '#60a5fa',          
  'loganworsdell': '#fde047',   
  'samuelbattista': '#9ca3af',  
  'currydestroyer27': '#ffb085' 
};

const getUserColor = (username) => {
  return USER_COLORS[username?.toLowerCase()] || '#ffffff';
};

// NEW: Calculates the Excel-style gradient color based on the score
const getScoreColor = (score) => {
  // Ensure the score is between 1 and 8
  const validScore = Math.max(1, Math.min(8, score));
  // 1 = Hue 120 (Green), 4 = Hue 60 (Yellow), 8 = Hue 0 (Red)
  const hue = 120 - ((validScore - 1) * 15);
  // Using 80% saturation and 60% lightness for an OLED-friendly pastel glow
  return `hsl(${hue}, 80%, 60%)`;
};

export default function History() {
  const [historyData, setHistoryData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [selectedDate, setSelectedDate] = useState('');

  const observer = useRef();
  const lastElementRef = useCallback(node => {
    if (isLoading) return;
    if (observer.current) observer.current.disconnect();
    
    observer.current = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasMore) {
        setOffset(prev => prev + 10);
      }
    });
    
    if (node) observer.current.observe(node);
  }, [isLoading, hasMore]);

  useEffect(() => {
    const fetchHistory = async () => {
      setIsLoading(true);
      try {
        let url = `${import.meta.env.VITE_API_URL}/api/history?skip=${offset}&limit=10`;
        if (selectedDate) url += `&specific_date=${selectedDate}`;

        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to fetch history');
        
        const data = await response.json();
        
        if (data.length < 10) setHasMore(false);
        
        if (offset === 0) {
          setHistoryData(data);
        } else {
          setHistoryData(prev => [...prev, ...data]);
        }
      } catch (err) {
        console.error("History fetch error:", err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchHistory();
  }, [offset, selectedDate]);

  const handleDateChange = (e) => {
    setSelectedDate(e.target.value);
    setOffset(0); 
    setHasMore(true);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      
      {/* Calendar Filter Tool */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.5rem' }}>
        <input 
          type="date" 
          value={selectedDate}
          onChange={handleDateChange}
          style={{
            background: 'var(--bg-card)', color: 'var(--text-main)', 
            border: '1px solid var(--border-color)', borderRadius: '8px',
            padding: '0.5rem 1rem', fontSize: '0.9rem', colorScheme: 'dark'
          }}
        />
      </div>

      {/* The History Feed */}
      <div className="history-feed" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
        {historyData.map((day, index) => {
          const isLastElement = historyData.length === index + 1;
          const winnerColor = getUserColor(day.winner.submittedBy);
          
          return (
            <div 
              ref={isLastElement ? lastElementRef : null}
              key={day.date} 
              style={{
                background: 'var(--bg-card)', border: `1px solid var(--border-color)`,
                borderRadius: 'var(--border-radius-md)', padding: '1.5rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem', marginBottom: '1.5rem' }}>
                <h2 style={{ fontSize: '1.2rem', margin: 0 }}>
                  {new Date(day.date).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'UTC' })}
                </h2>
                
                <span style={{ 
                  background: `${winnerColor}30`, 
                  color: winnerColor,
                  border: `1px solid ${winnerColor}50`,
                  padding: '0.3rem 0.8rem', 
                  borderRadius: '12px', 
                  fontSize: '0.85rem', 
                  fontWeight: 'bold' 
                }}>
                  👑 Winner: {day.winner.submittedBy}
                </span>
              </div>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                {day.leaderboard.map((song, rank) => {
                  const submitterColor = getUserColor(song.submittedBy);
                  const avgScoreColor = getScoreColor(song.average);
                  
                  return (
                    <div key={song.song_id} style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <h3 style={{ fontSize: '1.1rem', margin: 0, color: submitterColor, textShadow: '0 1px 2px rgba(0,0,0,0.5)' }}>
                            {rank + 1}. {song.title}
                          </h3>
                          <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', margin: '0.3rem 0 0 0' }}>
                            {song.artist} 
                            <span style={{ opacity: 0.8, marginLeft: '0.5rem' }}>
                              • Submitted by <span style={{ color: submitterColor, fontWeight: '600' }}>{song.submittedBy}</span>
                            </span>
                          </p>
                        </div>
                        
                        <div style={{ textAlign: 'right' }}>
                          {/* UPDATED: Overall Average is now color-coded! */}
                          <div style={{ 
                            fontSize: '1.2rem', 
                            fontWeight: 'bold', 
                            color: avgScoreColor,
                            textShadow: `0 0 8px ${avgScoreColor}40` // Adds a subtle neon glow
                          }}>
                            {song.average.toFixed(2)}
                          </div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>σ: {song.stdev.toFixed(2)}</div>
                        </div>
                      </div>

                      {/* Vote Breakdown Chips */}
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.4rem' }}>
                        {song.votes.map(vote => {
                          const voterColor = getUserColor(vote.username);
                          const voteScoreColor = getScoreColor(vote.score);
                          
                          return (
                            <div key={vote.username} style={{ 
                              background: 'var(--bg-secondary)', 
                              padding: '0.2rem 0.6rem', 
                              borderRadius: '6px', 
                              fontSize: '0.8rem', 
                              border: `1px solid ${voterColor}50`,
                              display: 'flex', 
                              gap: '0.5rem',
                              alignItems: 'center'
                            }}>
                              <span style={{ color: voterColor, fontWeight: '600', letterSpacing: '0.3px' }}>
                                {vote.username}
                              </span>
                              {/* UPDATED: Individual vote is now color-coded! */}
                              <span style={{ 
                                color: voteScoreColor, 
                                fontWeight: '800',
                                textShadow: '0 1px 2px rgba(0,0,0,0.6)'
                              }}>
                                {vote.score}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                      
                    </div>
                  );
                })}
              </div>
            </div>
          )
        })}
        
        {isLoading && (
          <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--text-muted)' }}>
            Loading deeper history...
          </div>
        )}
        {!hasMore && historyData.length > 0 && (
          <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            You've reached the beginning of time.
          </div>
        )}
      </div>
    </div>
  );
}