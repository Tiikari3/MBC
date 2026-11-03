import { useEffect, useState } from 'react';
import Login from './Login';
import Daily from './Daily';
import History from './History';
import Stats from './Stats';
import Profile from './Profile';
import FridayThemes from "./FridayThemes";
import Brackets from "./Brackets";
import './index.css';

const THEME_MODES = ['dark', 'light', 'fun'];

const THEME_INFO = {
  dark: {
    label: 'Dark mode',
    icon: '☾',
  },
  light: {
    label: 'Light mode',
    icon: '☀',
  },
  fun: {
    label: 'Fun mode',
    icon: '✦',
  },
};

const ACCENT_PALETTES = {
  forest: {
    name: "Forest Green",
    light: "#3F8058",
    dark: "#70C58D",
  },
  ocean: {
    name: "Ocean Blue",
    light: "#3268A5",
    dark: "#83B6F0",
  },
  rose: {
    name: "Rose Pink",
    light: "#AD5275",
    dark: "#F0A0C0",
  },
  plum: {
    name: "Plum",
    light: "#8054A6",
    dark: "#C6A0E8",
  },
  terracotta: {
    name: "Terracotta",
    light: "#A95038",
    dark: "#F0A087",
  },
  amber: {
    name: "Golden Amber",
    light: "#946A13",
    dark: "#E9BF60",
  },
};

