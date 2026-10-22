import { useState } from 'react';
import './index.css';

export default function Profile({ currentUser, onProfileUpdate, accentColor, changeAccentColor, accentPalettes, theme }) {
  // Safely check for the username, falling back to localStorage if the prop is missing!
  const defaultUser = currentUser?.username || currentUser || localStorage.getItem('user') || '';
  const [username, setUsername] = useState(defaultUser);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  
  const [status, setStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus(null);

    // 1. Validation
    if (password && password !== confirmPassword) {
      setStatus({ type: 'error', message: "Passwords do not match!" });
      return;
    }

    if (!username.trim()) {
      setStatus({ type: 'error', message: "Username cannot be empty!" });
      return;
    }

    setIsLoading(true);
    const token = localStorage.getItem('moosic_token');

    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL}/api/users/update-profile`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          new_username: username,
          new_password: password
        })
      });

      const data = await response.json();

      if (response.ok) {
        setStatus({ type: 'success', message: "Profile successfully updated!" });
        setPassword('');
        setConfirmPassword('');
        
        // Pass the new token and username back up to App.jsx!
        onProfileUpdate(data.access_token, data.username);
      } else {
        setStatus({ type: 'error', message: data.detail || "Failed to update profile." });
      }
    } catch (err) {
      setStatus({ type: 'error', message: "Error connecting to server." });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="profile-layout" style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem', marginTop: '2rem',}}>
      <div className="profile-settings-card accent-settings-card">
        <h2 className="profile-card-title">Accent Color</h2>

        <p className="profile-card-description">
          Choose the accent color used for buttons and highlights across the site.
        </p>

        <div
          className="profile-accent-grid"
          role="group"
          aria-label="Choose accent color"
        >
          {Object.entries(accentPalettes).map(([key, palette]) => (
            <button
              key={key}
              type="button"
              className={`profile-accent-option ${
                accentColor === key ? 'active' : ''
              }`}
              onClick={() => changeAccentColor(key)}
              aria-label={`Choose ${palette.name}`}
              aria-pressed={accentColor === key}
            >
              <span
                className="profile-accent-swatch"
                style={{
                  backgroundColor:
                    palette[theme === 'dark' ? 'dark' : 'light'],
                }}
              />

              <span className="profile-accent-name">{palette.name}</span>

              {accentColor === key && (
                <span className="profile-accent-selected">Selected</span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="profile-settings-card" style={{background: 'var(--bg-card)', padding: '2.5rem', width: '100%', maxWidth: '500px', borderRadius: 'var(--border-radius-lg)', border: '1px solid var(--border-color)',}}>
        <h2 style={{ marginBottom: '0.5rem', fontSize: '1.5rem' }}>Account Settings</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: '2rem', fontSize: '0.9rem' }}>
          Leave the password fields blank if you only want to change your username.
        </p>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
          <div>
            <label style={{ display: 'block', color: 'var(--text-muted)', marginBottom: '0.5rem', fontSize: '0.9rem' }}>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={{ width: '100%', padding: '0.8rem', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-main)', fontSize: '1rem' }}
              required
            />
          </div>

          <div style={{ borderTop: '1px solid var(--border-color)', margin: '1rem 0' }}></div>

          <div>
            <label style={{ display: 'block', color: 'var(--text-muted)', marginBottom: '0.5rem', fontSize: '0.9rem' }}>New Password</label>
            <input
              type="password"
              value={password}
              placeholder="Enter new password..."
              onChange={(e) => setPassword(e.target.value)}
              style={{ width: '100%', padding: '0.8rem', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-main)', fontSize: '1rem' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', color: 'var(--text-muted)', marginBottom: '0.5rem', fontSize: '0.9rem' }}>Confirm New Password</label>
            <input
              type="password"
              value={confirmPassword}
              placeholder="Confirm new password..."
              onChange={(e) => setConfirmPassword(e.target.value)}
              style={{ width: '100%', padding: '0.8rem', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-main)', fontSize: '1rem' }}
            />
          </div>

          {status && (
            <div style={{
              padding: '1rem', borderRadius: '8px', textAlign: 'center', fontWeight: 'bold',
              background: status.type === 'success' ? 'rgba(46, 213, 115, 0.1)' : 'rgba(255, 71, 87, 0.1)',
              color: status.type === 'success' ? '#2ed573' : '#ff4757'
            }}>
              {status.message}
            </div>
          )}

          <button type="submit" disabled={isLoading} style={{
            background: 'var(--accent-green)', color: '#000', border: 'none',
            padding: '1rem', borderRadius: '8px', fontWeight: 'bold', fontSize: '1rem',
            cursor: isLoading ? 'not-allowed' : 'pointer', marginTop: '1rem'
          }}>
            {isLoading ? 'Saving...' : 'Save Changes'}
          </button>
        </form>
      </div>
    </div>
  );
}