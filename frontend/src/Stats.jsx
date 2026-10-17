import { useState, useEffect } from 'react';
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

const getUserColor = (username) => USER_COLORS[username?.toLowerCase()] || '#ffffff';

const getScoreColor = (score) => {
  if (!score || score === 0) return 'transparent'; 
  const validScore = Math.max(1, Math.min(5, score));
  const hue = 120 - ((validScore - 1) * 30);
  return `hsl(${hue}, 80%, 60%)`;
};

const Td = ({ children, align = 'center', bg = 'transparent', color = 'var(--text-main)' }) => (
  <td style={{ padding: '0.6rem', border: '1px solid var(--border-color)', textAlign: align, backgroundColor: bg, color }}>
    {children}
  </td>
);

const Th = ({ children, align = 'center', bg = 'var(--bg-secondary)' }) => (
  <th style={{ padding: '0.6rem', border: '1px solid var(--border-color)', textAlign: align, backgroundColor: bg, color: 'var(--text-main)', fontSize: '0.9rem' }}>
    {children}
  </th>
);

const MatrixTable = ({ title, daysFilter, users, dataObj }) => (
  <div style={{ background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)', overflow: 'hidden', width: '100%' }}>
    <div style={{ background: '#000', padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid var(--border-color)' }}>
      <h3 style={{ margin: 0, fontSize: '0.95rem' }}>{title} <span style={{color: 'var(--accent-green)'}}>{daysFilter}</span> days</h3>
    </div>
    <div style={{ overflowX: 'auto', width: '100%' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
        <thead>
          <tr>
            <Th bg="#000">Poster \ Voter</Th>
            {users.map(u => <Th key={u} bg="#000">{u}</Th>)}
          </tr>
        </thead>
        <tbody>
          {users.map(poster => (
            <tr key={poster}>
              <Th bg="#000">{poster}</Th>
              {users.map(voter => {
                const val = dataObj?.[poster]?.[voter] || 0;
                return (
                  <Td key={voter} bg={getScoreColor(val)} color="#000">
                    <strong>{val > 0 ? val.toFixed(2) : '-'}</strong>
                  </Td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

// Custom Bulletproof SVG Wins Line Chart
const WinsLineChart = ({ data, users }) => {
  if (!data || data.length === 0) {
    return <div style={{ textAlign: 'center', marginTop: '4rem', color: 'var(--text-muted)' }}>Not enough data for chart yet.</div>;
  }

  const width = 800;
  const height = 300;
  const padding = 40;

  const maxWins = Math.max(...data.map(d => Math.max(...users.map(u => d[u] || 0))), 5);
  const minDateIndex = 0;
  const maxDateIndex = Math.max(data.length - 1, 1);

  const getX = (index) => padding + (index / (maxDateIndex)) * (width - padding * 2);
  const getY = (val) => height - padding - (val / maxWins) * (height - padding * 2);

  return (
    <div style={{ width: '100%', overflowX: 'auto' }}>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: '300px' }}>
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => {
          const y = padding + ratio * (height - padding * 2);
          const val = Math.round(maxWins * (1 - ratio));
          return (
            <g key={i}>
              <line x1={padding} y1={y} x2={width - padding} y2={y} stroke="#333" strokeDasharray="4 4" />
              <text x={padding - 10} y={y + 4} fill="var(--text-muted)" fontSize="10" textAnchor="end">{val}</text>
            </g>
          );
        })}

        {/* Lines for each user */}
        {users.map(u => {
          const points = data.map((d, i) => `${getX(i)},${getY(d[u] || 0)}`).join(' ');
          const color = getUserColor(u);
          return (
            <g key={u}>
              <polyline fill="none" stroke={color} strokeWidth="2.5" points={points} />
            </g>
          );
        })}
      </svg>
      {/* Legend */}
      <div style={{ display: 'flex', justifyContent: 'center', gap: '1.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
        {users.map(u => (
          <div key={u} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem' }}>
            <div style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: getUserColor(u) }}></div>
            <span>{u}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default function Stats() {
  const [stats, setStats] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [daysFilter, setDaysFilter] = useState(30); 

  useEffect(() => {
    const fetchStats = async () => {
      setIsLoading(true);
      try {
        const response = await fetch(`${import.meta.env.VITE_API_URL}/api/stats?days=${daysFilter}`);
        if (!response.ok) throw new Error("Failed to fetch");
        const data = await response.json();
        setStats(data);
      } catch (err) {
        console.error("Failed to fetch stats:", err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchStats();
  }, [daysFilter]);

  if (isLoading && !stats) return <div style={{ textAlign: 'center', marginTop: '2rem' }}>Crunching Dashboard Data...</div>;
  if (!stats) return <div style={{ textAlign: 'center', marginTop: '2rem', color: 'red' }}>Error loading stats.</div>;

  const users = stats.usernames || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      
      {/* Top Row: SVG Wins Line Chart */}
      <div style={{ background: 'var(--bg-card)', borderRadius: '8px', padding: '1.5rem', border: '1px solid var(--border-color)' }}>
        <h2 style={{ marginBottom: '1rem', fontSize: '1.2rem', textAlign: 'center' }}>Cumulative Wins Over Time</h2>
        <WinsLineChart data={stats.chart_data} users={users} />
      </div>

      {/* Days Filter Input */}
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '1rem', background: 'var(--bg-card)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
        <label style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>Analyze Past</label>
        <input 
          type="number" 
          value={daysFilter}
          onChange={(e) => setDaysFilter(e.target.value)}
          style={{ width: '80px', padding: '0.5rem', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-main)', fontSize: '1.1rem', textAlign: 'center' }}
        />
        <label style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>Days</label>
      </div>

      {/* Second Row: Static Lifetime Tables */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: '1rem' }}>
        
        <div style={{ background: 'var(--bg-card)', borderRadius: '8px', overflow: 'hidden', border: '1px solid var(--border-color)' }}>
          <div style={{ background: '#000', padding: '0.5rem', textAlign: 'center' }}>
            <h3 style={{ margin: 0, fontSize: '1rem' }}>Player Lifetime Stats</h3>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
              <thead>
                <tr>
                  <Th bg="#000">Player</Th>
                  <Th bg="#000">Wins</Th>
                  <Th bg="#000">Sum of Avg</Th>
                  <Th bg="#000">Overall Avg</Th>
                  <Th bg="#000">Place</Th>
                </tr>
              </thead>
              <tbody>
                {(stats.manager_stats || []).map((s) => (
                  <tr key={s.manager}>
                    <Td bg={getUserColor(s.manager)} color="#000"><strong>{s.manager}</strong></Td>
                    <Td>{s.wins || 0}</Td>
                    <Td>{(s.sum_avg || 0).toFixed(2)}</Td>
                    <Td>{(s.overall_avg || 0).toFixed(2)}</Td>
                    <Td>{s.place || '-'}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ background: 'var(--bg-card)', borderRadius: '8px', overflow: 'hidden', border: '1px solid var(--border-color)' }}>
          <div style={{ background: '#000', padding: '0.5rem', textAlign: 'center' }}>
            <h3 style={{ margin: 0, fontSize: '1rem' }}>Day Rank Frequency</h3>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
              <thead>
                <tr>
                  <Th bg="#000">Poster \ Rank</Th>
                  <Th bg="#000">1</Th><Th bg="#000">2</Th><Th bg="#000">3</Th><Th bg="#000">4</Th><Th bg="#000">5</Th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u}>
                    <Td bg={getUserColor(u)} color="#000"><strong>{u}</strong></Td>
                    <Td>{stats.rank_counts?.[u]?.[1] || 0}</Td>
                    <Td>{stats.rank_counts?.[u]?.[2] || 0}</Td>
                    <Td>{stats.rank_counts?.[u]?.[3] || 0}</Td>
                    <Td>{stats.rank_counts?.[u]?.[4] || 0}</Td>
                    <Td>{stats.rank_counts?.[u]?.[5] || 0}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Third Row: The 6 Matrices Grid */}
      {stats.matrices && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(600px, 1fr))', gap: '1rem' }}>
          <MatrixTable title="Average Score for past" daysFilter={daysFilter} users={users} dataObj={stats.matrices.average} />
          <MatrixTable title="Median Score for past" daysFilter={daysFilter} users={users} dataObj={stats.matrices.median} />
          <MatrixTable title="Standard Deviation for past" daysFilter={daysFilter} users={users} dataObj={stats.matrices.stdev} />
          <MatrixTable title="Mode Score for past" daysFilter={daysFilter} users={users} dataObj={stats.matrices.mode} />
          <MatrixTable title="Best Score for past" daysFilter={daysFilter} users={users} dataObj={stats.matrices.best} />
          <MatrixTable title="Worst Score for past" daysFilter={daysFilter} users={users} dataObj={stats.matrices.worst} />
        </div>
      )}

    </div>
  );
}