export default function App() {
  const [token, setToken] = useState(() => {
    return localStorage.getItem('moosic_token');
  });

  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const saved = localStorage.getItem('moosic_user');
      if (!saved) {
        return null;
      }

      return JSON.parse(saved);
    } catch {
      localStorage.removeItem('moosic_user');
      return null;
    }
  });

  const [activeTab, setActiveTab] = useState('daily');

  const [theme, setTheme] = useState(() => {
    const savedTheme = localStorage.getItem('moosic_theme');

    return THEME_MODES.includes(savedTheme)
      ? savedTheme
      : 'dark';
  });

  const [accentColor, setAccentColor] = useState(
    () => {
      const saved = localStorage.getItem("moosic_accent");
      return saved && ACCENT_PALETTES[saved] ? saved : "forest";
    }
  );
  
  const changeAccentColor = (color) => {
    setAccentColor(color);
    localStorage.setItem("moosic_accent", color);
  };

  useEffect(() => {
    document.documentElement.setAttribute(
      'data-theme',
      theme
    );

    localStorage.setItem('moosic_theme', theme);
  }, [theme]);

  const isLoggedIn = Boolean(
    token &&
      currentUser &&
      currentUser.id &&
      currentUser.username
  );

  const handleLogin = (newToken, userObj) => {
    localStorage.setItem(
      'moosic_token',
      newToken
    );
    localStorage.setItem(
      'moosic_user',
      JSON.stringify(userObj)
    );

    setToken(newToken);
    setCurrentUser(userObj);
    setActiveTab('daily');
  };

  const handleLogout = () => {
    localStorage.removeItem('moosic_token');
    localStorage.removeItem('moosic_user');

    setToken(null);
    setCurrentUser(null);
    setActiveTab('daily');
  };

  const handleProfileUpdate = (
    newToken,
    newUsername
  ) => {
    const updatedUser = {
      ...currentUser,
      username: newUsername
    };

    localStorage.setItem(
      'moosic_token',
      newToken
    );

    localStorage.setItem(
      'moosic_user',
      JSON.stringify(updatedUser)
    );

    setToken(newToken);
    setCurrentUser(updatedUser);
  };

  return (
    <div
      className={`app-shell theme-${theme}`}
      style={{
        minHeight: '100vh',
        background: 'var(--bg-primary)',
        color: 'var(--text-main)',
        padding: '2rem',
        '--accent-green': ACCENT_PALETTES[accentColor][
          theme === 'dark' ? 'dark' : 'light'
        ],
      }}
    >
      <div
        style={{
          maxWidth: '1200px',
          margin: '0 auto'
        }}
      >
        {/* HEADER */}
        <header
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '1rem',
            marginBottom: '2rem',
            borderBottom:
              '1px solid var(--border-color)',
            paddingBottom: '1rem'
          }}
        >
          {/* LOGO + TITLE */}
          <button
            onClick={() => setActiveTab('daily')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              background: 'transparent',
              border: 'none',
              padding: 0,
              margin: 0,
              color: 'inherit',
              cursor: 'pointer',
              minWidth: 0
            }}
            aria-label="Go to Music Book Club home"
          >
            <img
              src="/luckbookclub.jpg"
              alt="MBC logo"
              style={{
                width: '52px',
                height: '52px',
                objectFit: 'contain',
                display: 'block',
                flexShrink: 0
              }}
            />
            <h1
              style={{
                fontSize: '1.8rem',
                fontWeight: 'bold',
                letterSpacing: '-0.5px',
                margin: 0
              }}
            >
              Music Book Club
            </h1>
          </button>

          {/* LOGIN / USER / THEME */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.7rem',
              flexShrink: 0
            }}
          >
            <div
              className="theme-selector"
              role="group"
              aria-label="Choose website theme"
            >
              {THEME_MODES.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={`theme-option ${
                    theme === mode ? 'active' : ''
                  }`}
                  onClick={() => setTheme(mode)}
                  title={THEME_INFO[mode].label}
                  aria-label={`Switch to ${THEME_INFO[mode].label}`}
                  aria-pressed={theme === mode}
                >
                  <span aria-hidden="true">
                    {THEME_INFO[mode].icon}
                  </span>
                </button>
              ))}
            </div>

            {isLoggedIn ? (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1rem'
                }}
              >
                <span
                  className="logged-in-label"
                  style={{
                    color: 'var(--text-muted)',
                    fontSize: '0.9rem'
                  }}
                >
                  Logged in as{' '}
                  <strong
                    style={{
                      color: 'var(--text-main)'
                    }}
                  >
                    {currentUser.username}
                  </strong>
                </span>
                <button
                  onClick={handleLogout}
                  style={{
                    background: 'transparent',
                    color: '#ff4757',
                    border: '1px solid #ff4757',
                    padding: '0.4rem 1rem',
                    borderRadius: '6px',
                    fontWeight: 'bold',
                    cursor: 'pointer',
                    fontSize: '0.85rem'
                  }}
                >
                  Logout
                </button>
              </div>
            ) : (
              <button
                className="read-only-login-button"
                onClick={() => setActiveTab('login')}
                style={{
                  background: 'var(--accent-green)',
                  color: 'var(--accent-button-text)',
                  border: 'none',
                  padding: '0.5rem 1.2rem',
                  borderRadius: '6px',
                  fontWeight: 'bold',
                  cursor: 'pointer'
                }}
              >
                Login
              </button>
            )}
          </div>
        </header>

        {/* NAVIGATION */}
        <nav
          className="nav-tabs"
          style={{
            display: 'flex',
            gap: '1rem',
            marginBottom: '2rem'
          }}
        >
          <button
            className={`nav-tab ${
              activeTab === 'daily' ? 'active' : ''
            }`}
            onClick={() => setActiveTab('daily')}
          >
            Vote
          </button>

          <button
            className={`nav-tab ${
              activeTab === 'friday-themes' ? 'active' : ''
            }`}
            onClick={() => setActiveTab('friday-themes')}
          >
            Friday Themes
          </button>

          <button
            className={`nav-tab ${
              activeTab === 'brackets' ? 'active' : ''
            }`}
            onClick={() => setActiveTab('brackets')}
          >
            Brackets
          </button>

          <button
            className={`nav-tab ${
              activeTab === 'history' ? 'active' : ''
            }`}
            onClick={() => setActiveTab('history')}
          >
            History
          </button>

          <button
            className={`nav-tab ${
              activeTab === 'stats' ? 'active' : ''
            }`}
            onClick={() => setActiveTab('stats')}
          >
            Stats
          </button>

          {isLoggedIn && (
            <button
              className={`nav-tab ${
                activeTab === 'profile' ? 'active' : ''
              }`}
              onClick={() => setActiveTab('profile')}
            >
              Profile
            </button>
          )}
        </nav>

        {/* CONTENT */}
        <main>
          {activeTab === 'login' && (
            <Login onLogin={handleLogin} />
          )}

          {activeTab === 'friday-themes' && (
            <FridayThemes
              currentUser={currentUser}
              onGoToLogin={() => setActiveTab('login')}
            />
          )}

          {activeTab === 'brackets' && (
            <Brackets
              currentUser={currentUser}
              onGoToLogin={() => setActiveTab('login')}
            />
          )}

          {activeTab === 'history' && <History />}

          {activeTab === 'stats' && <Stats />}

          {activeTab === 'daily' && (
            <>
              <Daily
                currentUser={currentUser}
                onGoToLogin={() => setActiveTab('login')}
                onLogout={handleLogout}
              />
            </>
          )}

          {activeTab === 'profile' &&
            isLoggedIn && (
              <Profile
                currentUser={currentUser}
                onProfileUpdate={handleProfileUpdate}
                accentColor={accentColor}
                changeAccentColor={changeAccentColor}
                accentPalettes={ACCENT_PALETTES}
                theme={theme}
              />
            )}
        </main>
      </div>
    </div>
  );
}