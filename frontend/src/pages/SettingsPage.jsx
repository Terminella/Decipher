
import { useState } from 'react'
import {
  UserRound,
  Palette,
  Bell,
  SlidersHorizontal,
  Info,
  Sun,
  Moon,
  Save,
  ShieldCheck,
  Mail,
  Monitor,
  Check,
} from 'lucide-react'

const defaultProfile = {
  name: 'Decipher User',
  email: '',
  role: 'Investigation Analyst',
}

const defaultNotifications = {
  investigationUpdates: true,
  findingAlerts: true,
  reportUpdates: true,
  systemNotifications: false,
}

export default function SettingsPage({ theme = 'dark', onThemeChange }) {
  const [activeSection, setActiveSection] = useState('Profile')
  const [profile, setProfile] = useState(() => {
    try {
      const saved = localStorage.getItem('decipher-profile')
      return saved ? { ...defaultProfile, ...JSON.parse(saved) } : defaultProfile
    } catch {
      return defaultProfile
    }
  })

  const [notifications, setNotifications] = useState(() => {
    try {
      const saved = localStorage.getItem('decipher-notifications')
      return saved
        ? { ...defaultNotifications, ...JSON.parse(saved) }
        : defaultNotifications
    } catch {
      return defaultNotifications
    }
  })

  const [savedMessage, setSavedMessage] = useState('')

  const sections = [
    { name: 'Profile', icon: UserRound, description: 'Manage your personal information' },
    { name: 'Appearance', icon: Palette, description: 'Customize your application theme' },
    { name: 'Notifications', icon: Bell, description: 'Manage notification preferences' },
    { name: 'Preferences', icon: SlidersHorizontal, description: 'Application preferences' },
    { name: 'About', icon: Info, description: 'Application information' },
  ]

  const showSavedMessage = () => {
    setSavedMessage('Settings saved successfully.')
    window.setTimeout(() => setSavedMessage(''), 2500)
  }

  const saveProfile = (event) => {
    event.preventDefault()
    localStorage.setItem('decipher-profile', JSON.stringify(profile))
    showSavedMessage()
  }

  const saveNotifications = () => {
    localStorage.setItem('decipher-notifications', JSON.stringify(notifications))
    showSavedMessage()
  }

  const updateNotification = (key, value) => {
    setNotifications(prev => ({ ...prev, [key]: value }))
  }

  return (
    <div className="settings-page">
      {/* =========================================
          1. SETTINGS HEADER
      ========================================= */}

      <div className="settings-header">
        <div>
          <span className="settings-eyebrow">APPLICATION CONFIGURATION</span>
          <h1>Settings</h1>
          <p>Manage your account, appearance and application preferences.</p>
        </div>
      </div>

      {/* =========================================
          2. SETTINGS LAYOUT
      ========================================= */}

      <div className="settings-layout">

        {/* Settings Sidebar */}

        <aside className="settings-sidebar">
          <div className="settings-sidebar-title">GENERAL SETTINGS</div>

          {sections.map(section => {
            const Icon = section.icon

            return (
              <button
                key={section.name}
                className={`settings-nav-item ${
                  activeSection === section.name ? 'active' : ''
                }`}
                onClick={() => {
                  setActiveSection(section.name)
                  setSavedMessage('')
                }}
              >
                <Icon size={18} />
                <span>
                  <strong>{section.name}</strong>
                  <small>{section.description}</small>
                </span>
              </button>
            )
          })}
        </aside>

        {/* Settings Content */}

        <main className="settings-content">

          {/* =========================================
              3. PROFILE SETTINGS
          ========================================= */}

          {activeSection === 'Profile' && (
            <section className="settings-panel">
              <div className="settings-panel-heading">
                <div>
                  <h2>Profile Information</h2>
                  <p>Update your personal account information.</p>
                </div>
                <UserRound size={21} />
              </div>

              <div className="settings-profile-card">
                <div className="settings-profile-avatar">
                  {profile.name.trim().charAt(0).toUpperCase() || 'U'}
                </div>
                <div>
                  <strong>{profile.name || 'Your Name'}</strong>
                  <span>{profile.role}</span>
                </div>
              </div>

              <form onSubmit={saveProfile}>
                <div className="settings-form-group">
                  <label>Full Name</label>
                  <input
                    value={profile.name}
                    onChange={event =>
                      setProfile({ ...profile, name: event.target.value })
                    }
                    placeholder="Enter your name"
                    required
                  />
                </div>

                <div className="settings-form-group">
                  <label>Email Address</label>
                  <div className="settings-input-icon">
                    <Mail size={17} />
                    <input
                      type="email"
                      value={profile.email}
                      onChange={event =>
                        setProfile({ ...profile, email: event.target.value })
                      }
                      placeholder="Enter your email address"
                    />
                  </div>
                </div>

                <div className="settings-form-group">
                  <label>Role</label>
                  <input
                    value={profile.role}
                    onChange={event =>
                      setProfile({ ...profile, role: event.target.value })
                    }
                    placeholder="Enter your role"
                  />
                </div>

                <div className="settings-form-actions">
                  <button type="submit" className="settings-save-btn">
                    <Save size={16} />
                    Save Profile
                  </button>
                </div>
              </form>
            </section>
          )}

          {/* =========================================
              4. APPEARANCE SETTINGS
          ========================================= */}

          {activeSection === 'Appearance' && (
            <section className="settings-panel">
              <div className="settings-panel-heading">
                <div>
                  <h2>Appearance</h2>
                  <p>Choose how Decipher looks on your device.</p>
                </div>
                <Palette size={21} />
              </div>

              <div className="settings-subsection">
                <h3>Interface Theme</h3>
                <p>Select your preferred application theme.</p>

                <div className="settings-theme-options">

                  <button
                    className={`settings-theme-card ${
                      theme === 'dark' ? 'selected' : ''
                    }`}
                    onClick={() => onThemeChange?.('dark')}
                  >
                    <div className="theme-preview theme-preview-dark">
                      <div className="theme-preview-sidebar" />
                      <div className="theme-preview-content">
                        <div />
                        <div />
                        <div />
                      </div>
                    </div>

                    <div className="settings-theme-info">
                      <span>
                        <Moon size={17} />
                        Dark Mode
                      </span>
                      {theme === 'dark' && <Check size={17} />}
                    </div>
                    <small>Dark background with teal accents</small>
                  </button>

                  <button
                    className={`settings-theme-card ${
                      theme === 'light' ? 'selected' : ''
                    }`}
                    onClick={() => onThemeChange?.('light')}
                  >
                    <div className="theme-preview theme-preview-light">
                      <div className="theme-preview-sidebar" />
                      <div className="theme-preview-content">
                        <div />
                        <div />
                        <div />
                      </div>
                    </div>

                    <div className="settings-theme-info">
                      <span>
                        <Sun size={17} />
                        Light Mode
                      </span>
                      {theme === 'light' && <Check size={17} />}
                    </div>
                    <small>Light background with subtle accents</small>
                  </button>
                </div>
              </div>

              <div className="settings-info-note">
                <Monitor size={18} />
                <p>
                  Your selected theme will apply across the entire Decipher
                  application and will be remembered on this device.
                </p>
              </div>
            </section>
          )}

          {/* =========================================
              5. NOTIFICATION SETTINGS
          ========================================= */}

          {activeSection === 'Notifications' && (
            <section className="settings-panel">
              <div className="settings-panel-heading">
                <div>
                  <h2>Notification Preferences</h2>
                  <p>Choose which application updates you want to receive.</p>
                </div>
                <Bell size={21} />
              </div>

              <div className="settings-notification-list">

                {[
                  {
                    key: 'investigationUpdates',
                    title: 'Investigation Updates',
                    description: 'Updates related to investigation status and activity.',
                  },
                  {
                    key: 'findingAlerts',
                    title: 'Finding Alerts',
                    description: 'Notifications when new findings are recorded.',
                  },
                  {
                    key: 'reportUpdates',
                    title: 'Report Updates',
                    description: 'Updates related to dossiers and reports.',
                  },
                  {
                    key: 'systemNotifications',
                    title: 'System Notifications',
                    description: 'General application and system announcements.',
                  },
                ].map(item => (
                  <div className="settings-notification-item" key={item.key}>
                    <div>
                      <strong>{item.title}</strong>
                      <p>{item.description}</p>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={notifications[item.key]}
                      className={`settings-toggle ${
                        notifications[item.key] ? 'enabled' : ''
                      }`}
                      onClick={() =>
                        updateNotification(item.key, !notifications[item.key])
                      }
                    >
                      <span />
                    </button>
                  </div>
                ))}
              </div>

              <div className="settings-form-actions">
                <button
                  className="settings-save-btn"
                  onClick={saveNotifications}
                >
                  <Save size={16} />
                  Save Preferences
                </button>
              </div>
            </section>
          )}

          {/* =========================================
              6. GENERAL PREFERENCES
          ========================================= */}

          {activeSection === 'Preferences' && (
            <section className="settings-panel">
              <div className="settings-panel-heading">
                <div>
                  <h2>General Preferences</h2>
                  <p>Application defaults and workspace information.</p>
                </div>
                <SlidersHorizontal size={21} />
              </div>

              <div className="settings-preference-item">
                <div>
                  <strong>Application</strong>
                  <p>Decipher Document Intelligence Platform</p>
                </div>
                <span>Web Application</span>
              </div>

              <div className="settings-preference-item">
                <div>
                  <strong>Workspace</strong>
                  <p>Investigation and document analysis workspace</p>
                </div>
                <span>Default</span>
              </div>

              <div className="settings-preference-item">
                <div>
                  <strong>Data Storage</strong>
                  <p>Current frontend preferences are stored locally.</p>
                </div>
                <span>Local Storage</span>
              </div>

              <div className="settings-info-note">
                <ShieldCheck size={18} />
                <p>
                  These preferences currently affect the frontend interface
                  only. No backend configuration is changed.
                </p>
              </div>
            </section>
          )}

          {/* =========================================
              7. ABOUT DECIPHER
          ========================================= */}

          {activeSection === 'About' && (
            <section className="settings-panel">
              <div className="settings-about-brand">
                <div className="settings-about-logo">
                  <ShieldCheck size={32} />
                </div>
                <h2>DECIPHER</h2>
                <span>DOCUMENT INTELLIGENCE PLATFORM</span>
                <p>Version 1.0.0</p>
              </div>

              <div className="settings-about-details">
                <div>
                  <span>Application Name</span>
                  <strong>Decipher</strong>
                </div>
                <div>
                  <span>Version</span>
                  <strong>1.0.0</strong>
                </div>
                <div>
                  <span>Environment</span>
                  <strong>Development Preview</strong>
                </div>
                <div>
                  <span>Interface</span>
                  <strong>React + Vite</strong>
                </div>
              </div>

              <div className="settings-info-note">
                <Info size={18} />
                <p>
                  Decipher is an investigation workspace designed to organize
                  documents, findings, investigations and reports.
                </p>
              </div>
            </section>
          )}

          {/* =========================================
              8. SAVE CONFIRMATION
          ========================================= */}

          {savedMessage && (
            <div className="settings-success-message">
              <Check size={17} />
              {savedMessage}
            </div>
          )}

        </main>
      </div>
    </div>
  )
}
